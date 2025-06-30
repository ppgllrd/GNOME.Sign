# ui/stamp_editor_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gtk, Adw, Pango, PangoCairo, Secret, GLib
import uuid
import re

from certificate_manager import KEYRING_SCHEMA

class StampEditorWindow(Adw.Window):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = self.get_application()
        self.i18n_func = self.app._
        
        self.set_default_size(700, 600)
        self.set_modal(False)
        self.set_transient_for(self.app.window)
        self.set_hide_on_close(True)
        
        self._build_ui()
        self._connect_signals()
        self.update_ui()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        header_bar = Adw.HeaderBar.new()
        self.title_widget = Adw.WindowTitle.new("", "") # Se actualizará en update_ui
        header_bar.set_title_widget(self.title_widget)
        
        # SOLUCIÓN: Añadir botón de cerrar
        close_button = Gtk.Button.new_with_label(self.i18n_func("close_button"))
        close_button.connect("clicked", lambda w: self.close())
        header_bar.pack_end(close_button)
        
        root_box.append(header_bar)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        main_box.set_vexpand(True)
        root_box.append(main_box)
        
        left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=220); main_box.append(left_pane)
        right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True); main_box.append(right_pane)
        
        self.templates_label = Gtk.Label(use_markup=True, xalign=0); left_pane.append(self.templates_label)
        self.template_combo = Gtk.ComboBoxText(); left_pane.append(self.template_combo)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12); left_pane.append(btn_box)
        self.new_btn = Gtk.Button(); self.duplicate_btn = Gtk.Button()
        self.save_btn = Gtk.Button(); self.delete_btn = Gtk.Button()
        self.set_active_btn = Gtk.Button()
        btn_box.append(self.new_btn); btn_box.append(self.duplicate_btn); btn_box.append(self.save_btn); btn_box.append(self.delete_btn); btn_box.append(self.set_active_btn)
        
        self.template_name_label = Gtk.Label(use_markup=True, xalign=0); right_pane.append(self.template_name_label)
        self.name_entry = Gtk.Entry(); right_pane.append(self.name_entry)
        
        self.state = {"current_id": None, "block_combo_changed": False, "initial_form_data": None, "loaded_cert": None, "last_focused_view": None}
        self.text_es_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR); self.text_en_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.state["last_focused_view"] = self.text_es_view
        
        self._build_toolbar(right_pane)
        
        text_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); right_pane.append(text_box_container)
        self.template_es_label = Gtk.Label(use_markup=True, xalign=0); text_box_container.append(self.template_es_label)
        scrolled_es = Gtk.ScrolledWindow(child=self.text_es_view); scrolled_es.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scrolled_es.set_min_content_height(80); text_box_container.append(scrolled_es)
        self.template_en_label = Gtk.Label(use_markup=True, xalign=0); text_box_container.append(self.template_en_label)
        scrolled_en = Gtk.ScrolledWindow(child=self.text_en_view); scrolled_en.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scrolled_en.set_min_content_height(80); text_box_container.append(scrolled_en)
        
        preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=True); right_pane.append(preview_container)
        self.preview_label = Gtk.Label(use_markup=True, xalign=0); preview_container.append(self.preview_label)
        self.preview_area = Gtk.DrawingArea(vexpand=True, hexpand=True); self.preview_area.get_style_context().add_class("view"); preview_container.append(self.preview_area)
        
        if self.app.active_cert_path:
            password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": self.app.active_cert_path}, None)
            if password: _, self.state["loaded_cert"] = self.app.cert_manager.get_credentials(self.app.active_cert_path, password)

    def update_ui(self):
        """Actualiza todos los textos y el estado de la UI."""
        self.title_widget.set_title(self.i18n_func("edit_stamp_templates"))
        self.templates_label.set_markup(f"<b>{self.i18n_func('templates')}</b>")
        self.new_btn.set_label(self.i18n_func("new"))
        self.duplicate_btn.set_label(self.i18n_func("duplicate"))
        self.save_btn.set_label(self.i18n_func("save"))
        self.delete_btn.set_label(self.i18n_func("delete"))
        self.set_active_btn.set_label(self.i18n_func("set_as_active"))
        self.template_name_label.set_markup(f"<b>{self.i18n_func('template_name')}</b>")
        self.template_es_label.set_markup(f"<b>{self.i18n_func('template_es')}</b>")
        self.template_en_label.set_markup(f"<b>{self.i18n_func('template_en')}</b>")
        self.preview_label.set_markup(f"<b>{self.i18n_func('preview')}</b>")
        
        self.load_templates_to_combo()
    
    # ... (resto de la clase con sus métodos sin cambios)
    def _build_toolbar(self, parent_box):
        toolbar = Gtk.Box(spacing=6)
        bold_btn = Gtk.Button.new_from_icon_name("format-text-bold-symbolic"); bold_btn.connect("clicked", lambda b: self.toggle_pango_tag("b"))
        italic_btn = Gtk.Button.new_from_icon_name("format-text-italic-symbolic"); italic_btn.connect("clicked", lambda b: self.toggle_pango_tag("i"))
        
        self.pango_size_map = {self.i18n_func("size_small"): "small", self.i18n_func("size_normal"): "medium", self.i18n_func("size_large"): "large", self.i18n_func("size_huge"): "x-large"}
        
        font_combo = Gtk.ComboBoxText.new(); font_combo.append("placeholder_id", self.i18n_func("font"))
        for font in ["Times-Roman", "Helvetica", "Courier"]: font_combo.append_text(font)
        font_combo.set_active_id("placeholder_id"); font_combo.connect("changed", self.on_font_changed)
        size_combo = Gtk.ComboBoxText.new()

        size_combo.append("placeholder_id", self.i18n_func("size"))
        for label in self.pango_size_map: size_combo.append_text(label)
        size_combo.set_active_id("placeholder_id"); size_combo.connect("changed", self.on_size_changed)
        color_btn = Gtk.ColorButton.new(); color_btn.connect("color-set", lambda b: self.apply_span_tag("color", self._rgba_to_hex(b.get_rgba())))
        toolbar.append(bold_btn); toolbar.append(italic_btn); toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)); toolbar.append(font_combo); toolbar.append(size_combo); toolbar.append(color_btn)
        parent_box.append(toolbar)
    
    def on_font_changed(self, combo):
        if combo.get_active_id() != "placeholder_id": self.apply_span_tag("font_family", combo.get_active_text())
    def on_size_changed(self, combo):
        if combo.get_active_id() != "placeholder_id": self.apply_span_tag("size", self.pango_size_map.get(combo.get_active_text()))

    def _connect_signals(self):
        self.connect("close-request", self.on_close_request)
        self.text_es_view.connect("notify::has-focus", self.on_view_focus); self.text_en_view.connect("notify::has-focus", self.on_view_focus)
        self.preview_area.set_draw_func(self.draw_preview); self.preview_area.connect("resize", lambda a, w, h: a.queue_draw())
        self.text_es_view.get_buffer().connect("changed", lambda b: self.preview_area.queue_draw()); self.text_en_view.get_buffer().connect("changed", lambda b: self.preview_area.queue_draw())
        self.name_entry.connect("changed", lambda e: self.preview_area.queue_draw())
        self.new_btn.connect("clicked", self.on_new_clicked); self.duplicate_btn.connect("clicked", self.on_duplicate_clicked); self.save_btn.connect("clicked", self.on_save_clicked)
        self.delete_btn.connect("clicked", self.on_delete_clicked); self.set_active_btn.connect("clicked", self.on_set_active_clicked)
        self.template_combo.connect("changed", self.on_template_changed)

    def get_focused_buffer_and_bounds(self):
        view = self.state.get("last_focused_view");
        if not view: return None, None, None
        buffer = view.get_buffer(); bounds = buffer.get_selection_bounds()
        if not bounds: return None, None, None
        return buffer, *bounds

    def toggle_pango_tag(self, tag):
        buffer, start, end = self.get_focused_buffer_and_bounds()
        if not buffer or not start: return
        text = buffer.get_text(start, end, True)
        if text.strip().startswith(f"<{tag}>") and text.strip().endswith(f"</{tag}>"):
            unwrapped_text = re.sub(f'^\\s*<{tag}>(.*?)</{tag}>\\s*$', r'\1', text, flags=re.DOTALL)
            buffer.delete(start, end); buffer.insert(start, unwrapped_text)
        else: buffer.delete(start, end); buffer.insert(start, f"<{tag}>{text}</{tag}>")

    def apply_span_tag(self, attribute, value):
        buffer, start, end = self.get_focused_buffer_and_bounds()
        if not buffer or not start: return
        text = buffer.get_text(start, end, True)
        buffer.delete(start, end); buffer.insert(start, f'<span {attribute}="{value}">{text}</span>')

    def _rgba_to_hex(self, rgba): return f"#{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"
    def on_view_focus(self, widget, param_spec):
        if widget.get_property("has-focus"): self.state["last_focused_view"] = widget
    
    def draw_preview(self, area, cr, width, h):
        cr.save(); cr.set_source_rgb(0.9, 0.9, 0.9); cr.paint()
        text_buffer = self.text_es_view.get_buffer() if self.app.i18n.get_language() == "es" else self.text_en_view.get_buffer()
        text = text_buffer.get_text(text_buffer.get_start_iter(), text_buffer.get_end_iter(), False)
        if self.state["loaded_cert"]: preview_text = self.app.get_parsed_stamp_text(self.state["loaded_cert"], override_template=text)
        else: preview_text = re.sub(r'\$\$SIGNDATE=.*?Z\$\$', "24/12/2025", text.replace("$$SUBJECTCN$$", "Subject Name").replace("$$ISSUERCN$$", "Issuer Name").replace("$$CERTSERIAL$$", "123456789"))
        cr.rectangle(10, 10, width - 20, h - 20); cr.set_source_rgb(1.0, 1.0, 1.0); cr.fill_preserve(); cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.stroke()
        layout = PangoCairo.create_layout(cr); layout.set_width(Pango.units_from_double(width - 40)); layout.set_alignment(Pango.Alignment.CENTER); layout.set_markup(preview_text if preview_text else " ", -1)
        ink, logical = layout.get_pixel_extents()
        scale = min((width - 40) / logical.width if logical.width > 0 else 1, (h - 20) / logical.height if logical.height > 0 else 1, 1.0)
        final_w, final_h = logical.width * scale, logical.height * scale; start_x, start_y = (width - final_w) / 2, (h - final_h) / 2
        cr.translate(start_x - (logical.x * scale), start_y - (logical.y * scale)); cr.scale(scale, scale)
        cr.set_source_rgb(0, 0, 0); PangoCairo.show_layout(cr, layout); cr.restore()

    def get_current_form_state(self): return {"name": self.name_entry.get_text(), "template_es": self.text_es_view.get_buffer().get_text(*self.text_es_view.get_buffer().get_bounds(), False), "template_en": self.text_en_view.get_buffer().get_text(*self.text_en_view.get_buffer().get_bounds(), False)}
    def is_form_dirty(self): return self.state.get("initial_form_data") is not None and self.state["initial_form_data"] != self.get_current_form_state()
    def clear_fields(self): self.name_entry.set_text(""); self.text_es_view.get_buffer().set_text(""); self.text_en_view.get_buffer().set_text("")
    
    def load_templates_to_combo(self):
        self.state["block_combo_changed"] = True; self.template_combo.remove_all()
        for t in self.app.config.get_signature_templates(): self.template_combo.append(t['id'], t['name'])
        active_id = self.app.config.get_active_template_id()
        if active_id and any(t['id'] == active_id for t in self.app.config.get_signature_templates()):
            self.template_combo.set_active_id(active_id)
        elif self.app.config.get_signature_templates():
            self.template_combo.set_active(0)
            
        self.state["block_combo_changed"] = False; self.on_template_changed(self.template_combo, initial_load=True)

    def load_template_data(self, template_id):
        template = self.app.config.get_template_by_id(template_id)
        self.state["block_combo_changed"] = True
        if template:
            self.state["current_id"] = template_id; self.name_entry.set_text(template['name'])
            self.text_es_view.get_buffer().set_text(template.get('template_es', '')); self.text_en_view.get_buffer().set_text(template.get('template_en', ''))
            self.delete_btn.set_sensitive(len(self.app.config.get_signature_templates()) > 1)
            self.set_active_btn.set_sensitive(self.app.config.get_active_template_id() != template_id)
        else: self.clear_fields()
        self.state["block_combo_changed"] = False; self.state["initial_form_data"] = self.get_current_form_state(); self.preview_area.queue_draw()

    def on_template_changed(self, combo, initial_load=False):
        if self.state["block_combo_changed"]: return
        if not initial_load and self.is_form_dirty():
            target_id = combo.get_active_id()
            confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.i18n_func("unsaved_changes_title"), secondary_text=self.i18n_func("unsaved_changes_message"))
            def on_confirm_response(conf_d, res):
                if res == Gtk.ResponseType.YES: self.load_template_data(target_id)
                else: self.state["block_combo_changed"] = True; combo.set_active_id(self.state["current_id"]); self.state["block_combo_changed"] = False
                conf_d.destroy()
            confirm_dialog.connect("response", on_confirm_response); confirm_dialog.present()
        else:
            active_id = combo.get_active_id()
            if active_id: self.load_template_data(active_id)

    def on_new_clicked(self, btn):
        self.state["current_id"] = uuid.uuid4().hex; self.clear_fields()
        self.name_entry.set_text(self.i18n_func("new") + " " + self.i18n_func("templates")[:-1])
        self.state["initial_form_data"] = self.get_current_form_state(); self.name_entry.grab_focus()

    def on_duplicate_clicked(self, btn):
        if not self.state["current_id"]: return
        self.state["current_id"] = uuid.uuid4().hex; self.name_entry.set_text(self.name_entry.get_text() + f" ({self.i18n_func('copy')})")
        self.state["initial_form_data"] = self.get_current_form_state()

    def on_save_clicked(self, btn):
        if not self.state["current_id"]: return
        template_data = {"id": self.state["current_id"], **self.get_current_form_state()}; self.app.config.save_template(template_data)
        self.state["initial_form_data"] = self.get_current_form_state()
        self.load_templates_to_combo(); self.template_combo.set_active_id(self.state["current_id"])

    def on_delete_clicked(self, btn):
        if not self.state["current_id"] or len(self.app.config.get_signature_templates()) <= 1: return
        self.app.config.delete_template(self.state["current_id"]); self.state["current_id"] = None; self.load_templates_to_combo()

    def on_set_active_clicked(self, btn):
        if not self.state["current_id"]: return
        self.app.config.set_active_template_id(self.state["current_id"]); self.set_active_btn.set_sensitive(False); self.app.update_ui()
    
    def on_close_request(self, window):
        if self.is_form_dirty():
            confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.i18n_func("unsaved_changes_title"), secondary_text=self.i18n_func("confirm_close_message"))
            def on_confirm_response(conf_d, res):
                if res == Gtk.ResponseType.YES:
                    self.state["initial_form_data"] = self.get_current_form_state()
                    self.hide()
                conf_d.destroy()
            confirm_dialog.connect("response", on_confirm_response); confirm_dialog.present()
            return True
        return False