import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Secret", "1")
from gi.repository import Gtk, Gio, Secret, GLib
import fitz  # PyMuPDF
import os
import sys
import shutil
from datetime import datetime

from certificate_manager import CertificateManager, KEYRING_SCHEMA
from config_manager import ConfigManager
from ui.app_window import AppWindow
from ui.dialogs import (create_about_dialog, create_cert_selector_dialog, 
                        create_password_dialog, show_message_dialog,
                        create_jump_to_page_dialog)

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfSigner, PdfSignatureMetadata
from pyhanko.keys.internal import translate_pyca_cryptography_key_to_asn1, translate_pyca_cryptography_cert_to_asn1
from pyhanko_certvalidator.registry import SimpleCertificateStore

class GnomeSign(Gtk.Application):
    """
    The main application class. It manages the application lifecycle,
    state, and actions. It doesn't build the UI itself but delegates
    that to the AppWindow class.
    """
    def __init__(self):
        super().__init__(application_id="org.pepeg.GnomeSign", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config = ConfigManager()
        self.cert_manager = CertificateManager()
        self.doc, self.current_page, self.active_cert_path = None, 0, None
        self.page, self.display_pixbuf, self.current_file_path = None, None, None
        self.signature_rect, self.is_dragging_rect = None, False
        self.drag_offset_x, self.drag_offset_y = 0, 0
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.language = "es"
        self.translations = {
            "es": {"window_title": "GnomeSign", "open_pdf": "Abrir PDF...", "prev_page": "Página anterior", "next_page": "Página siguiente", "sign_document": "Firmar Documento", "load_certificate": "Cargar Certificado...", "select_certificate": "Seleccionar Certificado", "no_certificate_selected": "Sin certificado", "active_certificate": "Certificado activo: {}", "sign_reason": "Firmado con GNOMESign", "error": "Error", "success": "Éxito", "question": "Pregunta", "password": "Contraseña", "sig_error_title": "Error de Firma", "sig_error_message": "Error: {}", "need_pdf_and_area": "Necesitas abrir un PDF y seleccionar un área de firma.", "no_cert_selected_error": "No hay un certificado seleccionado.", "credential_load_error": "No se pudieron cargar las credenciales del certificado.", "sign_success_title": "Documento Firmado Correctamente", "sign_success_message": "Guardado en:\n{}\n\n¿Quieres abrir el documento firmado ahora?", "open_pdf_error": "No se pudo abrir el PDF: {}", "cert_load_success": "Certificado '{}' cargado.", "bad_password_or_file": "Contraseña incorrecta o archivo dañado.", "open_pdf_dialog_title": "Abrir Documento PDF", "open_cert_dialog_title": "Seleccionar Archivo de Certificado (.p12/.pfx)", "open": "_Abrir", "cancel": "_Cancelar", "accept": "_Aceptar", "pdf_files": "Archivos PDF", "p12_files": "Archivos PKCS#12 (.p12, .pfx)", "digitally_signed_by": "Firmado digitalmente por:", "date": "Fecha:", "change_language": "Cambiar Idioma", "about": "Acerca de", "open_recent": "Abrir Recientes", "jump_to_page_title": "Ir a la página", "jump_to_page_prompt": "Ir a la página (1 - {})"},
            "en": {"window_title": "GnomeSign", "open_pdf": "Open PDF...", "prev_page": "Previous page", "next_page": "Next page", "sign_document": "Sign Document", "load_certificate": "Load Certificate...", "select_certificate": "Select certificate", "no_certificate_selected": "No certificate", "active_certificate": "Active certificate: {}", "sign_reason": "Signed with GNOMESign", "error": "Error", "success": "Success", "question": "Question", "password": "Password", "sig_error_title": "Signature Error", "sig_error_message": "Error: {}", "need_pdf_and_area": "You need to open a PDF and select a signature area.", "no_cert_selected_error": "No certificate selected.", "credential_load_error": "Could not load certificate credentials.", "sign_success_title": "Document Signed Successfully", "sign_success_message": "Saved at:\n{}\n\nDo you want to open the signed document now?", "open_pdf_error": "Could not open PDF: {}", "cert_load_success": "Certificate '{}' loaded successfully.", "bad_password_or_file": "Incorrect password or corrupted file.", "open_pdf_dialog_title": "Open PDF Document", "open_cert_dialog_title": "Select Certificate File (.p12/.pfx)", "open": "_Open", "cancel": "_Cancel", "accept": "_Accept", "pdf_files": "PDF Files", "p12_files": "PKCS#12 Files (.p12, .pfx)", "digitally_signed_by": "Digitally signed by:", "date": "Date:", "change_language": "Change Language", "about": "About", "open_recent": "Open Recent", "jump_to_page_title": "Go to page", "jump_to_page_prompt": "Go to page (1 - {})"}
        }

    def _(self, key):
        return self.translations[self.language].get(key, key)

    def get_formatted_date(self):
        return datetime.now().strftime('%d-%m-%Y' if self.language == "es" else '%Y-%m-%d')

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.config.load()
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
            ("change_lang", self.on_lang_button_clicked),
            ("about", lambda a, p: create_about_dialog(self.window, self._)),
            ("open_recent", self.on_open_recent_clicked, "s"),
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
                if file: self.open_file_path(file.get_path())
        file_chooser = Gtk.FileChooserNative.new(self._("open_pdf_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_pdf = Gtk.FileFilter(); filter_pdf.set_name(self._("pdf_files")); filter_pdf.add_mime_type("application/pdf")
        file_chooser.add_filter(filter_pdf)
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
            
    def on_cert_button_clicked(self, button):
        cert_map = self.cert_manager.get_all_display_names(KEYRING_SCHEMA)
        if not cert_map: return
        def on_cert_selected(selected_path):
            if selected_path:
                self.active_cert_path = selected_path
                self.update_ui()
        create_cert_selector_dialog(self.window, self._, cert_map, on_cert_selected)

    def on_lang_button_clicked(self, action, param):
        self.language = "en" if self.language == "es" else "es"
        self.update_ui()

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
            signer_cn = certificate.subject.rfc4514_string().split('CN=')[1].split(',')[0]
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
                if file: self._process_certificate_selection(file.get_path())
        file_chooser = Gtk.FileChooserNative.new(self._("open_cert_dialog_title"), self.window, Gtk.FileChooserAction.OPEN, self._("open"), self._("cancel"))
        filter_p12 = Gtk.FileFilter(); filter_p12.set_name(self._("p12_files")); filter_p12.add_pattern("*.p12"); filter_p12.add_pattern("*.pfx")
        file_chooser.add_filter(filter_p12)
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
            # Ensure the scrollable area size is recalculated
            self.window.update_drawing_area_size_request()

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
        if not self.doc:
            return
            
        def on_page_selected(page_num):
            if page_num is not None:
                self.current_page = page_num
                self.reset_signature_state()
                self.display_page(self.current_page)
                self.update_ui()
        
        create_jump_to_page_dialog(
            self.window, self._, 
            self.current_page + 1, len(self.doc),
            on_page_selected
        )

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

    def _apply_visual_stamp(self, input_path, certificate):
        doc = fitz.open(input_path)
        page = doc.load_page(self.current_page)
        view_width = self.window.drawing_area.get_width()
        scale = page.rect.width / view_width if view_width > 0 else 1
        x, y, w, h = self.signature_rect
        fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
        page.draw_rect(fitz_rect, color=None, fill=(1.0, 1.0, 1.0), fill_opacity=1.0, overlay=True)
        signer_cn = certificate.subject.rfc4514_string().split('CN=')[1].split(',')[0]
        current_date = self.get_formatted_date()
        html_content = f"""
        <div style="
            text-align: center; 
            font-family: helvetica, sans-serif; 
            line-height: 1.3;
        ">
            <p style="margin: 0; font-size: 8pt;">{self._("digitally_signed_by")}</p>
            <p style="margin: 2px 0; font-size: 9pt; font-weight: bold;">{signer_cn}</p>
            <p style="margin: 0; font-size: 7pt;">{self._("date")} {current_date}</p>
        </div>
        """
        page.insert_htmlbox(fitz_rect, html_content, css="p {padding: 0;}")
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
                    self.config.add_cert_path(pkcs12_path); self.config.save(); self.cert_manager.add_cert_path(pkcs12_path)
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