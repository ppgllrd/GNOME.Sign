# main.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1") 
gi.require_version("Secret", "1")

from gi.repository import Gtk, Adw, Gio, Secret, GLib, Pango
import fitz, os, sys, shutil, re, hashlib
from datetime import datetime
from html.parser import HTMLParser

from i18n import I18NManager
from certificate_manager import CertificateManager, KEYRING_SCHEMA
from config_manager import ConfigManager

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfSigner, PdfSignatureMetadata
from cryptography import x509

class PangoToHtmlConverter(HTMLParser):
    def __init__(self): super().__init__(); self.html_parts = []; self.style_stack = [{}]
    def get_current_styles(self): return self.style_stack[-1]
    def handle_starttag(self, tag, attrs):
        new_styles = self.get_current_styles().copy(); attrs_dict = dict(attrs)
        if tag == 'b': new_styles['font-weight'] = 'bold'
        elif tag == 'i': new_styles['font-style'] = 'italic'
        elif tag == 'span':
            if 'font_family' in attrs_dict: new_styles['font-family'] = f"'{attrs_dict['font_family']}'"
            if 'color' in attrs_dict: new_styles['color'] = attrs_dict['color']
            if 'size' in attrs_dict:
                css_size = 12 
                pango_size = attrs_dict['size']
                if pango_size == "small": css_size = 9
                elif pango_size == "medium": css_size = 12
                elif pango_size == "large": css_size = 16
                elif pango_size == "x-large": css_size = 20
                else:
                    try: css_size = int(pango_size) / Pango.SCALE
                    except (ValueError, TypeError): pass
                new_styles['font-size'] = f'{css_size:.1f}pt'
        self.style_stack.append(new_styles)
    def handle_endtag(self, tag):
        if len(self.style_stack) > 1: self.style_stack.pop()
    def handle_data(self, data):
        if not data: return
        styles = self.get_current_styles(); style_str = "; ".join(f"{k}: {v}" for k, v in styles.items() if v)
        escaped_data = GLib.markup_escape_text(data)
        if style_str: self.html_parts.append(f'<span style="{style_str}">{escaped_data}</span>')
        else: self.html_parts.append(escaped_data)
    def get_html(self): return "".join(self.html_parts).replace('\n', '<br/>')

class GnomeSign(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.pepeg.GnomeSign", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = ConfigManager()
        self.i18n = I18NManager()
        self.cert_manager = CertificateManager()
        self.doc, self.current_page = None, 0
        self.page, self.display_pixbuf, self.current_file_path = None, None, None
        self.signature_rect, self.is_dragging_rect = None, False
        self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.window, self.stamp_editor_window, self.preferences_window = None, None, None

    def _(self, key): return self.i18n._(key)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.config.load()
        self.i18n.set_language(self.config.get_language())
        self.cert_manager.set_cert_paths(self.config.get_cert_paths())
        self._ensure_active_certificate()
        self._build_actions()
        from ui.app_window import AppWindow
        self.window = AppWindow(application=self)
        
    def do_activate(self):
        self.window.present()

    def do_open(self, files, n_files, hint):
        if n_files > 0:
            file_path = files[0].get_path()
            if file_path and file_path.lower().endswith('.pdf'): self.open_file_path(file_path)
        self.do_activate()

    def _ensure_active_certificate(self):
        cert_paths = self.config.get_cert_paths()
        if not cert_paths: self.active_cert_path = None; return
        stored_path = self.config.config_data.get('active_cert_path')
        if stored_path and stored_path in cert_paths: self.active_cert_path = stored_path
        else: self.active_cert_path = cert_paths[0] if cert_paths else None; self.config.config_data['active_cert_path'] = self.active_cert_path; self.config.save()

    def set_active_certificate(self, path):
        self.active_cert_path = path; self.config.config_data['active_cert_path'] = path; self.config.save(); self.update_ui()

    def _build_actions(self):
        simple_actions = [("open", self.on_open_pdf_clicked), ("sign", self.on_sign_document_clicked), ("preferences", self.on_preferences_clicked), ("about", self.on_about_clicked), ("edit_stamps", self.on_edit_stamps_clicked)]
        for name, callback in simple_actions:
            if not self.lookup_action(name): action = Gio.SimpleAction.new(name, None); action.connect("activate", callback); self.add_action(action)
        if not self.lookup_action("change_lang"):
            action = Gio.SimpleAction.new_stateful("change_lang", GLib.VariantType('s'), GLib.Variant('s', self.i18n.get_language())); action.connect("change-state", self.on_lang_change_state); self.add_action(action)

    def open_file_path(self, file_path):
        try:
            if not os.path.exists(file_path): raise FileNotFoundError(f"File not found: {file_path}")
            if self.doc: self.doc.close()
            self.current_file_path = file_path; self.doc = fitz.open(file_path); self.current_page = 0
            self.config.add_recent_file(file_path); self.config.set_last_folder(os.path.dirname(file_path)); self.config.save()
            self.reset_signature_state()
            self.window.sidebar.populate(self.doc)
            self.display_page(self.current_page)
            self.update_ui()
        except Exception as e:
            if self.window: self.window.show_toast(self._("open_pdf_error").format(e))
            self.doc = None; self.update_ui()

    def on_open_pdf_clicked(self, action, param):
        dialog = Gtk.FileDialog.new(); dialog.set_title(self._("open_pdf_dialog_title"))
        filters = Gio.ListStore.new(Gtk.FileFilter); filter_pdf = Gtk.FileFilter.new()
        filter_pdf.set_name(self._("pdf_files")); filter_pdf.add_mime_type("application/pdf")
        filters.append(filter_pdf); dialog.set_filters(filters); dialog.set_default_filter(filter_pdf)
        dialog.open(self.window, None, self._on_open_pdf_finish)

    def _on_open_pdf_finish(self, dialog, result):
        try: 
            file = dialog.open_finish(result);
            if file: self.open_file_path(file.get_path())
        except GLib.Error: pass

    def on_open_recent_clicked_action(self, file_path):
        if os.path.exists(file_path): self.open_file_path(file_path)
        else:
            if self.window: self.window.show_toast(f"File not found: {file_path}")
            self.config.remove_recent_file(file_path); self.config.save(); self.update_ui()

    def on_preferences_clicked(self, action, param):
        if not self.preferences_window:
            from ui.preferences_window import PreferencesWindow
            self.preferences_window = PreferencesWindow(application=self)
        self.preferences_window.present()

    def on_edit_stamps_clicked(self, action, param):
        if not self.stamp_editor_window:
            from ui.stamp_editor_window import StampEditorWindow
            self.stamp_editor_window = StampEditorWindow(application=self)
        self.stamp_editor_window.present()

    def on_lang_change_state(self, action, value):
        new_lang = value.get_string()
        if self.i18n.get_language() != new_lang:
            action.set_state(value)
            self.i18n.set_language(new_lang)
            self.config.set_language(new_lang) 
            self.update_ui()
    
    def update_ui(self):
        """SOLUCIÓN DEFINITIVA: Orquesta la actualización de textos en TODAS las ventanas."""
        if self.window: self.window.update_all_texts()
        if self.preferences_window: self.preferences_window.update_all_texts()
        if self.stamp_editor_window: self.stamp_editor_window.update_all_texts()

    def on_about_clicked(self, action, param):
        dialog = Adw.AboutWindow(transient_for=self.window, application_name="GnomeSign", application_icon="org.pepeg.GnomeSign", version="1.0", developer_name="Pepe Gallardo", website="https://github.com/ppgllrd/GNOME.Sign", comments=self._("sign_reason"))
        dialog.present()
        
    def reset_signature_state(self):
        self.signature_rect = None; self.start_x, self.start_y, self.end_x, self.end_y = -1, -1, -1, -1
        self.is_dragging_rect = False;
        if self.window: self.window.sign_button.set_sensitive(False)

    def display_page(self, page_num):
        if not self.doc or not (0 <= page_num < len(self.doc)): self.page, self.doc, self.current_file_path, self.display_pixbuf = None, None, None, None; return
        self.current_page = page_num; self.page = self.doc.load_page(page_num); self.display_pixbuf = None
        if self.window:
            self.window.update_header_bar_state(self); self.window.drawing_area.queue_draw()
            GLib.idle_add(self.window.adjust_scroll_and_viewport); self.window.sidebar.select_page(page_num)
    
    def on_prev_page_clicked(self, button):
        if self.doc and self.current_page > 0: self.reset_signature_state(); self.display_page(self.current_page - 1)
    
    def on_next_page_clicked(self, button):
        if self.doc and self.current_page < len(self.doc) - 1: self.reset_signature_state(); self.display_page(self.current_page + 1)
            
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
            if res == Gtk.ResponseType.OK: self.reset_signature_state(); self.display_page(spin.get_value_as_int() - 1)
            d.destroy()
        dialog.connect("response", on_response); dialog.present()

    def on_drag_begin(self, gesture, start_x, start_y):
        if self.signature_rect:
            x, y, w, h = self.signature_rect
            if x <= start_x <= x + w and y <= start_y <= y + h: self.is_dragging_rect, self.drag_offset_x, self.drag_offset_y = True, start_x - x, start_y - y; return
        self.is_dragging_rect, self.start_x, self.start_y = False, start_x, start_y
        self.end_x, self.end_y = start_x, start_y; self.signature_rect = None
        self.window.update_header_bar_state(self); self.window.drawing_area.queue_draw()
        if not self.has_shown_drag_infobar: self.has_shown_drag_infobar = True; self.window.update_info_bar(self)

    def on_drag_update(self, gesture, offset_x, offset_y):
        success, start_point_x, start_point_y = gesture.get_start_point()
        if not success: return
        current_x, current_y = start_point_x + offset_x, start_point_y + offset_y
        if self.is_dragging_rect: _, _, w, h = self.signature_rect; self.signature_rect = (current_x - self.drag_offset_x, current_y - self.drag_offset_y, w, h)
        else: self.end_x, self.end_y = current_x, current_y
        if self.window: self.window.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if not self.is_dragging_rect:
            x1, y1 = min(self.start_x, self.end_x), min(self.start_y, self.end_y)
            width, height = abs(self.start_x - self.end_x), abs(self.start_y - self.end_y)
            self.signature_rect = (x1, y1, width, height) if width > 10 and height > 10 else None
        self.is_dragging_rect = False
        if self.window: self.window.update_header_bar_state(self); self.window.drawing_area.queue_draw()
    
    def on_sign_document_clicked(self, action=None, param=None):
        if not self.doc or not self.current_file_path: return
        if not self.signature_rect:
            if self.window: self.window.show_toast(self._("need_pdf_and_area")); return
        if not self.active_cert_path:
            if self.window: self.window.show_toast(self._("no_cert_selected_error")); return
        
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

            signer = signers.SimpleSigner(private_key, certificate, ca_chain_certs=())
            
            signer_cn_attrs = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            signer_cn = signer_cn_attrs[0].value if signer_cn_attrs else "Unknown Signer"

            meta = PdfSignatureMetadata(field_name=f'Signature-{int(datetime.now().timestamp() * 1000)}', reason=self._("sign_reason"), name=signer_cn)
            pdf_signer = PdfSigner(meta, signer)
            with open(output_path, "rb+") as f:
                writer = IncrementalPdfFileWriter(f)                
                pdf_signer.sign_pdf(writer, output=f)
            
            if self.window:
                toast_message = self._("sign_success_message").format(os.path.basename(output_path))
                self.window.show_toast(toast_message, self._("open"), lambda: self.open_file_path(output_path))
            
        except Exception as e:
            if self.window: self.window.show_toast(self._("sig_error_message").format(e))
            import traceback; traceback.print_exc()

    def get_parsed_stamp_text(self, certificate, override_template=None):
        if override_template is not None: template = override_template
        else:
            template_obj = self.config.get_active_template()
            if not template_obj: return "Error: No active signature template found."
            template = template_obj.get(f"template_{self.i18n.get_language()}", template_obj.get("template_en", ""))
        def get_cn(name):
            try: return name.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            except (IndexError, AttributeError): return name.rfc4514_string()
        text = template.replace("$$SUBJECTCN$$", GLib.markup_escape_text(get_cn(certificate.subject)))
        text = text.replace("$$ISSUERCN$$", GLib.markup_escape_text(get_cn(certificate.issuer)))
        text = text.replace("$$CERTSERIAL$$", str(certificate.serial_number))
        date_match = re.search(r'\$\$SIGNDATE=(.*?)\$\$', text)
        if date_match:
            format_pattern = date_match.group(1).replace("dd", "%d").replace("MM", "%m").replace("yyyy", "%Y").replace("yy", "%y").replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
            text = text.replace(date_match.group(0), datetime.now().strftime(format_pattern))
        return text

    def _apply_visual_stamp(self, input_path, certificate):
        doc = fitz.open(input_path); page = doc.load_page(self.current_page)
        view_width = self.window.drawing_area.get_width()
        scale = page.rect.width / view_width if view_width > 0 else 1
        x, y, w, h = self.signature_rect
        fitz_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
        parsed_pango_text = self.get_parsed_stamp_text(certificate)
        converter = PangoToHtmlConverter(); converter.feed(parsed_pango_text)
        html_content = f"""
        <div style="width:100%; height:100%; display:table; text-align:center; line-height:1.2; font-family: sans-serif; font-size: 10pt;">
            <div style="display:table-cell; vertical-align:middle;">
                {converter.get_html()}
            </div>
        </div>
        """
        css = """ div { box-sizing: border-box; } """
        page.insert_htmlbox(fitz_rect + (5, 5, -5, -5), html_content, css=css, rotate=0)
        doc.save(input_path, incremental=True, encryption=0); doc.close()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    app = GnomeSign()
    sys.exit(app.run(sys.argv))