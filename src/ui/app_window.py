# ui/app_window.py
import gi
import os # <--- CORRECCIÓN DE IMPORTACIÓN
gi.require_version("Gtk", "4.0")
gi.require_version("Secret", "1") # <--- CORRECCIÓN DE IMPORTACIÓN
from gi.repository import Gtk, Gdk, Gio, Secret, GLib, Pango, PangoCairo # <--- CORRECCIÓN DE IMPORTACIÓN
from certificate_manager import KEYRING_SCHEMA # <--- CORRECCIÓN DE IMPORTACIÓN
import fitz # Needed for Matrix
from gi.repository import GdkPixbuf # Needed for Pixbuf creation

class AppWindow(Gtk.ApplicationWindow):
    """The main window of the application, responsible for building the UI."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        app = self.get_application()
        self.set_title(app._("window_title"))
        self.set_default_size(800, 600)

        self._build_ui()

    def _build_ui(self):
        """Constructs the user interface."""
        self.header_bar = Gtk.HeaderBar()
        self.set_titlebar(self.header_bar)
        
        # --- Left side buttons ---
        self.open_button = Gtk.Button.new_from_icon_name("document-open-symbolic")
        self.header_bar.pack_start(self.open_button)
        
        self.prev_page_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.header_bar.pack_start(self.prev_page_button)
        
        self.next_page_button = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.header_bar.pack_start(self.next_page_button)

        # --- Right side buttons ---
        self.menu_button = Gtk.MenuButton.new()
        self.menu_button.set_icon_name("open-menu-symbolic")
        self.header_bar.pack_end(self.menu_button)
        
        self.sign_button = Gtk.Button.new_from_icon_name("mail-signed-symbolic")
        self.header_bar.pack_end(self.sign_button)

        self.cert_button = Gtk.Button.new_from_icon_name("document-properties-symbolic")
        self.header_bar.pack_end(self.cert_button)
        
        # --- Drawing Area ---
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_child(self.drawing_area)
        self.set_child(scrolled_window)

        self._connect_signals()

    def _connect_signals(self):
        """Connects widget signals to application actions or internal handlers."""
        app = self.get_application()
        
        self.open_button.connect("clicked", lambda w: app.activate_action("open"))
        self.sign_button.connect("clicked", lambda w: app.activate_action("sign"))
        self.cert_button.connect("clicked", app.on_cert_button_clicked)
        self.prev_page_button.connect("clicked", app.on_prev_page_clicked)
        self.next_page_button.connect("clicked", app.on_next_page_clicked)

        self.drawing_area.set_draw_func(self._draw_page_and_rect)
        self.drawing_area.connect("resize", self._on_drawing_area_resize)

        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", app.on_drag_begin)
        drag_gesture.connect("drag-update", app.on_drag_update)
        drag_gesture.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag_gesture)

    def update_ui(self, app):
        """Updates all UI elements to reflect the application's state."""
        self.update_title(app)
        self.update_tooltips(app)
        self.update_cert_button_state(app)
        self.update_navigation_sensitivity(app)
        self._build_and_set_menu(app)
        self.drawing_area.queue_draw()

    def update_title(self, app):
        """Updates the window title."""
        if app.doc:
            title = f"{app._('window_title')} - {os.path.basename(app.current_file_path)} ({app.current_page + 1}/{len(app.doc)})"
            self.set_title(title)
        else:
            self.set_title(app._("window_title"))
            
    def update_tooltips(self, app):
        """Updates the tooltips for the header bar buttons."""
        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.prev_page_button.set_tooltip_text(app._("prev_page"))
        self.next_page_button.set_tooltip_text(app._("next_page"))
        self.sign_button.set_tooltip_text(app._("sign_document"))

    def update_cert_button_state(self, app):
        """Updates the state and tooltip of the certificate button."""
        cert_map = app.cert_manager.get_all_display_names(KEYRING_SCHEMA)
        self.cert_button.set_sensitive(bool(cert_map))
        if not cert_map:
            app.active_cert_path = None
            self.cert_button.set_tooltip_text(app._("no_certificate_selected"))
            return

        if app.active_cert_path and app.active_cert_path in cert_map.values():
            active_name = next((name for name, path in cert_map.items() if path == app.active_cert_path), "Unknown")
            self.cert_button.set_tooltip_text(app._("active_certificate").format(active_name))
        else:
            if cert_map:
                first_name, first_path = list(cert_map.items())[0]
                app.active_cert_path = first_path
                self.cert_button.set_tooltip_text(app._("active_certificate").format(first_name))

    def update_navigation_sensitivity(self, app):
        """Updates the sensitivity of the navigation buttons."""
        is_doc_loaded = app.doc is not None
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.sign_button.set_sensitive(is_doc_loaded and app.signature_rect is not None)

    def _build_and_set_menu(self, app):
        """Builds the main application menu."""
        
        menu = Gio.Menu()
        
        #  Files Submenu
        recent_files_menu = Gio.Menu.new()
        recent_files = app.config.get_recent_files()
        for i, file_path in enumerate(recent_files):
            display_name = os.path.basename(file_path)
            action_with_param = f"app.open_recent('{file_path}')"
            recent_files_menu.append(display_name, action_with_param)
            
        recent_submenu_item = Gio.MenuItem.new_submenu(app._("open_recent"), recent_files_menu)
        
        # Main Actions
        main_section = Gio.Menu()
        main_section.append(app._("open_pdf"), "app.open")
        main_section.append_item(recent_submenu_item)
        menu.append_section(None, main_section)

        # Sign Actions
        sign_section = Gio.Menu()
        sign_section.append(app._("sign_document"), "app.sign")
        menu.append_section(None, sign_section)

        # Settings
        settings_section = Gio.Menu()
        settings_section.append(app._("load_certificate"), "app.load_cert")
        settings_section.append(app._("change_language"), "app.change_lang")
        menu.append_section(None, settings_section)

        # About
        about_section = Gio.Menu()
        about_section.append(app._("about"), "app.about")
        menu.append_section(None, about_section)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        self.menu_button.set_popover(popover)
        
    def _on_drawing_area_resize(self, area, width, height):
        """Handles the resize event of the drawing area."""
        app = self.get_application()
        if app.page:
            app.display_pixbuf = None
            if app.page.rect.width > 0:
                target_h = width * (app.page.rect.height / app.page.rect.width)
                area.set_size_request(-1, int(target_h))

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        """The main draw function for the drawing area."""
        app = self.get_application()
        
        # Draw the PDF page
        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width
                matrix = fitz.Matrix(zoom, zoom)
                pix = app.page.get_pixmap(matrix=matrix, alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0)
            cr.paint()
        
        # Draw the signature rectangle preview
        rect_to_draw = app.signature_rect or ((min(app.start_x, app.end_x), min(app.start_y, app.end_y), abs(app.end_x - app.start_x), abs(app.end_y - app.start_y)) if app.start_x != -1 else None)
        if not rect_to_draw: return
        x, y, w, h = rect_to_draw
        cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.rectangle(x, y, w, h); cr.stroke_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8); cr.fill()
        
        # Draw the text preview inside the rectangle
        if w > 20 and h > 20 and app.active_cert_path:
            password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
            if not password: return
            _, certificate = app.cert_manager.get_credentials(app.active_cert_path, password)
            if not certificate: return
            layout = PangoCairo.create_layout(cr)
            layout.set_width(Pango.units_from_double(w - 10))
            layout.set_alignment(Pango.Alignment.CENTER)
            font_size_main = max(7, min(h / 4.5, w / 18)); font_size_small = font_size_main * 0.85
            signer_cn = certificate.subject.rfc4514_string().split('CN=')[1].split(',')[0]
            current_date = app.get_formatted_date()
            markup_text = f"<span font_size='{font_size_small}pt'>{app._('digitally_signed_by')}</span>\n<b><span font_size='{font_size_main}pt'>{signer_cn}</span></b>\n<span font_size='{font_size_small * 0.9}pt'>{app._('date')} {current_date}</span>"
            layout.set_markup(markup_text, -1)
            _, text_height = layout.get_pixel_size()
            cr.move_to(x + 5, y + (h - text_height) / 2)
            cr.set_source_rgb(0, 0, 0); PangoCairo.show_layout(cr, layout)
