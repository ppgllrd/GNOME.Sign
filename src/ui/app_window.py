import gi
import os
gi.require_version("Gtk", "4.0")
gi.require_version("Secret", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, Gio, Secret, GLib, Pango, PangoCairo
from certificate_manager import KEYRING_SCHEMA
import fitz 
from gi.repository import GdkPixbuf

class AppWindow(Gtk.ApplicationWindow):
    """The main window of the application, responsible for building the UI."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        app = self.get_application()
        self.set_default_size(800, 600)
        self.set_title(app._("window_title"))
        self._build_ui()

    def _build_ui(self):
        """Constructs the user interface."""
        self.header_bar = Gtk.HeaderBar()
        self.set_titlebar(self.header_bar)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.title_label = Gtk.Label()
        self.title_label.set_markup(f"<span weight='bold'>{self.get_application()._('window_title')}</span>")
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
        
        self.sign_button = Gtk.Button.new_from_icon_name("mail-signed-symbolic")
        self.header_bar.pack_end(self.sign_button)

        self.cert_button = Gtk.Button.new_from_icon_name("document-properties-symbolic")
        self.header_bar.pack_end(self.cert_button)
        
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_child(self.drawing_area)
        self.set_child(self.scrolled_window)

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
        self.sign_button.set_tooltip_text(app._("sign_document"))

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
            # If no active cert or active cert not found, default to first one
            app.active_cert_path = cert_details[0]['path']
            self.cert_button.set_tooltip_text(app._("active_certificate").format(cert_details[0]['subject_cn']))


    def update_header_bar_state(self, app):
        """Updates the title, subtitle, and sensitivity of header bar controls."""
        is_doc_loaded = app.doc is not None
        
        self.title_label.set_markup(f"<span weight='bold'>{app._('window_title')}</span>")
        if is_doc_loaded:
            self.subtitle_label.set_text(os.path.basename(app.current_file_path))
            self.subtitle_label.set_visible(True)
        else:
            self.subtitle_label.set_text("")
            self.subtitle_label.set_visible(False)
            
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
        settings_section.append(app._("load_certificate"), "app.load_cert")
        settings_section.append(app._("select_certificate"), "app.select_cert")
        settings_section.append(app._("edit_stamp_templates"), "app.edit_stamps")
        settings_section.append(app._("change_language"), "app.change_lang")
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
            
            layout = PangoCairo.create_layout(cr)
            layout.set_width(Pango.units_from_double(w - 10))
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_line_spacing(1.2)

            markup_text = app.get_parsed_stamp_text(certificate, for_html=False)
            layout.set_markup(markup_text, -1)

            _, text_height = layout.get_pixel_size()
            text_y = y + (h - text_height) / 2
            
            cr.move_to(x + 5, text_y)
            cr.set_source_rgb(0, 0, 0)
            PangoCairo.show_layout(cr, layout)