# ui/stamp_editor_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango, PangoCairo, Secret, Gdk
import uuid
import re
from certificate_manager import KEYRING_SCHEMA

class StampEditorDialog(Gtk.Dialog):
    """A dialog for creating, editing, and managing signature stamp templates."""

    def __init__(self, parent_window, app, **kwargs):
        super().__init__(transient_for=parent_window, modal=True, **kwargs)
        
        self.app = app
        self.config = self.app.config
        self.i18n = self.app.i18n
        
        # Estado interno
        self.current_id = None
        self.initial_form_data = None
        self.loaded_cert = None
        self.block_combo_changed = False

        self.set_title(self.i18n._("edit_stamp_templates"))
        self.set_default_size(700, 600)

        self.add_button(self.i18n._("close_button"), Gtk.ResponseType.CLOSE)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.get_content_area().append(main_box)

        # Paneles
        left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=220)
        main_box.append(left_pane)
        self.right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        main_box.append(self.right_pane)

        # Contenido Panel Izquierdo
        left_pane.append(Gtk.Label(label=f"<b>{self.i18n._('templates')}</b>", use_markup=True, xalign=0))
        self.template_combo = Gtk.ComboBoxText()
        left_pane.append(self.template_combo)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12)
        left_pane.append(btn_box)
        
        self.new_btn = Gtk.Button.new_with_label(self.i18n._("new"))
        self.duplicate_btn = Gtk.Button.new_with_label(self.i18n._("duplicate"))
        self.save_btn = Gtk.Button.new_with_label(self.i18n._("save"))
        self.delete_btn = Gtk.Button.new_with_label(self.i18n._("delete"))
        self.set_active_btn = Gtk.Button.new_with_label(self.i18n._("set_as_active"))
        btn_box.append(self.new_btn)
        btn_box.append(self.duplicate_btn)
        btn_box.append(self.save_btn)
        btn_box.append(self.delete_btn)
        btn_box.append(self.set_active_btn)

        self._build_right_pane()
        self._connect_signals()
        
        self._load_certificate_for_preview()
        self._load_templates_to_combo()

    def _build_right_pane(self):
        """Construye la parte derecha de la UI del editor."""
        self.right_pane.append(Gtk.Label(label=f"<b>{self.i18n._('template_name')}</b>", use_markup=True, xalign=0))
        self.name_entry = Gtk.Entry()
        self.right_pane.append(self.name_entry)

        toolbar = self._build_toolbar()
        self.right_pane.append(toolbar)

        self.right_pane.append(Gtk.Label(label=f"<b>{self.i18n._('template_content')}</b>", use_markup=True, xalign=0))
        self.text_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scrolled_text = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy="never", min_content_height=120)
        scrolled_text.set_child(self.text_view)
        self.right_pane.append(scrolled_text)

        preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=True)
        self.right_pane.append(preview_container)
        preview_container.append(Gtk.Label(label=f"<b>{self.i18n._('preview')}</b>", use_markup=True, xalign=0))
        self.preview_area = Gtk.DrawingArea(vexpand=True, hexpand=True)
        self.preview_area.get_style_context().add_class("view")
        preview_container.append(self.preview_area)

    def _build_toolbar(self):
        toolbar = Gtk.Box(spacing=6)
        
        bold_btn = Gtk.Button.new_from_icon_name("format-text-bold-symbolic")
        bold_btn.connect("clicked", lambda b: self._toggle_pango_tag("b"))
        italic_btn = Gtk.Button.new_from_icon_name("format-text-italic-symbolic")
        italic_btn.connect("clicked", lambda b: self._toggle_pango_tag("i"))

        font_combo = Gtk.ComboBoxText.new()
        font_combo.append("placeholder_id", self.i18n._("font"))
        for font in ["Times-Roman", "Helvetica", "Courier"]: font_combo.append_text(font)
        font_combo.set_active_id("placeholder_id")
        font_combo.connect("changed", self._on_font_changed)

        size_combo = Gtk.ComboBoxText.new()
        self.pango_size_map = {self.i18n._("size_small"): "small", self.i18n._("size_normal"): "medium", self.i18n._("size_large"): "large", self.i18n._("size_huge"): "x-large"}
        size_combo.append("placeholder_id", self.i18n._("size"))
        for label in self.pango_size_map: size_combo.append_text(label)
        size_combo.set_active_id("placeholder_id")
        size_combo.connect("changed", self._on_size_changed)

        color_btn = Gtk.ColorButton.new()
        color_btn.connect("color-set", lambda b: self._apply_span_tag("color", self._rgba_to_hex(b.get_rgba())))
        
        toolbar.append(bold_btn)
        toolbar.append(italic_btn)
        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        toolbar.append(font_combo)
        toolbar.append(size_combo)
        toolbar.append(color_btn)
        return toolbar

    def _connect_signals(self):
        self.new_btn.connect("clicked", self._on_new_clicked)
        self.duplicate_btn.connect("clicked", self._on_duplicate_clicked)
        self.save_btn.connect("clicked", self._on_save_clicked)
        self.delete_btn.connect("clicked", self._on_delete_clicked)
        self.set_active_btn.connect("clicked", self._on_set_active_clicked)
        
        self.template_combo.connect("changed", self._on_template_changed)
        self.text_view.get_buffer().connect("changed", self._on_buffer_changed)
        self.name_entry.connect("changed", self._on_buffer_changed)
        
        self.preview_area.set_draw_func(self._draw_preview)
        self.connect("response", self._on_response)
        self.connect("close-request", self._on_close_request)
    
    def _on_buffer_changed(self, widget):
        self.preview_area.queue_draw()
        if self._is_form_dirty():
            self.save_btn.set_sensitive(True)

    def _get_focused_buffer_and_bounds(self):
        buffer = self.text_view.get_buffer()
        if not buffer.get_has_selection(): return None, None, None
        return buffer, buffer.get_selection_bounds()

    def _toggle_pango_tag(self, tag):
        buffer, bounds = self._get_focused_buffer_and_bounds()
        if not buffer: return
        start, end = bounds
        text = buffer.get_text(start, end, True)
        if text.strip().startswith(f"<{tag}>") and text.strip().endswith(f"</{tag}>"):
            unwrapped_text = re.sub(f'^\\s*<{tag}>(.*?)</{tag}>\\s*$', r'\1', text, flags=re.DOTALL)
            buffer.delete(start, end); buffer.insert(start, unwrapped_text)
        else:
            buffer.delete(start, end); buffer.insert(start, f"<{tag}>{text}</{tag}>")

    def _apply_span_tag(self, attribute, value):
        buffer, bounds = self._get_focused_buffer_and_bounds()
        if not buffer: return
        start, end = bounds
        text = buffer.get_text(start, end, True)
        buffer.delete(start, end); buffer.insert(start, f'<span {attribute}="{value}">{text}</span>')

    def _rgba_to_hex(self, rgba):
        return f"#{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"
        
    def _on_font_changed(self, combo):
        if combo.get_active_id() == "placeholder_id": return
        self._apply_span_tag("font_family", combo.get_active_text())

    def _on_size_changed(self, combo):
        if combo.get_active_id() == "placeholder_id": return
        if pango_size := self.pango_size_map.get(combo.get_active_text()):
            self._apply_span_tag("size", pango_size)
            
    def _on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            # La lógica de confirmación está en _on_close_request.
            # Si devuelve True, se detiene el cierre.
            if not self._on_close_request(self):
                self.destroy()

    def _load_certificate_for_preview(self):
        if self.app.active_cert_path:
            password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": self.app.active_cert_path}, None)
            if password: _, self.loaded_cert = self.app.cert_manager.get_credentials(self.app.active_cert_path, password)

    def _get_current_form_state(self):
        return {
            "name": self.name_entry.get_text(),
            "template": self.text_view.get_buffer().get_text(*self.text_view.get_buffer().get_bounds(), False),
        }

    def _is_form_dirty(self):
        return self.initial_form_data is not None and self.initial_form_data != self._get_current_form_state()

    def _load_templates_to_combo(self):
        self.block_combo_changed = True
        self.template_combo.remove_all()
        for t in self.config.get_signature_templates(): self.template_combo.append(t['id'], t['name'])
        
        active_id = self.config.get_active_template_id()
        if active_id and any(t['id'] == active_id for t in self.config.get_signature_templates()):
             self.template_combo.set_active_id(active_id)
        elif self.config.get_signature_templates():
            self.template_combo.set_active(0)
        
        self.block_combo_changed = False
        self._on_template_changed(self.template_combo)

    def _clear_fields(self):
        self.name_entry.set_text("")
        self.text_view.get_buffer().set_text("")

    def _load_template_data(self, template_id):
        template = self.config.get_template_by_id(template_id)
        if template:
            self.current_id = template_id
            self.name_entry.set_text(template['name'])
            template_content = template.get('template', template.get('template_es', ''))
            self.text_view.get_buffer().set_text(template_content)
            self.delete_btn.set_sensitive(len(self.config.get_signature_templates()) > 1)
            self.set_active_btn.set_sensitive(self.config.get_active_template_id() != template_id)
        else:
            self._clear_fields()
        
        self.initial_form_data = self._get_current_form_state()
        self.save_btn.set_sensitive(False)
        self.preview_area.queue_draw()

    def _on_template_changed(self, combo):
        if self.block_combo_changed: return
        
        if self._is_form_dirty():
            target_id = combo.get_active_id()
            confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.i18n._("unsaved_changes_title"), secondary_text=self.i18n._("unsaved_changes_message"))
            def on_confirm_response(conf_d, res):
                if res == Gtk.ResponseType.YES:
                    self._load_template_data(target_id)
                else:
                    self.block_combo_changed = True
                    self.template_combo.set_active_id(self.current_id)
                    self.block_combo_changed = False
                conf_d.destroy()
            confirm_dialog.connect("response", on_confirm_response)
            confirm_dialog.present()
            return

        if active_id := combo.get_active_id():
            self._load_template_data(active_id)

    def _on_new_clicked(self, btn):
        self.current_id = uuid.uuid4().hex
        self._clear_fields()
        self.name_entry.set_text(f"{self.i18n._('new')} {self.i18n._('template')}")
        self.initial_form_data = self._get_current_form_state()
        self.name_entry.grab_focus()

    def _on_duplicate_clicked(self, btn):
        if not self.current_id: return
        self.current_id = uuid.uuid4().hex
        self.name_entry.set_text(f"{self.name_entry.get_text()} ({self.i18n._('copy')})")
        self.initial_form_data = self._get_current_form_state()
        self.save_btn.set_sensitive(True)

    def _on_save_clicked(self, btn):
        if not self.current_id: return
        template_data = {"id": self.current_id, **self._get_current_form_state()}
        self.config.save_template(template_data)
        self.initial_form_data = self._get_current_form_state()
        self.save_btn.set_sensitive(False)
        
        active_id_before = self.template_combo.get_active_id()
        self._load_templates_to_combo()
        self.template_combo.set_active_id(self.current_id or active_id_before)

    def _on_delete_clicked(self, btn):
        if not self.current_id or len(self.config.get_signature_templates()) <= 1: return
        self.config.delete_template(self.current_id)
        self.current_id = None
        self._load_templates_to_combo()

    def _on_set_active_clicked(self, btn):
        if not self.current_id: return
        self.config.set_active_template_id(self.current_id)
        self.set_active_btn.set_sensitive(False)
        self.app.emit("signature-state-changed")

    def _on_close_request(self, dialog):
        if self._is_form_dirty():
            confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.i18n._("unsaved_changes_title"), secondary_text=self.i18n._("confirm_close_message"))
            def on_confirm_response(conf_d, res):
                if res == Gtk.ResponseType.YES: self.destroy()
                conf_d.destroy()
            confirm_dialog.connect("response", on_confirm_response)
            confirm_dialog.present()
            return True 
        return False

    def _draw_preview(self, area, cr, width, h):
        cr.save()
        cr.set_source_rgb(0.9, 0.9, 0.9); cr.paint()
        
        text = self.text_view.get_buffer().get_text(*self.text_view.get_buffer().get_bounds(), False)
        
        if self.loaded_cert:
            preview_text = self.app.get_parsed_stamp_text(self.loaded_cert, override_template=text)
        else:
            preview_text = re.sub(r'\$\$SIGNDATE=.*?Z\$\$', "24/12/2025", text.replace("$$SUBJECTCN$$", "Subject Name").replace("$$ISSUERCN$$", "Issuer Name").replace("$$CERTSERIAL$$", "123456789"))
        
        cr.rectangle(10, 10, width - 20, h - 20)
        cr.set_source_rgb(1.0, 1.0, 1.0); cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.stroke()

        layout = PangoCairo.create_layout(cr)
        layout.set_width(Pango.units_from_double(width - 40))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_markup(preview_text if preview_text else " ", -1)
        
        ink, logical = layout.get_pixel_extents()
        scale = min((width - 40) / logical.width if logical.width > 0 else 1, (h - 20) / logical.height if logical.height > 0 else 1, 1.0)
        final_w, final_h = logical.width * scale, logical.height * scale
        start_x, start_y = (width - final_w) / 2, (h - final_h) / 2
        
        cr.translate(start_x - (logical.x * scale), start_y - (logical.y * scale))
        cr.scale(scale, scale)
        cr.set_source_rgb(0, 0, 0)
        PangoCairo.show_layout(cr, layout)
        cr.restore()