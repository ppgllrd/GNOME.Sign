import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Secret", "1")
from gi.repository import Gtk, Gio, Secret, GLib
import fitz  # PyMuPDF
import os
import sys
import shutil
import re
from datetime import datetime

from i18n import I18NManager
from certificate_manager import CertificateManager, KEYRING_SCHEMA
from config_manager import ConfigManager
from ui.app_window import AppWindow
from ui.dialogs import (create_about_dialog, create_cert_selector_dialog, 
                        create_password_dialog, show_message_dialog,
                        create_jump_to_page_dialog, create_stamp_editor_dialog)

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfSigner, PdfSignatureMetadata
from pyhanko.keys.internal import translate_pyca_cryptography_key_to_asn1, translate_pyca_cryptography_cert_to_asn1
from pyhanko_certvalidator.registry import SimpleCertificateStore
from cryptography import x509

class GnomeSign(Gtk.Application):
    """
    The main application class. It manages the application lifecycle,
    state, and actions. It doesn't build the UI itself but delegates
    that to the AppWindow class.
    """
    def __init__(self):
        super().__init__(application_id="org.pepeg.GnomeSign", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config = ConfigManager()
        self.i18n = I18NManager()
        self.cert_manager = CertificateManager()
        self.doc, self.current_page, self.active_cert_path = None, 0, None
        self.page, self.display_pixbuf, self.current_file_path = None, None, None
        self.signature_rect, self.is_dragging_rect = None, False
        self.drag_offset_x, self.drag_offset_y = 0, 0
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1

    def _(self, key):
        return self.i18n._(key)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.config.load()
        self.i18n.set_language(self.config.get_language())
        self.cert_manager.set_cert_paths(self.config.get_cert_paths())
        self._build_actions()

    def do_activate(self):
        self.window = AppWindow(application=self)
        self.window.present()
        self.update_ui()
        
    def _build_actions(self):
        actions = [
            ("open", self.on_open_pdf_clicked),
            ("sign", self.on_sign_document_clicked),
            ("load_cert", self.on_load_certificate_clicked),
            ("select_cert", self.on_cert_button_clicked),
            ("change_lang", self.on_lang_button_clicked),
            ("about", lambda a, p: create_about_dialog(self.window, self._)),
            ("open_recent", self.on_open_recent_clicked, "s"),
            ("edit_stamps", self.on_edit_stamps_clicked),
        ]
        for name, callback, *param_type in actions:
            action = Gio.SimpleAction.new(name, GLib.VariantType(param_type[0]) if param_type else None)
            action.connect("activate", callback)
            self.add_action(action)

    def open_file_path(self, file_path):
        try:
            if self.doc: self.doc.close()
            self.current_file_path = file_path
            self.doc = fitz.open(file_path)
            self.current_page = 0
            self.config.add_recent_file(file_path)
            folder_path = os.path.dirname(file_path)
            self.config.set_last_folder(folder_path)
            self.config.save()
            self.reset_signature_state()
            self.display_page(self.current_page)
            self.update_ui()
        except Exception as e:
            show_message_dialog(self.window, self._("error"), self._("open_pdf_error").format(e), Gtk.MessageType.ERROR)

    def on_open_pdf_clicked(self, action, param):
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    self.open_file_path(file.get_path())
        
        file_chooser = Gtk.FileChooserNative.new(self._("open_pdf_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_pdf = Gtk.FileFilter(); filter_pdf.set_name(self._("pdf_files")); filter_pdf.add_mime_type("application/pdf")
        file_chooser.add_filter(filter_pdf)
        
        last_folder = self.config.get_last_folder()
        if os.path.isdir(last_folder):
            file_chooser.set_current_folder(Gio.File.new_for_path(last_folder))
            
        file_chooser.connect("response", on_response)
        file_chooser.show()

    def on_open_recent_clicked(self, action, param):
        file_path = param.get_string()
        if os.path.exists(file_path):
            self.open_file_path(file_path)
        else:
            show_message_dialog(self.window, self._("error"), f"File not found:\n{file_path}", Gtk.MessageType.ERROR)
            self.config.remove_recent_file(file_path)
            self.config.save()
            self.update_ui()
            
    def on_cert_button_clicked(self, action, param=None):
        cert_details = self.cert_manager.get_all_certificate_details()
        if not cert_details:
             show_message_dialog(self.window, self._("select_certificate"), self._("no_certificate_selected"), Gtk.MessageType.INFO)
             return
        create_cert_selector_dialog(self.window, self)

    def on_lang_button_clicked(self, action, param):
        current_lang = self.i18n.get_language()
        new_lang = "en" if current_lang == "es" else "es"
        self.i18n.set_language(new_lang)
        self.config.set_language(new_lang)
        self.update_ui()
        
    def on_edit_stamps_clicked(self, action, param):
        create_stamp_editor_dialog(self.window, self, self.config)

    def on_sign_document_clicked(self, action=None, param=None):
        if not all([self.doc, self.signature_rect, self.current_file_path, self.active_cert_path]):
            show_message_dialog(self.window, self._("error"), self._("need_pdf_and_area"), Gtk.MessageType.ERROR); return
        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": self.active_cert_path}, None)
        if not password:
            show_message_dialog(self.window, self._("error"), self._("credential_load_error"), Gtk.MessageType.ERROR); return
        private_key, certificate = self.cert_manager.get_credentials(self.active_cert_path, password)
        if not (private_key and certificate):
            show_message_dialog(self.window, self._("error"), self._("credential_load_error"), Gtk.MessageType.ERROR); return
        output_path = self.current_file_path.replace(".pdf", "-signed.pdf")     
        version = 1
        while os.path.exists(output_path):
            base = os.path.splitext(self.current_file_path)[0] + "-signed"
            output_path = f"{base}-{version}.pdf"
            version += 1
        shutil.copyfile(self.current_file_path, output_path)
        try:
            self._apply_visual_stamp(output_path, certificate)
            signer = signers.SimpleSigner(translate_pyca_cryptography_cert_to_asn1(certificate), translate_pyca_cryptography_key_to_asn1(private_key), SimpleCertificateStore())
            signer_cn = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            meta = PdfSignatureMetadata(field_name=f'Signature-{int(datetime.now().timestamp() * 1000)}', reason=self._("sign_reason"), name=signer_cn)
            pdf_signer = PdfSigner(meta, signer)
            with open(output_path, "rb+") as f:
                writer = IncrementalPdfFileWriter(f)                
                signed_bytes = pdf_signer.sign_pdf(writer)
                f.seek(0); f.write(signed_bytes.getbuffer()); f.truncate()
            self._ask_to_open_new_file(output_path)
        except Exception as e:
            show_message_dialog(self.window, self._("sig_error_title"), self._("sig_error_message").format(e), Gtk.MessageType.ERROR)
            import traceback; traceback.print_exc()

    def on_load_certificate_clicked(self, action, param):
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    self._process_certificate_selection(file.get_path())
        
        file_chooser = Gtk.FileChooserNative.new(self._("open_cert_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_p12 = Gtk.FileFilter(); filter_p12.set_name(self._("p12_files")); filter_p12.add_pattern("*.p12"); filter_p12.add_pattern("*.pfx")
        file_chooser.add_filter(filter_p12)

        last_folder = self.config.get_last_folder()
        if os.path.isdir(last_folder):
            file_chooser.set_current_folder(Gio.File.new_for_path(last_folder))
            
        file_chooser.connect("response", on_response)
        file_chooser.show()

    def update_ui(self):
        if hasattr(self, 'window'): self.window.update_ui(self)

    def reset_signature_state(self):
        self.signature_rect = None
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.is_dragging_rect = False
        if hasattr(self, 'window'): self.window.sign_button.set_sensitive(False)

    def display_page(self, page_num):
        is_doc_loaded = self.doc is not None
        if is_doc_loaded and 0 <= page_num < len(self.doc):
            self.page = self.doc.load_page(page_num)
            self.display_pixbuf = None
        else:
            self.page, self.doc, self.current_file_path, self.display_pixbuf = None, None, None, None
        
        if hasattr(self, 'window'):
            self.window.update_header_bar_state(self)
            self.window.drawing_area.queue_draw()
            GLib.idle_add(self.window.adjust_scroll_and_viewport)

    def on_prev_page_clicked(self, button):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.reset_signature_state()
            self.display_page(self.current_page)
            self.update_ui()
    
    def on_next_page_clicked(self, button):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.reset_signature_state()
            self.display_page(self.current_page)
            self.update_ui()
            
    def on_jump_to_page_clicked(self, button):
        if not self.doc: return
        def on_page_selected(page_num):
            if page_num is not None:
                self.current_page = page_num
                self.reset_signature_state()
                self.display_page(self.current_page)
                self.update_ui()
        create_jump_to_page_dialog(self.window, self._, self.current_page + 1, len(self.doc), on_page_selected)

    def on_drag_begin(self, gesture, start_x, start_y):
        if self.signature_rect:
            x, y, w, h = self.signature_rect
            if x <= start_x <= x + w and y <= start_y <= y + h:
                self.is_dragging_rect = True
                self.drag_offset_x, self.drag_offset_y = start_x - x, start_y - y
                return
        self.is_dragging_rect = False
        self.start_x, self.start_y = start_x, start_y
        self.end_x, self.end_y = start_x, start_y
        self.signature_rect = None
        self.window.sign_button.set_sensitive(False)
        self.window.drawing_area.queue_draw()

    def on_drag_update(self, gesture, offset_x, offset_y):
        success, start_point_x, start_point_y = gesture.get_start_point()
        if not success: return
        current_x, current_y = start_point_x + offset_x, start_point_y + offset_y
        if self.is_dragging_rect:
            _, _, w, h = self.signature_rect
            self.signature_rect = (current_x - self.drag_offset_x, current_y - self.drag_offset_y, w, h)
        else:
            self.end_x, self.end_y = current_x, current_y
        if hasattr(self, 'window'): self.window.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if not self.is_dragging_rect:
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            self.signature_rect = (x1, y1, abs(self.start_x - self.end_x), abs(self.start_y - self.end_y))
        self.is_dragging_rect = False
        if hasattr(self, 'window'):
            self.window.update_header_bar_state(self)
            self.window.drawing_area.queue_draw()

    def get_parsed_stamp_text(self, certificate, for_html=False, override_template=None):
        if override_template is not None:
            template = override_template
        else:
            template_obj = self.config.get_active_template()
            if not template_obj:
                return "Error: No active signature template found."
            template = template_obj.get(f"template_{self.i18n.get_language()}", template_obj.get("template_en", ""))
        
        def get_cn(name):
            try:
                return name.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            except (IndexError, AttributeError):
                return name.rfc4514_string()

        subject_cn = get_cn(certificate.subject)
        issuer_cn = get_cn(certificate.issuer)
        cert_serial = str(certificate.serial_number)
        
        text = template.replace("$$SUBJECTCN$$", subject_cn)
        text = text.replace("$$ISSUERCN$$", issuer_cn)
        text = text.replace("$$CERTSERIAL$$", cert_serial)

        date_match = re.search(r'\$\$SIGNDATE=(.*?)\$\$', text)
        if date_match:
            format_pattern = date_match.group(1)
            py_format = format_pattern.replace("dd", "%d").replace("MM", "%m").replace("yyyy", "%Y").replace("yy", "%y")
            py_format = py_format.replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
            formatted_date = datetime.now().strftime(py_format)
            text = text.replace(date_match.group(0), formatted_date)
        
        if for_html:
            text = text.replace("\n", "<br>")
            
        return text

    def _apply_visual_stamp(self, input_path, certificate):
        doc = fitz.open(input_path)
        page = doc.load_page(self.current_page)
        view_width = self.window.drawing_area.get_width()
        scale = page.rect.width / view_width if view_width > 0 else 1
        x, y, w, h = self.signature_rect
        fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)

        page.draw_rect(fitz_rect, color=None, fill=(1.0, 1.0, 1.0), fill_opacity=1.0, overlay=False)
        
        parsed_text_for_html = self.get_parsed_stamp_text(certificate, for_html=True)

        html_content = f"""
        <div style="width: 100%; height: 100%; display: table; text-align: center;">
            <div style="display: table-cell; vertical-align: middle; font-family: sans-serif; font-size: 8pt; line-height: 1.2;">
                {parsed_text_for_html}
            </div>
        </div>
        """
        html_rect = fitz_rect + (5, 5, -5, -5)
        page.insert_htmlbox(html_rect, html_content, rotate=0, css="b { font-size: 9pt; }")

        doc.save(input_path, incremental=True, encryption=0); doc.close()

    def _ask_to_open_new_file(self, file_path):
        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.YES:
                self.open_file_path(file_path)
            d.destroy()
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self._("sign_success_title"), secondary_text=self._("sign_success_message").format(file_path))
        dialog.connect("response", on_response); dialog.present()
    
    def _process_certificate_selection(self, pkcs12_path):
        def on_password_response(password):
            if password is not None:
                common_name = self.cert_manager.test_certificate(pkcs12_path, password)
                if common_name:
                    Secret.password_store_sync(KEYRING_SCHEMA, {"path": pkcs12_path}, Secret.COLLECTION_DEFAULT, f"Certificate password for {common_name}", password, None)
                    self.config.add_cert_path(pkcs12_path)
                    self.config.set_last_folder(os.path.dirname(pkcs12_path))
                    self.config.save()
                    self.cert_manager.add_cert_path(pkcs12_path)
                    show_message_dialog(self.window, self._("success"), self._("cert_load_success").format(common_name), Gtk.MessageType.INFO)
                    self.update_ui()
                else:
                    show_message_dialog(self.window, self._("error"), self._("bad_password_or_file"), Gtk.MessageType.ERROR)
        create_password_dialog(self.window, self._, pkcs12_path, on_password_response)

def main():
    app = GnomeSign()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()