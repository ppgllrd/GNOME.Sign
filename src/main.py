# gnomesign.py

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
from ui.stamp_editor_dialog import StampEditorDialog
from ui.dialogs import create_password_dialog, create_about_dialog, show_error_dialog
from stamp_creator import HtmlStamp, pango_to_html
from pyhanko.stamp import StaticStampStyle

class SignatureDetails:
    """A data class to hold processed information about a digital signature."""
    def __init__(self, pyhanko_sig, validation_status, page_num, rect):
        """Initializes the signature details from pyHanko objects."""
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
        except (KeyError, AttributeError, IndexError, TypeError):
            # This is not a critical error, just a missing attribute.
            pass
        if not self.sign_time and validation_status.timestamp_validity:
            self.sign_time = validation_status.timestamp_validity.timestamp

class GnomeSign(Adw.Application):
    """The main application class, managing state and high-level logic."""
    __gsignals__ = {
        'language-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'certificates-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'document-changed': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
        'page-changed': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_INT, GObject.TYPE_INT, GObject.TYPE_BOOLEAN)),
        'signature-state-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'signatures-found': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
        'toast-request': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_PYOBJECT)),
        'highlight-rect-changed': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        """Initializes the application."""
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
        self.window, self.preferences_window = None, None
        self.signatures = []
    
    def _(self, key):
        """A shorthand for the translation function."""
        return self.i18n._(key)
    
    def do_startup(self):
        """Called when the application is starting up."""
        Adw.Application.do_startup(self)
        self.config.load()
        self.i18n.set_language(self.config.get_language())
        self.cert_manager.set_cert_paths(self.config.get_cert_paths())
        self._build_actions()
        self.active_cert_path = self.config.get_active_cert_path()
        from ui.app_window import AppWindow
        self.window = AppWindow(application=self)
        self.window.sidebar.connect("signature-selected", self.on_signature_selected)
        self.window.connect("close-request", self._on_window_close_request)
        self.connect("shutdown", self._on_shutdown)

    def _on_window_close_request(self, window):
        """Handles the main window close request."""
        self.quit()
        return True

    def _on_shutdown(self, app):
        """Saves the configuration when the application is shutting down."""
        self.config.save()
    
    def do_activate(self):
        """Called when the application is activated (e.g., launched from the desktop)."""
        self.window.present()
    
    def do_open(self, files, n_files, hint):
        """Handles opening files passed as arguments to the application."""
        if n_files > 0 and files[0].get_path():
            self.open_file_path(files[0].get_path())
        self.do_activate()
    
    def _build_actions(self):
        """Creates and adds application-wide actions."""
        actions_with_params = [("open_recent", self.on_open_recent_clicked, "s"), ("change_lang", self.on_lang_change_state, 's', self.i18n.get_language())]
        for name, callback, p_type, *state in actions_with_params:
            action = Gio.SimpleAction.new_stateful(name, GLib.VariantType(p_type), GLib.Variant(p_type, state[0])) if state else Gio.SimpleAction.new(name, GLib.VariantType(p_type))
            if state: action.connect("change-state", callback)
            else: action.connect("activate", callback)
            self.add_action(action)

        sign_action = Gio.SimpleAction.new("sign", None)
        sign_action.connect("activate", self.on_sign_document_clicked)
        sign_action.set_enabled(False) 
        self.add_action(sign_action)
        
        simple_actions = [
            ("open", self.on_open_pdf_clicked), 
            ("preferences", self.on_preferences_clicked), ("manage_certs", self.on_preferences_clicked), 
            ("about", self.on_about_clicked), ("edit_stamps", self.on_edit_stamps_clicked),
            ("show_signatures", self.on_show_signatures_clicked)
        ]
        for name, callback in simple_actions:
            action = Gio.SimpleAction.new(name, None); action.connect("activate", callback); self.add_action(action)

    def open_file_path(self, file_path, show_toast=True):
        """Opens a PDF document, analyzes it for signatures, and updates the application state."""
        try:
            if not os.path.exists(file_path): raise FileNotFoundError(f"File not found: {file_path}")
            if self.doc: self.doc.close()
            
            self.signatures = []
            try:
                with open(file_path, 'rb') as f:
                    reader = PdfFileReader(f, strict=False)
                    validation_context = ValidationContext(allow_fetching=True) 
                    pages = list(reader.root['/Pages']['/Kids'])
                    for sig in reader.embedded_signatures:
                        try:
                            page_ref = sig.sig_field.get('/P')
                            page_num = pages.index(page_ref)
                            rect = [float(v) for v in sig.sig_field.get('/Rect', [])]
                            status = validate_pdf_signature(sig, validation_context, skip_diff=True)
                            self.signatures.append(SignatureDetails(sig, status, page_num, rect))
                        except (ValueError, KeyError, IndexError):
                            status = validate_pdf_signature(sig, validation_context, skip_diff=True)
                            self.signatures.append(SignatureDetails(sig, status, -1, None))
            except Exception as e:
                # This is not a critical failure; the PDF might just not be analyzable.
                print(f"Could not analyze for signatures: {e}")

            self.current_file_path = file_path; self.doc = fitz.open(file_path); self.current_page = 0
            self.config.add_recent_file(file_path); self.config.set_last_folder(os.path.dirname(file_path))
            
            self.emit("document-changed", self.doc)
            if self.signatures: self.emit("signatures-found", self.signatures)
            elif self.active_cert_path and show_toast: self.emit("toast-request", self._("toast_select_area"), None, None)

            self.reset_signature_state(); self.display_page(0)
            
        except Exception as e:
            show_error_dialog(self.window, self._("error"), self._("open_pdf_error").format(e))
            self.doc = None; self.signatures = []
            self.emit("document-changed", None)

    def on_show_signatures_clicked(self, action, param):
        """Focuses the sidebar on the list of existing signatures."""
        if self.window:
            if not self.window.flap.get_reveal_flap(): self.window.flap.set_reveal_flap(True)
            self.window.hide_signature_info()
            self.window.sidebar.focus_on_signatures()
            
    def on_signature_selected(self, sidebar, sig_details):
        """Shows details for a selected signature."""
        if self.window:
            self.window.hide_signature_info()
        if self.window:
            if not self.window.flap.get_reveal_flap():
                self.window.flap.set_reveal_flap(True)
            self.window.sidebar.select_signature(sig_details)    
        if sig_details.page_num != -1:
            self.display_page(sig_details.page_num, keep_sidebar_view=True)
            if sig_details.rect:
                self.highlight_rect = sig_details.rect
                self.emit("highlight-rect-changed", self.highlight_rect)
                if self.window:
                    self.window.scroll_to_rect(sig_details.rect)
        
        dialog = Adw.MessageDialog.new(self.window,
                                       heading=self._("sig_details_title"),
                                       body="") 

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
            f"\n<b>{self._('signer')}:</b> {signer_esc}",
            f"<b>{self._('sign_date')}:</b> {sig_details.sign_time.strftime('%Y-%m-%d %H:%M:%S %Z') if sig_details.sign_time else 'N/A'}"
        ]
        
        if sig_details.reason:
            details_parts.append(f"<b>{self._('signature_reason_label')}:</b> {GLib.markup_escape_text(sig_details.reason)}")

        if sig_details.location:
            details_parts.append(f"<b>{self._('signature_location_label')}:</b> {GLib.markup_escape_text(sig_details.location)}")
            
        if sig_details.contact_info:
            details_parts.append(f"<b>{self._('signature_contact_label')}:</b> {GLib.markup_escape_text(sig_details.contact_info)}")

        details_parts.extend([
            f"\n<b>{self._('issuer')}:</b> {issuer_esc}",
            f"<b>{self._('serial')}:</b> {serial_esc}"
        ])
        
        details_text = "\n".join(details_parts)
        
        body_label = Gtk.Label(
            use_markup=True,
            label=details_text,
            wrap=True,
            xalign=0, 
            selectable=True,
            justify=Gtk.Justification.CENTER
        )
        
        dialog.set_extra_child(body_label)
        
        dialog.add_response("ok", self._("accept"))
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        
        dialog.present()

    def on_open_pdf_clicked(self, action, param):
        """Handles the 'Open' action, showing a file chooser."""
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                if file := dialog.get_file(): self.open_file_path(file.get_path())
        file_chooser = Gtk.FileChooserNative.new(self._("open_pdf_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_pdf = Gtk.FileFilter(); filter_pdf.set_name(self._("pdf_files")); filter_pdf.add_mime_type("application/pdf")
        file_chooser.add_filter(filter_pdf)
        if os.path.isdir(last_folder := self.config.get_last_folder()):
            file_chooser.set_current_folder(Gio.File.new_for_path(last_folder))
        file_chooser.connect("response", on_response); file_chooser.show()

    def on_open_recent_clicked(self, action, param):
        """Handles opening a file from the 'Open Recent' menu."""
        file_path = param.get_string()
        if os.path.exists(file_path): self.open_file_path(file_path)
        else:
            self.emit("toast-request", f"File not found: {file_path}", None, None)
            self.config.remove_recent_file(file_path); self.emit("language-changed")

    def on_preferences_clicked(self, action, param):
        """Shows the preferences window."""
        if self.preferences_window and self.preferences_window.is_visible():
            self.preferences_window.present()
            return
        from ui.preferences_window import PreferencesWindow
        page_name = 'certificates' if action.get_name() == 'manage_certs' else None
        self.preferences_window = PreferencesWindow(application=self, initial_page_name=page_name)
        self.preferences_window.connect("destroy", lambda w: self.config.save())
        self.preferences_window.present()

    def on_edit_stamps_clicked(self, action, param):
        """Shows the stamp editor dialog."""
        from ui.stamp_editor_dialog import StampEditorDialog
        dialog = StampEditorDialog(parent_window=self.window, app=self)
        dialog.connect("destroy", lambda w: self.config.save())
        dialog.present()
    
    def on_lang_change_state(self, action, value):
        """Handles changing the application language."""
        new_lang = value.get_string()
        if action.get_state().get_string() != new_lang:
            action.set_state(value); self.i18n.set_language(new_lang)
            self.config.set_language(new_lang); self.emit('language-changed')

    def on_sign_document_clicked(self, action=None, param=None):
        """Handles the main 'Sign Document' action."""
        if not self.active_cert_path:
            self.emit("toast-request", self._("no_cert_selected_error"), None, None); return
        if not all([self.doc, self.signature_rect, self.current_file_path]):
            self.emit("toast-request", self._("need_pdf_and_area"), None, None); return
        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": self.active_cert_path}, None)
        if not password:
            show_error_dialog(self.window, self._("error"), self._("credential_load_error"))
            return
        
        private_key_pyca, certificate_pyca = self.cert_manager.get_credentials(self.active_cert_path, password)
        if not (private_key_pyca and certificate_pyca):
            show_error_dialog(self.window, self._("error"), self._("credential_load_error"))
            return

        try:
            # The signing process itself
            output_path = self._perform_signing(private_key_pyca, certificate_pyca)
            
            # Show success toast
            self.emit("toast-request", self._("sign_success_message").format(os.path.basename(output_path)), self._("open"), lambda: self.open_file_path(output_path, show_toast=False))
        except Exception as e:
            show_error_dialog(self.window, self._("sig_error_title"), self._("sig_error_message").format(e))
            import traceback; traceback.print_exc()

    def _perform_signing(self, private_key_pyca, certificate_pyca):
        """Encapsulates the pyHanko signing logic."""
        signing_key_asn1 = translate_pyca_cryptography_key_to_asn1(private_key_pyca)
        signer_cert_asn1 = translate_pyca_cryptography_cert_to_asn1(certificate_pyca)
        
        output_path = self.current_file_path.replace(".pdf", "-signed.pdf"); version = 1
        while os.path.exists(output_path):
            output_path = f"{os.path.splitext(self.current_file_path)[0]}-signed-{version}.pdf"; version += 1
        
        signer = signers.SimpleSigner(signing_cert=signer_cert_asn1, signing_key=signing_key_asn1, cert_registry=SimpleCertificateStore.from_certs([signer_cert_asn1]))
        x, y, w, h = self.signature_rect
        view_width = self.window.drawing_area.get_width()
        scale = self.page.rect.width / view_width if view_width > 0 else 1
        fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
        parsed_pango_text = self.get_parsed_stamp_text(certificate_pyca)
        html_content = pango_to_html(parsed_pango_text)
        stamp_creator = HtmlStamp(html_content=html_content, width=fitz_rect.width, height=fitz_rect.height)
        
        meta = PdfSignatureMetadata(
            field_name=f'Signature-{int(datetime.now().timestamp() * 1000)}',
            reason=self.config.get_signature_reason() or None,
            location=self.config.get_signature_location() or None
        )
        
        pdf_box_y0 = self.page.rect.height - fitz_rect.y1
        pdf_box_y1 = self.page.rect.height - fitz_rect.y0
        new_field_spec = fields.SigFieldSpec(sig_field_name=meta.field_name, on_page=self.current_page, box=(fitz_rect.x0, pdf_box_y0, fitz_rect.x1, pdf_box_y1))
        
        pdf_signer = PdfSigner(meta, signer, stamp_style=stamp_creator.get_style(), new_field_spec=new_field_spec)
        
        with open(self.current_file_path, "rb") as orig_f, open(output_path, "wb") as out_f:
            writer = IncrementalPdfFileWriter(orig_f, strict=False)
            pdf_signer.sign_pdf(writer, output=out_f)
            
        return output_path

    def on_about_clicked(self, action, param):
        """Shows the 'About' dialog."""
        create_about_dialog(self.window, self._)
        
    def _update_sign_action_state(self):
        """Centralized method to update the enabled state of the sign action."""
        can_sign = self.doc is not None and self.signature_rect is not None and self.active_cert_path is not None
        sign_action = self.lookup_action("sign")
        if sign_action:
            sign_action.set_enabled(can_sign)
    
    def reset_signature_state(self):
        """Resets all properties related to the current signature drawing/selection."""
        self.signature_rect = None
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.is_dragging_rect = False
        self.highlight_rect = None
        self.emit("signature-state-changed")
        self._update_sign_action_state()

    def display_page(self, page_num, keep_sidebar_view=False):
        """Loads and displays a specific page of the current document."""
        if self.highlight_rect:
            self.highlight_rect = None
            self.emit("highlight-rect-changed", None)
        if not self.doc or not (0 <= page_num < len(self.doc)):
            self.page = None; self.doc = None; self.current_file_path = None; self.display_pixbuf = None; self.signatures = []
            self.emit("document-changed", None)
        else:
            self.current_page = page_num
            self.page = self.doc.load_page(page_num)
            self.display_pixbuf = None
            self.emit("page-changed", self.page, self.current_page, len(self.doc), keep_sidebar_view)
    
    def on_prev_page_clicked(self, button):
        """Navigates to the previous page."""
        if self.doc and self.current_page > 0:
            self.reset_signature_state(); self.display_page(self.current_page - 1)
    
    def on_next_page_clicked(self, button):
        """Navigates to the next page."""
        if self.doc and self.current_page < len(self.doc) - 1:
            self.reset_signature_state(); self.display_page(self.current_page + 1)
            
    def on_jump_to_page_clicked(self, button):
        """Shows a dialog to jump to a specific page."""
        if not self.doc: return
        # This can be refactored into ui/dialogs.py if needed, but is simple enough here.
        dialog = Gtk.Dialog(title=self._("jump_to_page_title"), transient_for=self.window, modal=True)
        dialog.add_buttons(self._("cancel"), Gtk.ResponseType.CANCEL, self._("accept"), Gtk.ResponseType.OK)
        content_area = dialog.get_content_area(); content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
        content_area.append(Gtk.Label(label=self._("jump_to_page_prompt").format(len(self.doc))))
        adj = Gtk.Adjustment(value=self.current_page + 1, lower=1, upper=len(self.doc), step_increment=1)
        spin = Gtk.SpinButton(adjustment=adj, numeric=True); content_area.append(spin)
        dialog.set_default_widget(spin); spin.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        def on_response(d, res):
            if res == Gtk.ResponseType.OK:
                self.reset_signature_state(); self.display_page(spin.get_value_as_int() - 1)
            d.destroy()
        dialog.connect("response", on_response); dialog.present()

    def on_drag_begin(self, gesture, start_x, start_y):
        """Handles the beginning of a drag gesture on the document view."""
        self.highlight_rect = None; self.emit("highlight-rect-changed", None)
        if self.signature_rect:
            x, y, w, h = self.signature_rect
            if x <= start_x <= x + w and y <= start_y <= y + h:
                self.is_dragging_rect, self.drag_offset_x, self.drag_offset_y = True, start_x - x, start_y - y; return
        self.is_dragging_rect, self.start_x, self.start_y = False, start_x, start_y
        self.end_x, self.end_y = start_x, start_y; self.signature_rect = None
        self.emit("signature-state-changed")

    def on_drag_update(self, gesture, offset_x, offset_y):
        """Handles the update of a drag gesture."""
        success, start_point_x, start_point_y = gesture.get_start_point()
        if not success: return
        current_x, current_y = start_point_x + offset_x, start_point_y + offset_y
        if self.is_dragging_rect:
            _, _, w, h = self.signature_rect
            self.signature_rect = (current_x - self.drag_offset_x, current_y - self.drag_offset_y, w, h)
        else: self.end_x, self.end_y = current_x, current_y
        self.emit("signature-state-changed")

    def on_drag_end(self, gesture, offset_x, offset_y):
        """Handles the end of a drag gesture, finalizing the signature rectangle."""
        if not self.is_dragging_rect:
            x1, y1 = min(self.start_x, self.end_x), min(self.start_y, self.end_y)
            width, height = abs(self.start_x - self.end_x), abs(self.start_y - self.end_y)
            self.signature_rect = (x1, y1, width, height) if width > 5 and height > 5 else None
        self.is_dragging_rect = False
        self.emit("signature-state-changed")
        self._update_sign_action_state()

    def get_parsed_stamp_text(self, certificate, override_template=None):
        """Parses a signature template, replacing placeholders with actual certificate data."""
        if override_template is not None:
            template_text = override_template
        else:
            template_obj = self.config.get_active_template()
            if not template_obj: return "Error: No active signature template found."
            template_text = template_obj.get("template", template_obj.get("template_es", ""))

        def get_cn(name):
            try: return name.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            except (IndexError, AttributeError): return str(name)

        text = template_text.replace("$$SUBJECTCN$$", get_cn(certificate.subject))\
                           .replace("$$ISSUERCN$$", get_cn(certificate.issuer))\
                           .replace("$$CERTSERIAL$$", str(certificate.serial_number))
        
        if date_match := re.search(r'\$\$SIGNDATE=(.*?)\$\$', text):
            format_pattern = date_match.group(1).replace("dd", "%d").replace("MM", "%m").replace("yyyy", "%Y").replace("yy", "%y").replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
            text = text.replace(date_match.group(0), datetime.now().strftime(format_pattern))
        return text

    def set_active_certificate(self, path):
        """Sets the active certificate, saves the config, and notifies the UI."""
        self.active_cert_path = path
        self.config.set_active_cert_path(path)
        self.emit("certificates-changed")
        self._update_sign_action_state()

    def add_certificate(self, pkcs12_path, password):
        """Adds a new certificate, saves it, and notifies the UI."""
        common_name = self.cert_manager.test_certificate(pkcs12_path, password)
        if common_name:
            Secret.password_store_sync(KEYRING_SCHEMA, {"path": pkcs12_path}, Secret.COLLECTION_DEFAULT, f"Certificate password for {common_name}", password, None)
            self.config.add_cert_path(pkcs12_path)
            self.config.set_last_folder(os.path.dirname(pkcs12_path))
            self.cert_manager.add_cert_path(pkcs12_path)
            self.set_active_certificate(pkcs12_path)
            self.config.save() # Save immediately after a successful addition
            return True
        else:
            show_error_dialog(self.window, self._("error"), self._("bad_password_or_file"))
            return False

    def remove_certificate(self, path):
        """Removes a certificate and notifies the UI."""
        self.cert_manager.remove_credentials_from_keyring(path)
        self.config.remove_cert_path(path)
        self.cert_manager.remove_cert_path(path)

        if self.active_cert_path == path:
            certs = self.cert_manager.get_all_certificate_details()
            new_path = certs[0]['path'] if certs else None
            self.set_active_certificate(new_path)
        else:
            self.emit("certificates-changed")
        
        self.config.save() # Save immediately after a removal

    def request_add_new_certificate(self):
        """Manages the full flow of adding a new certificate."""
        def on_file_chooser_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                if file := dialog.get_file():
                    pkcs12_path = file.get_path()
                    
                    def on_password_response(password):
                        if password is not None:
                            self.add_certificate(pkcs12_path, password)
                    
                    create_password_dialog(self.window, self._("password"), os.path.basename(pkcs12_path), self._, on_password_response)

        file_chooser = Gtk.FileChooserNative.new(self._("open_cert_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_p12 = Gtk.FileFilter()
        filter_p12.set_name(self._("p12_files"))
        filter_p12.add_pattern("*.p12"); filter_p12.add_pattern("*.pfx")
        file_chooser.add_filter(filter_p12)
        file_chooser.connect("response", on_file_chooser_response)
        file_chooser.show()

if __name__ == "__main__":
    app = GnomeSign()
    sys.exit(app.run(sys.argv))