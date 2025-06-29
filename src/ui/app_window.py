import gi
import os
import re
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Secret", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Adw, Gdk, Gio, Secret, GLib, Pango, PangoCairo
from certificate_manager import KEYRING_SCHEMA
import fitz 
from gi.repository import GdkPixbuf

class AppWindow(Adw.ApplicationWindow):
    """The main window of the application, responsible for building the UI."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        app = self.get_application()
        self.set_default_size(800, 600)
        self.set_icon_name("org.pepeg.GnomeSign")
        self._build_ui()

    def _build_ui(self):
        """Constructs the user interface."""
        app = self.get_application()
        
        self.header_bar = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title=app._("window_title"))
        self.header_bar.set_title_widget(self.title_widget)
        
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
        
        self.sign_button = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        self.header_bar.pack_end(self.sign_button)

        self.cert_button = Gtk.Button.new_from_icon_name("dialog-password-symbolic")
        self.header_bar.pack_end(self.cert_button)
        
        # Main Content Box
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.append(self.header_bar)

        # --- Main Content Stack ---
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        main_content.append(self.stack)
        
        self.set_content(main_content)

        # PDF View
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_child(self.drawing_area)
        self.stack.add_named(self.scrolled_window, "pdf_view")
        
        # Welcome View
        welcome_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                              valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
                              hexpand=True, vexpand=True)
        welcome_icon = Gtk.Image.new_from_icon_name("org.pepeg.GnomeSign")
        welcome_icon.set_pixel_size(128)
        self.welcome_label = Gtk.Label()
        self.welcome_button = Gtk.Button.new()
        self.welcome_button.get_style_context().add_class("suggested-action")
        welcome_box.append(welcome_icon)
        welcome_box.append(self.welcome_label)
        welcome_box.append(self.welcome_button)
        self.stack.add_named(welcome_box, "welcome_view")
        
        self._connect_signals()

    def _connect_signals(self):
        """Connects widget signals to application actions or internal handlers."""
        app = self.get_application()
        
        self.open_button.connect("clicked", lambda w: app.activate_action("open"))
        self.sign_button.connect("clicked", lambda w: app.activate_action("sign"))
        self.cert_button.connect("clicked", lambda w: app.activate_action("select_cert"))
        self.prev_page_button.connect("clicked", app.on_prev_page_clicked)
        self.next_page_button.connect("clicked", app.on_next_page_clicked)
        self.page_entry_button.connect("clicked", app.on_jump_to_page_clicked)

        self.drawing_area.set_draw_func(self._draw_page_and_rect)
        self.drawing_area.connect("resize", self._on_drawing_area_resize)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", app.on_drag_begin)
        drag_gesture.connect("drag-update", app.on_drag_update)
        drag_gesture.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag_gesture)

    def update_ui(self, app):
        """Updates all UI elements to reflect the application's state."""
        self.title_widget.set_title(app._('window_title'))
        
        # --- Lógica de la pantalla de bienvenida ---
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        if certs_exist:
            self.welcome_label.set_markup(f"<span size='large'>{app._('welcome_prompt_cert_ok')}</span>")
            self.welcome_button.set_label(app._("welcome_button"))
            if hasattr(self.welcome_button, "handler_id") and self.welcome_button.handler_id:
                self.welcome_button.disconnect(self.welcome_button.handler_id)
            self.welcome_button.handler_id = self.welcome_button.connect("clicked", lambda w: app.activate_action("open"))
        else:
            self.welcome_label.set_markup(f"<span size='large'>{app._('welcome_prompt_no_cert')}</span>")
            self.welcome_button.set_label(app._("welcome_button_no_cert"))
            if hasattr(self.welcome_button, "handler_id") and self.welcome_button.handler_id:
                self.welcome_button.disconnect(self.welcome_button.handler_id)
            self.welcome_button.handler_id = self.welcome_button.connect("clicked", lambda w: app.activate_action("load_cert"))

        self.update_tooltips(app)
        self.update_cert_button_state(app)
        self.update_header_bar_state(app)
        self._build_and_set_menu(app)
        self.drawing_area.queue_draw()
            
    def update_tooltips(self, app):
        """Updates the tooltips for the header bar buttons."""
        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.prev_page_button.set_tooltip_text(app._("prev_page"))
        self.next_page_button.set_tooltip_text(app._("next_page"))
        self.page_entry_button.set_tooltip_text(app._("jump_to_page_title"))
        self.cert_button.set_tooltip_text(app._("select_certificate"))
        
        if app.signature_rect:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_sign"))
        else:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_select_area"))

    def update_cert_button_state(self, app):
        """Updates the state and tooltip of the certificate button."""
        cert_details = app.cert_manager.get_all_certificate_details()
        self.cert_button.set_sensitive(bool(cert_details))
        if not cert_details:
            app.active_cert_path = None
            self.cert_button.set_tooltip_text(app._("no_certificate_selected"))
            return

        active_cert_details = next((c for c in cert_details if c['path'] == app.active_cert_path), None)

        if active_cert_details:
            self.cert_button.set_tooltip_text(app._("active_certificate").format(active_cert_details['subject_cn']))
        else:
            if cert_details:
                app.active_cert_path = cert_details[0]['path']
                self.cert_button.set_tooltip_text(app._("active_certificate").format(cert_details[0]['subject_cn']))
            else:
                app.active_cert_path = None
                self.cert_button.set_tooltip_text(app._("no_certificate_selected"))


    def update_header_bar_state(self, app):
        """Updates the title, subtitle, and sensitivity of header bar controls."""
        is_doc_loaded = app.doc is not None
        
        self.stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")

        if is_doc_loaded:
            self.title_widget.set_subtitle(os.path.basename(app.current_file_path))
        else:
            self.title_widget.set_subtitle("")
            
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.page_entry_button.set_sensitive(is_doc_loaded)
        if is_doc_loaded:
            self.page_entry_button.set_label(f"{app.current_page + 1} / {len(app.doc)}")
        else:
            self.page_entry_button.set_label("- / -")

        self.sign_button.set_sensitive(is_doc_loaded and app.signature_rect is not None)

    def _build_and_set_menu(self, app):
        """Builds the main application menu."""
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

        sign_section = Gio.Menu()
        sign_section.append(app._("sign_document"), "app.sign")
        menu.append_section(None, sign_section)

        settings_section = Gio.Menu()
        settings_section.append(app._("select_certificate"), "app.select_cert")
        settings_section.append(app._("edit_stamp_templates"), "app.edit_stamps")
        menu.append_section(None, settings_section)

        # Language Radio Buttons Section
        lang_section = Gio.Menu()
        lang_section.append("Idioma Español", "app.change_lang::es")
        lang_section.append("English Language", "app.change_lang::en")
        menu.append_section(None, lang_section)

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

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        """The main draw function for the drawing area."""
        app = self.get_application()
        
        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width
                matrix = fitz.Matrix(zoom, zoom)
                pix = app.page.get_pixmap(matrix=matrix, alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0)
            cr.paint()
        
        rect_to_draw = app.signature_rect or ((min(app.start_x, app.end_x), min(app.start_y, app.end_y), abs(app.end_x - app.start_x), abs(app.end_y - app.start_y)) if app.start_x != -1 else None)
        if not rect_to_draw: return
        
        x, y, w, h = rect_to_draw
        
        cr.set_source_rgb(0.0, 0.5, 0.0)
        cr.set_line_width(1.5)
        cr.rectangle(x, y, w, h)
        cr.stroke_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8)
        cr.fill()
        
        if w > 20 and h > 20 and app.active_cert_path:
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