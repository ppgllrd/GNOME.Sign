# ui/app_window.py
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("PangoCairo", "1.0"); gi.require_version('GdkPixbuf', '2.0'); gi.require_version('Secret', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango, PangoCairo, GdkPixbuf, Secret
import os, fitz

class AppWindow(Adw.ApplicationWindow):
    """The main application window, containing the header bar, sidebar, and content area."""
    def __init__(self, **kwargs):
        """Initializes the main application window and its UI."""
        super().__init__(**kwargs)
        from .components.sidebar import Sidebar; from .components.welcome import WelcomeView
        self.active_toasts = []
        self.set_default_size(900, 700); self.set_icon_name("org.pepeg.GnomeSign")
        self.set_hide_on_close(False)
        self._build_ui(Sidebar, WelcomeView); self._connect_signals()

    def _build_ui(self, Sidebar, WelcomeView):
        """Constructs the main UI layout and widgets."""
        app = self.get_application()
        self.toast_overlay = Adw.ToastOverlay.new(); self.set_content(self.toast_overlay)
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.toast_overlay.set_child(self.main_box)
        self.header_bar = Adw.HeaderBar(); self.main_box.append(self.header_bar)
        self.flap = Adw.Flap(); self.main_box.append(self.flap)
        self.sidebar_button = Gtk.ToggleButton(icon_name="view-list-symbolic"); self.header_bar.pack_start(self.sidebar_button)
        self.sidebar_button.set_tooltip_text(app._("toggle_sidebar_tooltip"))
        self.title_widget = Adw.WindowTitle(title=app._("window_title")); self.header_bar.set_title_widget(self.title_widget)
        self.open_button = Gtk.Button(icon_name="document-open-symbolic"); self.header_bar.pack_start(self.open_button)
        nav_box = Gtk.Box(spacing=6); nav_box.get_style_context().add_class("linked")
        self.prev_page_button = Gtk.Button(icon_name="go-previous-symbolic"); self.page_entry_button = Gtk.Button(label="- / -"); self.page_entry_button.get_style_context().add_class("flat")
        self.next_page_button = Gtk.Button(icon_name="go-next-symbolic"); nav_box.append(self.prev_page_button); nav_box.append(self.page_entry_button); nav_box.append(self.next_page_button)
        self.header_bar.pack_start(nav_box)
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic"); self.header_bar.pack_end(self.menu_button)
        self.certs_button = Gtk.Button(icon_name="dialog-password-symbolic"); self.header_bar.pack_end(self.certs_button)
        self.sign_button = Gtk.Button(icon_name="document-edit-symbolic"); self.header_bar.pack_end(self.sign_button)
        self.sidebar = Sidebar(); self.flap.set_flap(self.sidebar)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, vexpand=True); self.flap.set_content(self.stack)
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow(); self.scrolled_window.set_property("hscrollbar-policy", Gtk.PolicyType.NEVER); self.scrolled_window.set_property("vscrollbar-policy", Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_child(self.drawing_area); self.stack.add_named(self.scrolled_window, "pdf_view")
        self.welcome_view = WelcomeView(); self.stack.add_named(self.welcome_view, "welcome_view")

    def _connect_signals(self):
        """Connects UI element signals to their corresponding handlers."""
        app = self.get_application()
        self.open_button.connect("clicked", lambda w: app.activate_action("open")); self.sign_button.connect("clicked", lambda w: app.activate_action("sign"))
        self.certs_button.connect("clicked", lambda w: app.activate_action("manage_certs"))
        self.prev_page_button.connect("clicked", app.on_prev_page_clicked); self.next_page_button.connect("clicked", app.on_next_page_clicked)
        self.page_entry_button.connect("clicked", app.on_jump_to_page_clicked)
        self.sidebar_button.connect("toggled", self.on_sidebar_toggled); self.flap.connect("notify::reveal-flap", self.on_flap_reveal_changed)
        self.sidebar.connect("page-selected", lambda sb, page_num: app.display_page(page_num))
        self.drawing_area.set_draw_func(self._draw_page_and_rect); self.drawing_area.connect("resize", self._on_drawing_area_resize)
        drag = Gtk.GestureDrag.new(); drag.connect("drag-begin", app.on_drag_begin); drag.connect("drag-update", app.on_drag_update); drag.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag)
        drop_target = Gtk.DropTarget.new(type=Gio.File, actions=Gdk.DragAction.COPY); drop_target.connect("drop", self._on_file_drop)
        self.add_controller(drop_target)
        
    def _on_file_drop(self, target, value, x, y):
        """Handles a file drop event, opening the PDF if it's a valid file."""
        app = self.get_application()
        file = value.get_file()
        if file and file.get_path().lower().endswith(".pdf"): app.open_file_path(file.get_path()); return True
        return False
    
    def on_sidebar_toggled(self, button):
        """Toggles the visibility of the sidebar flap when the button is clicked."""
        self.flap.set_reveal_flap(button.get_active())

    def on_flap_reveal_changed(self, flap, param):
        """Synchronizes the sidebar toggle button's state with the flap's visibility."""
        self.sidebar_button.set_active(flap.get_reveal_flap())

    def update_ui(self, app):
        """Refreshes the entire window UI based on the application's current state."""
        self.welcome_view.update_ui(app); self.update_header_bar_state(app)
        self._build_and_set_menu(app); self.drawing_area.queue_draw()
            
    def update_header_bar_state(self, app):
        """Updates the state (sensitivity, labels, tooltips) of the header bar widgets."""
        is_doc_loaded = app.doc is not None
        self.stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")
        self.sidebar_button.set_sensitive(is_doc_loaded)
        if not is_doc_loaded and self.flap.get_reveal_flap(): self.flap.set_reveal_flap(False)

        if is_doc_loaded:
            self.title_widget.set_subtitle(os.path.basename(app.current_file_path) if app.current_file_path else "")
        else:
            self.title_widget.set_subtitle("")
            
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.page_entry_button.set_sensitive(is_doc_loaded)
        if is_doc_loaded: self.page_entry_button.set_label(f"{app.current_page + 1} / {len(app.doc)}")
        else: self.page_entry_button.set_label("- / -")

        can_sign = is_doc_loaded and app.signature_rect and app.active_cert_path
        self.sign_button.set_sensitive(can_sign)
        if can_sign:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_sign"))
        elif not app.active_cert_path:
            self.sign_button.set_tooltip_text(app._("no_cert_selected_error"))
        else:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_select_area"))

        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.prev_page_button.set_tooltip_text(app._("prev_page"))
        self.next_page_button.set_tooltip_text(app._("next_page"))
        self.page_entry_button.set_tooltip_text(app._("jump_to_page_title"))
        self.sidebar_button.set_tooltip_text(app._("toggle_sidebar_tooltip"))

        if app.active_cert_path:
            cert_details = next((c for c in app.cert_manager.get_all_certificate_details() if c['path'] == app.active_cert_path), None)
            if cert_details:
                self.certs_button.set_tooltip_text(cert_details['subject_cn'])
            else:
                self.certs_button.set_tooltip_text(app._("manage_certificates_tooltip"))

    def _build_and_set_menu(self, app):
        """Creates and sets the main application menu, including recent files."""
        menu = Gio.Menu.new(); menu.append(app._("open_pdf"), "app.open")
        recent_files = app.config.get_recent_files()
        if recent_files:
            recent_menu = Gio.Menu.new()
            for file_path in recent_files:
                action_string = f"app.open_recent({GLib.shell_quote(file_path)})"
                recent_menu.append(os.path.basename(file_path), action_string)
            menu.append_submenu(app._("open_recent"), recent_menu)
        menu.append_section(None, Gio.Menu.new()); menu.append(app._("sign_document"), "app.sign")
        menu.append_section(None, Gio.Menu.new()); menu.append(app._("edit_stamp_templates"), "app.edit_stamps")
        menu.append(app._("preferences"), "app.preferences"); menu.append_section(None, Gio.Menu.new())
        menu.append(app._("about"), "app.about"); self.menu_button.set_menu_model(menu)
        
    def _on_drawing_area_resize(self, area, width, height):
        """Handles the resize event for the PDF drawing area, triggering a redraw."""
        app = self.get_application();
        if app.page: app.display_pixbuf = None
        GLib.idle_add(self.adjust_scroll_and_viewport)

    def adjust_scroll_and_viewport(self):
        """Adjusts the scrollbar position after a resize to keep the content visible."""
        self.update_drawing_area_size_request()
        adj = self.scrolled_window.get_vadjustment()
        if adj:
            upper = adj.get_upper(); page_size = adj.get_page_size()
            if upper > page_size and adj.get_value() > upper - page_size: adj.set_value(upper - page_size)

    def update_drawing_area_size_request(self):
        """Requests a new size for the drawing area to maintain the PDF's aspect ratio."""
        app = self.get_application()
        if not app.page: self.drawing_area.set_size_request(-1, -1); return
        width = self.drawing_area.get_width()
        if width > 0 and app.page.rect.width > 0:
            target_h = width * (app.page.rect.height / app.page.rect.width)
            if abs(self.drawing_area.get_property("height-request") - int(target_h)) > 1: self.drawing_area.set_size_request(-1, int(target_h))

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        """Draw callback for the main canvas; renders the PDF page and the signature rectangle."""
        app = self.get_application()
        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width; pix = app.page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0); cr.paint()
        rect_to_draw = app.signature_rect or ((min(app.start_x, app.end_x), min(app.start_y, app.end_y), abs(app.end_x - app.start_x), abs(app.end_y - app.start_y)) if app.start_x != -1 else None)
        if not rect_to_draw: return
        x, y, w, h = rect_to_draw
        if w < 5 or h < 5:
            cr.set_source_rgba(0.0, 0.5, 0.0, 0.5); cr.set_line_width(1.0); cr.rectangle(x, y, w, h); cr.fill(); return
        cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.rectangle(x, y, w, h); cr.stroke_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8); cr.fill()
        if w > 20 and h > 20 and app.active_cert_path:
            password = Secret.password_lookup_sync(app.cert_manager.KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
            if not password: return
            _, certificate = app.cert_manager.get_credentials(app.active_cert_path, password)
            if not certificate: return
            cr.save(); layout = PangoCairo.create_layout(cr)
            layout.set_width(Pango.units_from_double(w - 10)); layout.set_alignment(Pango.Alignment.CENTER)
            markup_text = app.get_parsed_stamp_text(certificate); layout.set_markup(markup_text, -1)
            ink_rect, logical_rect = layout.get_pixel_extents()
            scale = min((w - 10) / logical_rect.width if logical_rect.width > 0 else 1, (h - 10) / logical_rect.height if logical_rect.height > 0 else 1, 1.0)
            final_width, final_height = logical_rect.width * scale, logical_rect.height * scale
            final_x, final_y = x + (w - final_width) / 2, y + (h - final_height) / 2
            cr.translate(final_x - (logical_rect.x * scale), final_y - (logical_rect.y * scale)); cr.scale(scale, scale)
            cr.set_source_rgb(0, 0, 0); PangoCairo.show_layout(cr, layout); cr.restore()
            
    def _on_toast_dismissed(self, toast):
        """
        Callback for a toast's 'dismissed' signal.
        This is the equivalent of 'dismissed_cb' in the C example. Its only job
        is to remove our reference to the toast, allowing garbage collection.
        """
        if toast in self.active_toasts:
            self.active_toasts.remove(toast)

    def show_toast(self, text, button_label=None, callback=None, timeout=4):
        """
        Displays a short-lived notification toast, correctly managing its lifecycle
        by holding a reference and using a manual GLib timer, as deduced from
        the Adwaita source code.
        """
        toast = Adw.Toast.new(text)
        toast.connect("dismissed", self._on_toast_dismissed)

        if button_label and callback:
            toast.set_button_label(button_label)
            def on_button_clicked(t):
                t.dismiss() 
                callback()
            toast.connect("button-clicked", on_button_clicked)
        elif timeout > 0:
            GLib.timeout_add_seconds(timeout, lambda: toast.dismiss() or GLib.SOURCE_REMOVE)

        self.active_toasts.append(toast)
        self.toast_overlay.add_toast(toast)

    
