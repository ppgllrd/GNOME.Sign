import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Secret", "1")
from gi.repository import Gtk, Adw, Gio, Secret, GLib, Pango, GObject
import fitz, os, sys, shutil, re
from datetime import datetime
from html.parser import HTMLParser
from i18n import I18NManager
from certificate_manager import CertificateManager, KEYRING_SCHEMA
from config_manager import ConfigManager
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfSigner, PdfSignatureMetadata
from pyhanko.keys.internal import translate_pyca_cryptography_key_to_asn1, translate_pyca_cryptography_cert_to_asn1
from pyhanko_certvalidator.registry import SimpleCertificateStore
from cryptography import x509
from ui.dialogs import create_stamp_editor_dialog


class PangoToHtmlConverter(HTMLParser):
    """A simple parser to convert Pango markup to basic HTML with inline styles."""
    def __init__(self):
        """Initializes the converter."""
        super().__init__(); self.html_parts = []; self.style_stack = [{}]

    def get_current_styles(self):
        """Returns the current dictionary of CSS styles."""
        return self.style_stack[-1]

    def handle_starttag(self, tag, attrs):
        """Handles a start tag, updating the style stack."""
        new_styles = self.get_current_styles().copy(); attrs_dict = dict(attrs)
        if tag == 'b': new_styles['font-weight'] = 'bold'
        elif tag == 'i': new_styles['font-style'] = 'italic'
        elif tag == 'span':
            if 'font_family' in attrs_dict: new_styles['font-family'] = f"'{attrs_dict['font_family']}'"
            if 'color' in attrs_dict: new_styles['color'] = attrs_dict['color']
            if 'size' in attrs_dict:
                try: css_size = int(attrs_dict['size']) / Pango.SCALE; new_styles['font-size'] = f'{css_size:.1f}pt'
                except (ValueError, TypeError): pass
        self.style_stack.append(new_styles)

    def handle_endtag(self, tag):
        """Handles an end tag, popping from the style stack."""
        if len(self.style_stack) > 1: self.style_stack.pop()

    def handle_data(self, data):
        """Handles text data, wrapping it in a span with the current styles."""
        if not data: return
        styles = self.get_current_styles(); style_str = "; ".join(f"{k}: {v}" for k, v in styles.items() if v)
        escaped_data = GLib.markup_escape_text(data)
        if style_str: self.html_parts.append(f'<span style="{style_str}">{escaped_data}</span>')
        else: self.html_parts.append(escaped_data)

    def get_html(self):
        """Returns the final, converted HTML string."""
        return "".join(self.html_parts)

class GnomeSign(Adw.Application):
    """The main application class, handling state, actions, and core logic."""
    __gsignals__ = {
        'language-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'certificates-changed': (GObject.SignalFlags.RUN_FIRST, None, ()) # <-- AÑADIR ESTA LÍNEA
    }

    def __init__(self):
        """Initializes the main application class and its state variables."""
        super().__init__(application_id="org.pepeg.GnomeSign", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = ConfigManager()
        self.i18n = I18NManager()
        self.cert_manager = CertificateManager()
        self.doc, self.current_page, self.active_cert_path = None, 0, None
        self.page, self.display_pixbuf, self.current_file_path = None, None, None
        self.signature_rect, self.is_dragging_rect = None, False
        self.drag_offset_x, self.drag_offset_y = 0, 0
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.window, self.stamp_editor_window, self.preferences_window = None, None, None
        self.signatures = []

    def _(self, key):
        """Shortcut for the i18n translation function."""
        return self.i18n._(key)

    def do_startup(self):
        """Performs application startup tasks like loading config, setting up i18n, and building actions."""
        Adw.Application.do_startup(self)
        self.config.load()
        self.i18n.set_language(self.config.get_language())
        self.cert_manager.set_cert_paths(self.config.get_cert_paths())
        self._build_actions()
        self.active_cert_path = self.config.get_active_cert_path()
        from ui.app_window import AppWindow
        self.window = AppWindow(application=self)
        self.connect("certificates-changed", self.on_certificates_changed) 

        def on_window_close_request(window):
            """
            This handler is connected to the 'close-request' signal.
            It's the earliest and most reliable point to intercept the user
            closing the window.
            """
            self.quit()
            return True

        self.window.connect("close-request", on_window_close_request)

    def on_certificates_changed(self, app): 
        """Handles the 'certificates-changed' signal by updating the main UI."""
        self.update_ui()
        
    def do_activate(self):
        """Activates the application by presenting the main window."""
        self.window.present()
        self.update_ui()
    
    def do_open(self, files, n_files, hint):
        """Handles opening files from the command line or file manager."""
        if n_files > 0 and files[0].get_path(): self.open_file_path(files[0].get_path())
        self.do_activate()

    def _build_actions(self):
        """Creates and registers all Gio.SimpleAction for the application."""
        actions_with_params = [("open_recent", self.on_open_recent_clicked, "s"), ("change_lang", self.on_lang_change_state, 's', self.i18n.get_language())]
        for name, callback, p_type, *state in actions_with_params:
            action = Gio.SimpleAction.new_stateful(name, GLib.VariantType(p_type), GLib.Variant(p_type, state[0])) if state else Gio.SimpleAction.new(name, GLib.VariantType(p_type))
            if state: action.connect("change-state", callback)
            else: action.connect("activate", callback)
            self.add_action(action)
        simple_actions = [("open", self.on_open_pdf_clicked), ("sign", self.on_sign_document_clicked), ("preferences", self.on_preferences_clicked), ("manage_certs", self.on_preferences_clicked), ("about", self.on_about_clicked), ("edit_stamps", self.on_edit_stamps_clicked)]
        for name, callback in simple_actions:
            action = Gio.SimpleAction.new(name, None); action.connect("activate", callback); self.add_action(action)

    def open_file_path(self, file_path, show_toast=True):
        """Opens a PDF document from a given file path, updating the application state."""
        try:
            if not os.path.exists(file_path): raise FileNotFoundError(f"File not found: {file_path}")
            if self.doc: self.doc.close()
            self.signatures = []
            self.current_file_path = file_path; self.doc = fitz.open(file_path); self.current_page = 0
            self.config.add_recent_file(file_path); self.config.set_last_folder(os.path.dirname(file_path)); self.config.save()
            self.reset_signature_state(); self.display_page(self.current_page)
            if self.window: self.window.sidebar.populate(self.doc, self.signatures)
            self.update_ui()

            if self.window and self.active_cert_path and show_toast:
                self.window.show_toast(self._("toast_select_area"), timeout=4)

        except Exception as e:
            if self.window: self.window.show_toast(self._("open_pdf_error").format(e))
            self.doc = None; self.signatures = []; self.update_ui()

    def on_open_pdf_clicked(self, action, param):
        """Handles the 'open' action, showing a file chooser dialog."""
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file: self.open_file_path(file.get_path())
        
        # Use Gtk.FileChooserNative for better desktop integration
        file_chooser = Gtk.FileChooserNative.new(
            self._("open_pdf_dialog_title"), # title
            self.window,                     # transient_for (parent)
            Gtk.FileChooserAction.OPEN,      # action
            self._("open"),                  # accept_label
            self._("cancel")                 # cancel_label
        )

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
        """Handles the 'open_recent' action, opening a file from the recent list."""
        file_path = param.get_string()
        if os.path.exists(file_path): self.open_file_path(file_path)
        else:
            if self.window: self.window.show_toast(f"File not found: {file_path}")
            self.config.remove_recent_file(file_path); self.config.save(); self.update_ui()
    
    def on_preferences_clicked(self, action, param):
        """
        Handles the 'preferences' and 'manage_certs' actions by creating 
        and showing a new preferences window, optionally on a specific page.
        """
        if self.preferences_window:
            self.preferences_window.present()
            return

        # Determine which page to open based on the action name
        page_name = None
        if action.get_name() == 'manage_certs':
            page_name = 'certificates'
            
        from ui.preferences_window import PreferencesWindow
        
        # Pass the target page name to the constructor
        self.preferences_window = PreferencesWindow(application=self, transient_for=self.window, initial_page_name=page_name)
        self.preferences_window.connect("destroy", self.on_preferences_window_destroyed)
        self.preferences_window.present()

    def on_preferences_window_destroyed(self, widget): # <-- 3. AÑADIR ESTE NUEVO MÉTODO
        """
        Callback for when the preferences window is destroyed.
        It resets our reference to None, allowing a new window to be created next time.
        """
        self.preferences_window = None

    def on_edit_stamps_clicked(self, action, param):
        """Handles the 'edit_stamps' action by opening the stamp editor dialog."""
        # The dialog is modal and its lifecycle is managed within the function call.
        create_stamp_editor_dialog(self.window, self, self.config)
    
    def on_lang_change_state(self, action, value):
        """Handles the state change for the 'change_lang' action."""
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
        private_key, certificate = self.cert_manager.get_credentials(self.active_cert_path, password)
        if not (private_key and certificate):
            if self.window: self.window.show_toast(self._("credential_load_error")); return

        output_path = self.current_file_path.replace(".pdf", "-signed.pdf")
        version = 1
        while os.path.exists(output_path):
            output_path = f"{os.path.splitext(self.current_file_path)[0]}-signed-{version}.pdf"; version += 1
        shutil.copyfile(self.current_file_path, output_path)
        try:
            self._apply_visual_stamp(output_path, certificate)
            signer = signers.SimpleSigner(translate_pyca_cryptography_cert_to_asn1(certificate), translate_pyca_cryptography_key_to_asn1(private_key), SimpleCertificateStore())
            signer_cn = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            meta = PdfSignatureMetadata(field_name=f'Signature-{int(datetime.now().timestamp() * 1000)}', reason=self._("sign_reason"), name=signer_cn)
            pdf_signer = PdfSigner(meta, signer)
            with open(output_path, "rb+") as f:
                writer = IncrementalPdfFileWriter(f, strict=False)
                signed_bytes = pdf_signer.sign_pdf(writer)
                f.seek(0); f.write(signed_bytes.getbuffer()); f.truncate()
            
            if self.window: 
                self.window.show_toast(
                    self._("sign_success_message").format(os.path.basename(output_path)), 
                    self._("open"), 
                    lambda: self.open_file_path(output_path, show_toast=False)
                )
        except Exception as e:
            if self.window: self.window.show_toast(self._("sig_error_message").format(e))
            import traceback; traceback.print_exc()

    def on_about_clicked(self, action, param):
        """Handles the 'about' action, showing the application's about dialog."""
        dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        dialog.set_program_name("GnomeSign"); dialog.set_version("1.0"); dialog.set_comments(self._("sign_reason"))
        dialog.set_logo_icon_name("org.pepeg.GnomeSign"); dialog.set_website("https://github.com/ppgllrd/GNOME.Sign")
        dialog.set_authors(["Pepe Gallardo", "Gemini"]); dialog.present()
        
    def update_ui(self):
        """Updates the entire application UI, including the state of global actions."""
        can_sign = self.doc is not None and self.signature_rect is not None and self.active_cert_path is not None
        sign_action = self.lookup_action("sign")
        if sign_action:
            sign_action.set_enabled(can_sign)

        if self.window: self.window.update_ui(self)

    def reset_signature_state(self):
        """Resets all variables related to the signature rectangle selection."""
        self.signature_rect = None
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.is_dragging_rect = False
        if self.window: self.window.sign_button.set_sensitive(False)

    def display_page(self, page_num):
        """Loads and displays a specific page of the current document."""
        if not self.doc or not (0 <= page_num < len(self.doc)):
            self.page, self.doc, self.current_file_path, self.display_pixbuf = None, None, None, None
            self.signatures = []
        else:
            self.current_page = page_num; self.page = self.doc.load_page(page_num); self.display_pixbuf = None
        if self.window:
            self.window.update_header_bar_state(self)
            self.window.drawing_area.queue_draw()
            GLib.idle_add(self.window.adjust_scroll_and_viewport)
            self.window.sidebar.select_page(page_num)
    
    def on_prev_page_clicked(self, button):
        """Navigates to the previous page of the document."""
        if self.doc and self.current_page > 0:
            self.reset_signature_state(); self.display_page(self.current_page - 1); self.update_ui()
    
    def on_next_page_clicked(self, button):
        """Navigates to the next page of the document."""
        if self.doc and self.current_page < len(self.doc) - 1:
            self.reset_signature_state(); self.display_page(self.current_page + 1); self.update_ui()
            
    def on_jump_to_page_clicked(self, button):
        """Opens a dialog to jump to a specific page number."""
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
        """Handles the beginning of a drag gesture on the drawing area."""
        if self.signature_rect:
            x, y, w, h = self.signature_rect
            if x <= start_x <= x + w and y <= start_y <= y + h:
                self.is_dragging_rect, self.drag_offset_x, self.drag_offset_y = True, start_x - x, start_y - y; return
        self.is_dragging_rect, self.start_x, self.start_y = False, start_x, start_y
        self.end_x, self.end_y = start_x, start_y; self.signature_rect = None
        self.update_ui()

        self.window.drawing_area.queue_draw()

    def on_drag_update(self, gesture, offset_x, offset_y):
        """Handles the update of a drag gesture, resizing or moving the signature rectangle."""
        success, start_point_x, start_point_y = gesture.get_start_point()
        if not success: return
        current_x, current_y = start_point_x + offset_x, start_point_y + offset_y
        if self.is_dragging_rect:
            _, _, w, h = self.signature_rect
            self.signature_rect = (current_x - self.drag_offset_x, current_y - self.drag_offset_y, w, h)
        else: self.end_x, self.end_y = current_x, current_y
        if self.window: self.window.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        """Handles the end of a drag gesture, finalizing the signature rectangle."""
        if not self.is_dragging_rect:
            x1, y1 = min(self.start_x, self.end_x), min(self.start_y, self.end_y)
            width, height = abs(self.start_x - self.end_x), abs(self.start_y - self.end_y)
            self.signature_rect = (x1, y1, width, height) if width > 5 and height > 5 else None
        self.is_dragging_rect = False
        self.update_ui()
        if self.window:
            self.window.drawing_area.queue_draw()

    def get_parsed_stamp_text(self, certificate, override_template=None):
        """Parses a signature template, replacing placeholders with actual certificate data."""
        if override_template is not None: template = override_template
        else:
            template_obj = self.config.get_active_template()
            if not template_obj: return "Error: No active signature template found."
            template = template_obj.get(f"template_{self.i18n.get_language()}", template_obj.get("template_en", ""))
        def get_cn(name):
            try: return name.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            except (IndexError, AttributeError): return name.rfc4514_string()
        text = template.replace("$$SUBJECTCN$$", get_cn(certificate.subject)).replace("$$ISSUERCN$$", get_cn(certificate.issuer)).replace("$$CERTSERIAL$$", str(certificate.serial_number))
        date_match = re.search(r'\$\$SIGNDATE=(.*?)\$\$', text)
        if date_match:
            format_pattern = date_match.group(1).replace("dd", "%d").replace("MM", "%m").replace("yyyy", "%Y").replace("yy", "%y").replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
            text = text.replace(date_match.group(0), datetime.now().strftime(format_pattern))
        return text

    def _apply_visual_stamp(self, input_path, certificate):
        """Applies the visual signature (stamp) to the PDF document."""
        doc = fitz.open(input_path); page = doc.load_page(self.current_page)
        view_width = self.window.drawing_area.get_width()
        scale = page.rect.width / view_width if view_width > 0 else 1
        x, y, w, h = self.signature_rect
        fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
        parsed_pango_text = self.get_parsed_stamp_text(certificate)
        converter = PangoToHtmlConverter(); converter.feed(parsed_pango_text.replace('\n', '<br/>'))
        html_content = f"""<div style="width:100%;height:100%;display:table;text-align:center;line-height:1.2;"><div style="display:table-cell;vertical-align:middle;">{converter.get_html()}</div></div>"""
        page.insert_htmlbox(fitz_rect + (5, 5, -5, -5), html_content, rotate=0)
        doc.save(input_path, incremental=True, encryption=0); doc.close()

if __name__ == "__main__":
    app = GnomeSign()
    sys.exit(app.run(sys.argv))