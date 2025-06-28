import gi
import os
import re
gi.require_version("Gtk", "4.0")
gi.require_version("Secret", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, Gio, Secret, GLib, Pango, PangoCairo
from certificate_manager import KEYRING_SCHEMA
import fitz 
from gi.repository import GdkPixbuf
from .dialogs import show_message_dialog

class AppWindow(Gtk.ApplicationWindow):
    """The main window of the application, responsible for building the UI."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        app = self.get_application()
        self.set_default_size(800, 600)
        self.set_title(app._("window_title"))
        self.set_icon_name("org.pepeg.GnomeSign")
        self._build_ui()
        self._setup_drop_target()

    def _build_ui(self):
        """Constructs the user interface."""
        app = self.get_application()
        self.header_bar = Gtk.HeaderBar()
        self.set_titlebar(self.header_bar)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.title_label = Gtk.Label()
        self.title_label.set_markup(f"<span weight='bold'>{app._('window_title')}</span>")
        self.subtitle_label = Gtk.Label()
        self.subtitle_label.get_style_context().add_class("caption")
        title_box.append(self.title_label)
        title_box.append(self.subtitle_label)
        self.header_bar.set_title_widget(title_box)
        
        self.open_button = Gtk.Button.new_from_icon_name("document-open-symbolic")
        self.header_bar.pack_start(self.open_button)

        nav_box = Gtk.Box(spacing=6)
        nav_box.get_style_context().add_class("linked")
        self.prev_page_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.page_entry_button = Gtk.Button.new_with_label("- / -")
        self.page_entry_button.get_style_context().add_class("flat")
        self.next_page_button = Gtk.Button.new_from_icon_name("go-next-symbolic")
        nav_box.append(self.prev_page_button)
        nav_box.append(self.page_entry_button)
        nav_box.append(self.next_page_button)
        self.header_bar.pack_start(nav_box)

        self.menu_button = Gtk.MenuButton.new()
        self.menu_button.set_icon_name("open-menu-symbolic")
        self.header_bar.pack_end(self.menu_button)

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(main_vbox)

        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_revealed(False)
        self.info_bar.set_show_close_button(True)
        self.info_bar.connect("response", lambda bar, res: bar.set_revealed(False))
        self.info_label = Gtk.Label()
        self.info_bar.add_child(self.info_label)
        main_vbox.append(self.info_bar)

        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_paned.set_vexpand(True)
        main_vbox.append(self.main_paned)
        
        self.view_stack = Gtk.Stack()
        self.view_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        self.main_paned.set_start_child(self.view_stack)

        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_child(self.drawing_area)
        self.view_stack.add_named(self.scrolled_window, "pdf_view")
        
        welcome_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                              valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        welcome_icon = Gtk.Image.new_from_icon_name("org.pepeg.GnomeSign")
        welcome_icon.set_pixel_size(128)
        self.welcome_label = Gtk.Label()
        self.welcome_label.set_markup(f"<span size='large'>{app._('welcome_prompt')}</span>")
        self.welcome_button = Gtk.Button.new_with_label(app._("welcome_button"))
        self.welcome_button.get_style_context().add_class("suggested-action")
        welcome_box.append(welcome_icon)
        welcome_box.append(self.welcome_label)
        welcome_box.append(self.welcome_button)
        self.view_stack.add_named(welcome_box, "welcome_view")

        self._build_signature_panel()
        self.main_paned.set_end_child(self.signature_panel)
        self.signature_panel.set_visible(False)

        self._connect_signals()

    def _build_signature_panel(self):
        app = self.get_application()
        self.signature_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_start=12, margin_end=12, margin_top=12, margin_bottom=12, width_request=280)

        self.signature_panel.append(Gtk.Label(label=f"<b>{app._('sign_document')}</b>", use_markup=True, xalign=0))
        
        self.stamp_preview = Gtk.DrawingArea(height_request=120, vexpand=False)
        self.stamp_preview.get_style_context().add_class("view")
        self.signature_panel.append(self.stamp_preview)
        
        self.signature_panel.append(Gtk.Label(label=app._("select_certificate"), xalign=0))
        self.cert_combo = Gtk.ComboBoxText()
        self.signature_panel.append(self.cert_combo)

        self.signature_panel.append(Gtk.Label(label=app._("templates"), xalign=0))
        self.template_combo = Gtk.ComboBoxText()
        self.signature_panel.append(self.template_combo)
        
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.END, vexpand=True)
        self.sign_button_panel = Gtk.Button(label=app._("sign_document"))
        self.sign_button_panel.get_style_context().add_class("suggested-action")
        action_box.append(self.sign_button_panel)
        self.signature_panel.append(action_box)


    def _connect_signals(self):
        app = self.get_application()
        
        self.open_button.connect("clicked", lambda w: app.activate_action("open"))
        self.sign_button_panel.connect("clicked", lambda w: app.activate_action("sign"))

        self.prev_page_button.connect("clicked", app.on_prev_page_clicked)
        self.next_page_button.connect("clicked", app.on_next_page_clicked)
        self.page_entry_button.connect("clicked", app.on_jump_to_page_clicked)
        self.welcome_button.connect("clicked", lambda w: app.activate_action("open"))

        self.drawing_area.set_draw_func(self._draw_page_and_rect)
        self.drawing_area.connect("resize", self._on_drawing_area_resize)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self._on_drawing_area_clicked)
        self.drawing_area.add_controller(click_gesture)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", app.on_drag_begin)
        drag_gesture.connect("drag-update", app.on_drag_update)
        drag_gesture.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag_gesture)

        self.stamp_preview.set_draw_func(self._draw_stamp_preview)
        self.cert_combo.connect("changed", self._on_panel_cert_changed)
        self.template_combo.connect("changed", lambda w: self.stamp_preview.queue_draw())

    def _setup_drop_target(self):
        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_file_drop)
        self.add_controller(drop_target)

    def _on_drawing_area_clicked(self, gesture, n_press, x, y):
        app = self.get_application()
        if app.signature_rect:
            rect_for_drawing = self.get_signature_rect_for_drawing()
            if not (rect_for_drawing and rect_for_drawing.x <= x <= rect_for_drawing.x + rect_for_drawing.width and
                    rect_for_drawing.y <= y <= rect_for_drawing.y + rect_for_drawing.height):
                app.reset_signature_state()
        
    def _on_file_drop(self, target, value, x, y):
        app = self.get_application()
        file_list = value.get_files()
        if file_list and len(file_list) > 0:
            file_path = file_list[0].get_path()
            if file_path and file_path.lower().endswith('.pdf'):
                app.open_file_path(file_path)
                return True
        return False

    def update_ui(self, app):
        self.title_label.set_markup(f"<span weight='bold'>{app._('window_title')}</span>")
        self.welcome_label.set_markup(f"<span size='large'>{app._('welcome_prompt')}</span>")
        self.welcome_button.set_label(app._("welcome_button"))
        
        self.update_tooltips(app)
        self.update_header_bar_state(app)
        self._build_and_set_menu(app)
        self.drawing_area.queue_draw()
        if self.signature_panel.get_visible():
            self.update_signature_panel()
            
    def update_tooltips(self, app):
        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.prev_page_button.set_tooltip_text(app._("prev_page"))
        self.next_page_button.set_tooltip_text(app._("next_page"))
        self.page_entry_button.set_tooltip_text(app._("jump_to_page_title"))

    def update_header_bar_state(self, app):
        is_doc_loaded = app.doc is not None
        
        self.view_stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")

        self.title_label.set_markup(f"<span weight='bold'>{app._('window_title')}</span>")
        if is_doc_loaded:
            self.subtitle_label.set_text(os.path.basename(app.current_file_path))
            self.subtitle_label.set_visible(True)
        else:
            self.subtitle_label.set_text("")
            self.subtitle_label.set_visible(False)
            self.hide_signature_panel()
            
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.page_entry_button.set_sensitive(is_doc_loaded)
        if is_doc_loaded:
            self.page_entry_button.set_label(f"{app.current_page + 1} / {len(app.doc)}")
        else:
            self.page_entry_button.set_label("- / -")

    def _build_and_set_menu(self, app):
        menu = Gio.Menu()
        menu.append(app._("open_pdf"), "app.open")
        
        recent_files_menu = Gio.Menu.new()
        recent_files = app.config.get_recent_files()
        if recent_files:
            for file_path in recent_files:
                display_name = os.path.basename(file_path)
                action_with_param = f"app.open_recent('{file_path}')"
                recent_files_menu.append(display_name, action_with_param)
            menu.append_submenu(app._("open_recent"), recent_files_menu)

        settings_section = Gio.Menu()
        settings_section.append(app._("select_certificate"), "app.select_cert")
        settings_section.append(app._("edit_stamp_templates"), "app.edit_stamps")
        
        lang_submenu = Gio.Menu()
        lang_submenu.append("Idioma Español", "app.change_lang('es')")
        lang_submenu.append("English Language", "app.change_lang('en')")
        settings_section.append_submenu("Idioma / Language", lang_submenu)
        
        menu.append_section(None, settings_section)

        about_section = Gio.Menu()
        about_section.append(app._("about"), "app.about")
        menu.append_section(None, about_section)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        self.menu_button.set_popover(popover)
        
    def _on_drawing_area_resize(self, area, width, height):
        app = self.get_application()
        if app.page:
            app.display_pixbuf = None
        GLib.idle_add(self.adjust_scroll_and_viewport)

    def adjust_scroll_and_viewport(self):
        self.update_drawing_area_size_request()
        adj = self.scrolled_window.get_vadjustment()
        upper = adj.get_upper()
        page_size = adj.get_page_size()
        if adj.get_value() > upper - page_size:
            adj.set_value(upper - page_size)

    def update_drawing_area_size_request(self):
        app = self.get_application()
        if not app.page:
            self.drawing_area.set_size_request(-1, -1)
            return

        width = self.drawing_area.get_width()
        if width > 0 and app.page.rect.width > 0:
            target_h = width * (app.page.rect.height / app.page.rect.width)
            if abs(self.drawing_area.get_property("height-request") - int(target_h)) > 1:
                self.drawing_area.set_size_request(-1, int(target_h))

    def show_info_bar(self, text):
        self.info_label.set_text(text)
        self.info_bar.set_revealed(True)

    def show_signature_panel(self):
        self.update_signature_panel()
        self.signature_panel.set_visible(True)

    def hide_signature_panel(self):
        self.signature_panel.set_visible(False)
        self.drawing_area.queue_draw()

    def update_signature_panel(self):
        app = self.get_application()
        
        self.cert_combo.remove_all()
        cert_details = app.cert_manager.get_all_certificate_details()
        for i, cert in enumerate(cert_details):
            self.cert_combo.append(cert['path'], cert['subject_cn'])
            if cert['path'] == app.active_cert_path:
                self.cert_combo.set_active(i)

        self.template_combo.remove_all()
        templates = app.config.get_signature_templates()
        active_template_id = app.config.get_active_template_id()
        for i, template in enumerate(templates):
            self.template_combo.append(template['id'], template['name'])
            if template['id'] == active_template_id:
                self.template_combo.set_active(i)

        self.stamp_preview.queue_draw()

    def _on_panel_cert_changed(self, combo):
        app = self.get_application()
        path = combo.get_active_id()
        if path and path != app.active_cert_path:
            app.active_cert_path = path
            self.stamp_preview.queue_draw()
            self.drawing_area.queue_draw() 
            
    def _draw_stamp_preview(self, area, cr, width, h):
        app = self.get_application()
        if not app.active_cert_path: return
        
        cr.save()
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.paint()
        cr.rectangle(5, 5, width - 10, h - 10)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.fill()
        
        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
        if not password: return
        _, certificate = app.cert_manager.get_credentials(app.active_cert_path, password)
        if not certificate: return
        
        active_template_id = self.template_combo.get_active_id()
        template_obj = app.config.get_template_by_id(active_template_id)
        if not template_obj: return
        
        override_template = template_obj.get(f"template_{app.i18n.get_language()}", template_obj.get("template_en", ""))

        layout = PangoCairo.create_layout(cr)
        layout.set_width(Pango.units_from_double(width - 20))
        layout.set_alignment(Pango.Alignment.CENTER)
        markup_text = app.get_parsed_stamp_text(certificate, for_html=False, override_template=override_template)
        layout.set_markup(markup_text, -1)
        
        ink_rect, logical_rect = layout.get_pixel_extents()
        scale = min((width - 20) / logical_rect.width if logical_rect.width > 0 else 1, 
                    (h - 10) / logical_rect.height if logical_rect.height > 0 else 1, 1.0)
        
        final_w, final_h = logical_rect.width * scale, logical_rect.height * scale
        start_x, start_y = (width - final_w) / 2, (h - final_h) / 2
        
        cr.translate(start_x - (logical_rect.x * scale), start_y - (logical_rect.y * scale))
        cr.scale(scale, scale)
        cr.set_source_rgb(0, 0, 0)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    def get_signature_rect_for_drawing(self):
        app = self.get_application()
        if not app.signature_rect or not app.page:
            return None

        drawing_width = self.drawing_area.get_width()
        drawing_height = self.drawing_area.get_height()
        
        rel_x, rel_y, rel_w, rel_h = app.signature_rect
        
        abs_x = rel_x * drawing_width
        abs_y = rel_y * drawing_height
        abs_w = rel_w * drawing_width
        abs_h = rel_h * drawing_height
        
        return Gdk.Rectangle(x=int(abs_x), y=int(abs_y), width=int(abs_w), height=int(abs_h))

    def get_signature_rect_relative_to_page(self):
        app = self.get_application()
        if not app.signature_rect or not app.page: return None

        # Convert drawing area relative coords to page relative coords
        drawing_width = self.drawing_area.get_width()
        drawing_height = self.drawing_area.get_height()
        page_width = app.page.rect.width
        page_height = app.page.rect.height

        scale_w = page_width / drawing_width
        scale_h = page_height / drawing_height
        
        rel_x, rel_y, rel_w, rel_h = app.signature_rect
        
        page_rel_x = (rel_x * drawing_width * scale_w) / page_width
        page_rel_y = (rel_y * drawing_height * scale_h) / page_height
        page_rel_w = (rel_w * drawing_width * scale_w) / page_width
        page_rel_h = (rel_h * drawing_height * scale_h) / page_height

        return (page_rel_x, page_rel_y, page_rel_w, page_rel_h)


    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        app = self.get_application()
        
        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width
                matrix = fitz.Matrix(zoom, zoom)
                pix = app.page.get_pixmap(matrix=matrix, alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0)
            cr.paint()
        
        rect_to_draw = None
        if app.signature_rect:
             rect_to_draw = self.get_signature_rect_for_drawing()
        elif app.start_x != -1:
             rect_to_draw = Gdk.Rectangle(x=int(min(app.start_x, app.end_x)), y=int(min(app.start_y, app.end_y)),
                                          width=int(abs(app.end_x-app.start_x)), height=int(abs(app.end_y-app.start_y)))
        
        if not rect_to_draw: return
        
        x, y, w, h = rect_to_draw.x, rect_to_draw.y, rect_to_draw.width, rect_to_draw.height
        
        cr.set_source_rgb(0.0, 0.5, 0.0)
        cr.set_line_width(1.5)
        cr.rectangle(x, y, w, h)
        cr.stroke_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8)
        cr.fill()
        
        if w > 20 and h > 20 and app.active_cert_path and app.signature_rect:
            password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
            if not password: return
            _, certificate = app.cert_manager.get_credentials(app.active_cert_path, password)
            if not certificate: return
            
            cr.save()
            
            layout = PangoCairo.create_layout(cr)
            layout.set_width(Pango.units_from_double(w - 10))
            layout.set_alignment(Pango.Alignment.CENTER)
            
            markup_text = app.get_parsed_stamp_text(certificate, for_html=False)
            layout.set_markup(markup_text, -1)

            ink_rect, logical_rect = layout.get_pixel_extents()
            
            available_width = w - 10
            available_height = h - 10
            scale_x = available_width / logical_rect.width if logical_rect.width > 0 else 1
            scale_y = available_height / logical_rect.height if logical_rect.height > 0 else 1
            scale = min(scale_x, scale_y, 1.0) 
            
            final_width = logical_rect.width * scale
            final_height = logical_rect.height * scale
            
            final_x = x + (w - final_width) / 2
            final_y = y + (h - final_height) / 2
            
            cr.translate(final_x - (logical_rect.x * scale), final_y - (logical_rect.y * scale))
            cr.scale(scale, scale)

            cr.set_source_rgb(0, 0, 0)
            PangoCairo.show_layout(cr, layout)
            
            cr.restore()