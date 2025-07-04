import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Secret", "1")
from gi.repository import Gtk, Adw, Gio, Secret, GLib, GObject
import fitz, sys, os, re
from datetime import datetime, timezone, timedelta
from cryptography import x509
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers, fields
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.signers.pdf_signer import PdfSigner, PdfSignatureMetadata
from pyhanko.keys.internal import (
    translate_pyca_cryptography_key_to_asn1,
    translate_pyca_cryptography_cert_to_asn1
)
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore
from pyhanko.pdf_utils.generic import ArrayObject

from i18n import I18NManager
from certificate_manager import CertificateManager, KEYRING_SCHEMA
from config_manager import ConfigManager
from ui.dialogs import create_stamp_editor_dialog
from stamp_creator import HtmlStamp, pango_to_html
from pyhanko.stamp import StaticStampStyle

class SignatureDetails:
    def __init__(self, pyhanko_sig, validation_status, page_num, rect):
        self.pyhanko_sig = pyhanko_sig
        self.status = validation_status
        self.intact = validation_status.intact
        self.valid = validation_status.valid
        self.trusted = validation_status.trusted
        self.revoked = validation_status.revoked
        self.valid = validation_status.bottom_line
        self.signer_name = "Unknown"
        self.sign_time = None
        self.issuer_cn = "Unknown"
        self.serial = "Unknown"
        self.page_num = page_num
        self.rect = rect
        
        sig_obj = pyhanko_sig.sig_object
        self.reason = str(sig_obj.get('/Reason', ''))
        self.location = str(sig_obj.get('/Location', ''))
        self.contact_info = str(sig_obj.get('/ContactInfo', ''))
       
        cert = getattr(validation_status, 'signer_cert', None)
        if not cert:
            cert = pyhanko_sig.signer_cert
        def get_cn_from_name(name_obj):
            if not name_obj: return "N/A"
            try:
                native_dict = name_obj.native
                return native_dict.get('common_name', str(name_obj))
            except Exception: return str(name_obj)
        if cert:
            try:
                self.signer_name = get_cn_from_name(cert.subject)
                self.issuer_cn = get_cn_from_name(cert.issuer)
                self.serial = str(cert.serial_number)
            except Exception as e:
                print(f"Error parsing certificate details: {e}")
                self.signer_name = str(cert.subject) if cert.subject else "Parsing Error"
                self.issuer_cn = str(cert.issuer) if cert.issuer else "Parsing Error"
        self.sign_time = None
        try:
            signed_attrs = self.pyhanko_sig.signer_info['signed_attrs']
            for attr in signed_attrs:
                if attr['type'].native == 'signing_time':
                    self.sign_time = attr['values'][0].native
                    break
        except (KeyError, AttributeError, IndexError, TypeError) as e:
            print(f"Could not extract signing_time from signed attributes: {e}")
            self.sign_time = None
        if not self.sign_time and validation_status.timestamp_validity:
            self.sign_time = validation_status.timestamp_validity.timestamp

class GnomeSign(Adw.Application):
    __gsignals__ = {
        'language-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'certificates-changed': (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self):
        super().__init__(application_id="org.pepeg.GnomeSign", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = ConfigManager()
        self.i18n = I18NManager()
        self.cert_manager = CertificateManager()
        self.doc, self.current_page, self.active_cert_path = None, 0, None
        self.page, self.display_pixbuf, self.current_file_path = None, None, None
        self.signature_rect, self.is_dragging_rect = None, False
        self.drag_offset_x, self.drag_offset_y = 0, 0
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.highlight_rect = None
        self.window, self.stamp_editor_window, self.preferences_window = None, None, None
        self.signatures = []
    
    def _(self, key): return self.i18n._(key)
    
    def do_startup(self):
        Adw.Application.do_startup(self)
        self.config.load()
        self.i18n.set_language(self.config.get_language())
        self.cert_manager.set_cert_paths(self.config.get_cert_paths())
        self._build_actions()
        self.active_cert_path = self.config.get_active_cert_path()
        from ui.app_window import AppWindow
        self.window = AppWindow(application=self)
        self.window.sidebar.connect("signature-selected", self.on_signature_selected)
        self.connect("certificates-changed", self.on_certificates_changed) 
        def on_window_close_request(window):
            self.quit()
            return True
        self.window.connect("close-request", on_window_close_request)
    
    def on_certificates_changed(self, app): self.update_ui()
    
    def do_activate(self):
        self.window.present()
        self.update_ui()
    
    def do_open(self, files, n_files, hint):
        if n_files > 0 and files[0].get_path(): self.open_file_path(files[0].get_path())
        self.do_activate()
    
    def _build_actions(self):
        actions_with_params = [("open_recent", self.on_open_recent_clicked, "s"), ("change_lang", self.on_lang_change_state, 's', self.i18n.get_language())]
        for name, callback, p_type, *state in actions_with_params:
            action = Gio.SimpleAction.new_stateful(name, GLib.VariantType(p_type), GLib.Variant(p_type, state[0])) if state else Gio.SimpleAction.new(name, GLib.VariantType(p_type))
            if state: action.connect("change-state", callback)
            else: action.connect("activate", callback)
            self.add_action(action)
        simple_actions = [
            ("open", self.on_open_pdf_clicked), ("sign", self.on_sign_document_clicked), 
            ("preferences", self.on_preferences_clicked), ("manage_certs", self.on_preferences_clicked), 
            ("about", self.on_about_clicked), ("edit_stamps", self.on_edit_stamps_clicked),
            ("show_signatures", self.on_show_signatures_clicked)
        ]
        for name, callback in simple_actions:
            action = Gio.SimpleAction.new(name, None); action.connect("activate", callback); self.add_action(action)

    def open_file_path(self, file_path, show_toast=True):
        try:
            if not os.path.exists(file_path): raise FileNotFoundError(f"File not found: {file_path}")
            if self.doc: self.doc.close()
            self.signatures = []
            try:
                with open(file_path, 'rb') as f:
                    r = PdfFileReader(f, strict=False)
                    vc = ValidationContext(allow_fetching=True) 
                    pages = list(r.root['/Pages']['/Kids'])
                    for sig in r.embedded_signatures:
                        try:
                            page_ref = sig.sig_field.get('/P')
                            page_num = pages.index(page_ref)
                            
                            rect = sig.sig_field.get('/Rect')
                            if isinstance(rect, ArrayObject):
                                rect = [float(v) for v in rect]
                            
                            status = validate_pdf_signature(sig, vc, skip_diff=True)
                            self.signatures.append(SignatureDetails(sig, status, page_num, rect))
                        except (ValueError, KeyError) as e:
                            print(f"Could not locate signature '{sig.field_name}': {e}")
                            status = validate_pdf_signature(sig, vc, skip_diff=True)
                            self.signatures.append(SignatureDetails(sig, status, -1, None))
            except Exception as e:
                print(f"Could not analyze for signatures: {e}")
            self.current_file_path = file_path; self.doc = fitz.open(file_path); self.current_page = 0
            self.config.add_recent_file(file_path); self.config.set_last_folder(os.path.dirname(file_path)); self.config.save()
            self.reset_signature_state(); self.display_page(self.current_page)
            if self.window: 
                self.window.sidebar.populate(self.doc, self.signatures)
                if self.signatures:
                    self.window.show_signature_info(len(self.signatures))
                elif self.active_cert_path and show_toast:
                    self.window.show_toast(self._("toast_select_area"), timeout=4)
        except Exception as e:
            if self.window: self.window.show_toast(self._("open_pdf_error").format(e))
            self.doc = None; self.signatures = []; self.update_ui()

    def on_show_signatures_clicked(self, action, param):
        if self.window:
            if not self.window.flap.get_reveal_flap():
                self.window.flap.set_reveal_flap(True)
            self.window.hide_signature_info()
            self.window.sidebar.focus_on_signatures()
            
    def on_signature_selected(self, sidebar, sig_details):
        """Handles a click on a signature in the sidebar, showing a details dialog."""
        if sig_details.page_num != -1:
            self.display_page(sig_details.page_num, keep_sidebar_view=True)
            if sig_details.rect and self.window:
                self.highlight_rect = sig_details.rect
                self.window.scroll_to_rect(sig_details.rect)
                self.window.drawing_area.queue_draw()
        
        dialog = Adw.MessageDialog.new(self.window,
                                       heading=self._("sig_details_title"))
        
        validity_parts = [f"<b>{self._('sig_validity_title')}</b>"]
        if sig_details.intact and sig_details.valid:
            validity_parts.append(f"<span color='green'>{self._('sig_integrity_ok')}</span>")
            if sig_details.trusted:
                 validity_parts.append(f"<span color='green'>{self._('sig_trust_ok')}</span>")
            elif sig_details.revoked:
                 validity_parts.append(f"<span color='red'>{self._('sig_revoked')}</span>")
            else:
                 validity_parts.append(f"<span color='orange'>{self._('sig_trust_untrusted')}</span>")
        else:
            validity_parts.append(f"<span color='red'>{self._('sig_integrity_error')}</span>")
        validity_text = "\n".join(validity_parts)
        
        signer_esc = GLib.markup_escape_text(sig_details.signer_name)
        issuer_esc = GLib.markup_escape_text(sig_details.issuer_cn)
        serial_esc = GLib.markup_escape_text(sig_details.serial)
        
        details_parts = [
            validity_text,
            f"<b>{self._('signer')}:</b> {signer_esc}",
            f"<b>{self._('sign_date')}:</b> {sig_details.sign_time.strftime('%Y-%m-%d %H:%M:%S %Z') if sig_details.sign_time else 'N/A'}"
        ]
        
        if sig_details.reason:
            reason_esc = GLib.markup_escape_text(sig_details.reason)
            details_parts.append(f"<b>{self._('signature_reason_label')}:</b> {reason_esc}")

        if sig_details.location:
            location_esc = GLib.markup_escape_text(sig_details.location)
            details_parts.append(f"<b>{self._('signature_location_label')}:</b> {location_esc}")
            
        if sig_details.contact_info:
            contact_esc = GLib.markup_escape_text(sig_details.contact_info)
            details_parts.append(f"<b>{self._('signature_contact_label')}:</b> {contact_esc}")

        details_parts.extend([
            f"\n<b>{self._('issuer')}:</b> {issuer_esc}",
            f"<b>{self._('serial')}:</b> {serial_esc}"
        ])
        details_text = "\n".join(details_parts)
        
        body_label = Gtk.Label()
        
        body_label.set_markup(details_text)
        body_label.set_wrap(True)
        body_label.set_justify(Gtk.Justification.CENTER) 
        body_label.set_xalign(0)
        body_label.set_size_request(350, 0) 
        
        dialog.set_extra_child(body_label)
        
        dialog.add_response("ok", self._("accept"))
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        dialog.present()

    def on_open_pdf_clicked(self, action, param):
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file: self.open_file_path(file.get_path())
        file_chooser = Gtk.FileChooserNative.new(self._("open_pdf_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name(self._("pdf_files"))
        filter_pdf.add_mime_type("application/pdf")
        file_chooser.add_filter(filter_pdf)
        last_folder = self.config.get_last_folder()
        if os.path.isdir(last_folder):
            file_chooser.set_current_folder(Gio.File.new_for_path(last_folder))
        file_chooser.connect("response", on_response)
        file_chooser.show()

    def on_open_recent_clicked(self, action, param):
        file_path = param.get_string()
        if os.path.exists(file_path): self.open_file_path(file_path)
        else:
            if self.window: self.window.show_toast(f"File not found: {file_path}")
            self.config.remove_recent_file(file_path); self.config.save(); self.update_ui()
    
    def on_preferences_clicked(self, action, param):
        if self.preferences_window:
            self.preferences_window.present()
            return
        page_name = None
        if action.get_name() == 'manage_certs': page_name = 'certificates'
        from ui.preferences_window import PreferencesWindow
        self.preferences_window = PreferencesWindow(
            application=self, 
            transient_for=self.window, 
            initial_page_name=page_name
        )
        self.preferences_window.connect("close-request", self.on_preferences_close_request)
        self.preferences_window.present()

    def on_preferences_close_request(self, widget):
        self.preferences_window = None

    def on_edit_stamps_clicked(self, action, param): create_stamp_editor_dialog(self.window, self, self.config)
    def on_lang_change_state(self, action, value):
        new_lang = value.get_string()
        if action.get_state().get_string() != new_lang:
            action.set_state(value); self.i18n.set_language(new_lang)
            self.config.set_language(new_lang)
            self.emit('language-changed') 
            self.update_ui()

    def on_sign_document_clicked(self, action=None, param=None):
        """Handles the 'sign' action, performing the cryptographic signing process."""
        if not self.active_cert_path:
            if self.window: self.window.show_toast(self._("no_cert_selected_error")); return
        if not all([self.doc, self.signature_rect, self.current_file_path]):
            if self.window: self.window.show_toast(self._("need_pdf_and_area")); return

        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": self.active_cert_path}, None)
        if not password:
            if self.window: self.window.show_toast(self._("credential_load_error")); return

        private_key_pyca, certificate_pyca = self.cert_manager.get_credentials(self.active_cert_path, password)
        if not (private_key_pyca and certificate_pyca):
            if self.window: self.window.show_toast(self._("credential_load_error")); return

        signing_key_asn1 = translate_pyca_cryptography_key_to_asn1(private_key_pyca)
        signer_cert_asn1 = translate_pyca_cryptography_cert_to_asn1(certificate_pyca)
        
        output_path = self.current_file_path.replace(".pdf", "-signed.pdf"); version = 1
        while os.path.exists(output_path):
            output_path = f"{os.path.splitext(self.current_file_path)[0]}-signed-{version}.pdf"; version += 1
        
        try:
            signer = signers.SimpleSigner(signing_cert=signer_cert_asn1, signing_key=signing_key_asn1, cert_registry=SimpleCertificateStore.from_certs([signer_cert_asn1]))
            
            x, y, w, h = self.signature_rect
            view_width = self.window.drawing_area.get_width()
            scale = self.page.rect.width / view_width if view_width > 0 else 1
            fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
            
            from stamp_creator import HtmlStamp, pango_to_html
            
            parsed_pango_text = self.get_parsed_stamp_text(certificate_pyca)
            html_content = pango_to_html(parsed_pango_text)
            
            stamp_creator = HtmlStamp(
                html_content=html_content,
                width=fitz_rect.width,
                height=fitz_rect.height
            )
            stamp_style = stamp_creator.get_style()

            field_name = f'Signature-{int(datetime.now().timestamp() * 1000)}'

            meta_kwargs = {'field_name': field_name}
            
            reason = self.config.get_signature_reason()
            if reason:
                meta_kwargs['reason'] = reason
            
            location = self.config.get_signature_location()
            if location:
                meta_kwargs['location'] = location

            meta = PdfSignatureMetadata(**meta_kwargs)

            page_height = self.page.rect.height
            pdf_box_y0 = page_height - fitz_rect.y1
            pdf_box_y1 = page_height - fitz_rect.y0

            new_field_spec = fields.SigFieldSpec(
                sig_field_name=field_name,
                on_page=self.current_page,
                box=(fitz_rect.x0, pdf_box_y0, fitz_rect.x1, pdf_box_y1)
            )
            
            pdf_signer = PdfSigner(
                meta, 
                signer, 
                stamp_style=stamp_style,
                new_field_spec=new_field_spec
            )
            
            with open(self.current_file_path, "rb") as orig_f, open(output_path, "wb") as out_f:
                writer = IncrementalPdfFileWriter(orig_f, strict=False)
                pdf_signer.sign_pdf(writer, output=out_f)

            if self.window: 
                self.window.show_toast(
                    self._("sign_success_message").format(os.path.basename(output_path)), 
                    self._("open"), 
                    lambda: self.open_file_path(output_path, show_toast=False)
                )
        except Exception as e:
            if self.window: self.window.show_toast(self._("sig_error_message").format(e))
            import traceback
            traceback.print_exc()
        
    def on_about_clicked(self, action, param):
        dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        dialog.set_program_name("GnomeSign"); dialog.set_version("1.0"); dialog.set_comments(self._("sign_reason"))
        dialog.set_logo_icon_name("org.pepeg.GnomeSign"); dialog.set_website("https://github.com/ppgllrd/GNOME.Sign")
        dialog.set_authors(["Pepe Gallardo", "Gemini"]); dialog.present()
        
    def update_ui(self):
        can_sign = self.doc is not None and self.signature_rect is not None and self.active_cert_path is not None
        sign_action = self.lookup_action("sign")
        if sign_action: sign_action.set_enabled(can_sign)
        if self.window: self.window.update_ui(self)

    def reset_signature_state(self):
        self.signature_rect = None
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.is_dragging_rect = False
        self.highlight_rect = None
        if self.window: self.window.sign_button.set_sensitive(False)

    def display_page(self, page_num, keep_sidebar_view=False):
        if self.highlight_rect:
            self.highlight_rect = None
        if not self.doc or not (0 <= page_num < len(self.doc)):
            self.page, self.doc, self.current_file_path, self.display_pixbuf = None, None, None, None
            self.signatures = []
        else:
            self.current_page = page_num; self.page = self.doc.load_page(page_num); self.display_pixbuf = None
        if self.window:
            self.window.update_header_bar_state(self)
            self.window.drawing_area.queue_draw()
            GLib.idle_add(self.window.adjust_scroll_and_viewport)
            if not keep_sidebar_view:
                self.window.sidebar.select_page(page_num)
    
    def on_prev_page_clicked(self, button):
        if self.doc and self.current_page > 0:
            self.reset_signature_state(); self.display_page(self.current_page - 1); self.update_ui()
    
    def on_next_page_clicked(self, button):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.reset_signature_state(); self.display_page(self.current_page + 1); self.update_ui()
            
    def on_jump_to_page_clicked(self, button):
        if not self.doc: return
        dialog = Gtk.Dialog(title=self._("jump_to_page_title"), transient_for=self.window, modal=True)
        dialog.add_buttons(self._("cancel"), Gtk.ResponseType.CANCEL, self._("accept"), Gtk.ResponseType.OK)
        content_area = dialog.get_content_area(); content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
        content_area.append(Gtk.Label(label=self._("jump_to_page_prompt").format(len(self.doc))))
        adj = Gtk.Adjustment(value=self.current_page + 1, lower=1, upper=len(self.doc), step_increment=1)
        spin = Gtk.SpinButton(adjustment=adj, numeric=True); content_area.append(spin)
        dialog.set_default_widget(spin); spin.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        def on_response(d, res):
            if res == Gtk.ResponseType.OK:
                self.reset_signature_state(); self.display_page(spin.get_value_as_int() - 1); self.update_ui()
            d.destroy()
        dialog.connect("response", on_response); dialog.present()

    def on_drag_begin(self, gesture, start_x, start_y):
        self.highlight_rect = None
        if self.signature_rect:
            x, y, w, h = self.signature_rect
            if x <= start_x <= x + w and y <= start_y <= y + h:
                self.is_dragging_rect, self.drag_offset_x, self.drag_offset_y = True, start_x - x, start_y - y; return
        self.is_dragging_rect, self.start_x, self.start_y = False, start_x, start_y
        self.end_x, self.end_y = start_x, start_y; self.signature_rect = None
        self.update_ui()
        self.window.drawing_area.queue_draw()

    def on_drag_update(self, gesture, offset_x, offset_y):
        success, start_point_x, start_point_y = gesture.get_start_point()
        if not success: return
        current_x, current_y = start_point_x + offset_x, start_point_y + offset_y
        if self.is_dragging_rect:
            _, _, w, h = self.signature_rect
            self.signature_rect = (current_x - self.drag_offset_x, current_y - self.drag_offset_y, w, h)
        else: self.end_x, self.end_y = current_x, current_y
        if self.window: self.window.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if not self.is_dragging_rect:
            x1, y1 = min(self.start_x, self.end_x), min(self.start_y, self.end_y)
            width, height = abs(self.start_x - self.end_x), abs(self.start_y - self.end_y)
            self.signature_rect = (x1, y1, width, height) if width > 5 and height > 5 else None
        self.is_dragging_rect = False
        self.update_ui()
        if self.window: self.window.drawing_area.queue_draw()

    def get_parsed_stamp_text(self, certificate, override_template=None):
        """Parses a signature template, replacing placeholders with actual certificate data."""
        if override_template is not None:
            template = override_template
        else:
            template_obj = self.config.get_active_template()
            if not template_obj:
                return "Error: No active signature template found."
            template = template_obj.get(f"template_{self.i18n.get_language()}", template_obj.get("template_en", ""))

        def get_cn(name):
            """This is the original, working method to get the Common Name."""
            try:
                return name.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            except (IndexError, AttributeError):
                # This fallback is for certificates that might not have a CN.
                return str(name)

        text = template.replace("$$SUBJECTCN$$", get_cn(certificate.subject))\
                       .replace("$$ISSUERCN$$", get_cn(certificate.issuer))\
                       .replace("$$CERTSERIAL$$", str(certificate.serial_number))
        
        date_match = re.search(r'\$\$SIGNDATE=(.*?)\$\$', text)
        if date_match:
            format_pattern = date_match.group(1).replace("dd", "%d").replace("MM", "%m").replace("yyyy", "%Y").replace("yy", "%y").replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
            text = text.replace(date_match.group(0), datetime.now().strftime(format_pattern))
        return text

if __name__ == "__main__":
    app = GnomeSign()
    sys.exit(app.run(sys.argv))