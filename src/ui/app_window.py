# ui/app_window.py

import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("PangoCairo", "1.0"); gi.require_version('GdkPixbuf', '2.0'); gi.require_version('Secret', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, GdkPixbuf, Secret
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
        
        # Main vertical box that will hold the HeaderBar and the content Flap.
        self.view_stacker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.header_bar = Adw.HeaderBar()
        self.view_stacker.append(self.header_bar)
        
        # The Adw.Banner for signature notifications.
        self.signature_banner = Adw.Banner.new("")
        self.signature_banner.set_revealed(False)
        self.view_stacker.append(self.signature_banner)
        
        self.flap = Adw.Flap()
        self.view_stacker.append(self.flap)
        
        # Adw.ToastOverlay wraps the main view stacker.
        self.toast_overlay = Adw.ToastOverlay.new()
        self.toast_overlay.set_child(self.view_stacker)
        self.set_content(self.toast_overlay)

        # --- HeaderBar Content ---
        self.sidebar_button = Gtk.ToggleButton(icon_name="view-list-symbolic")
        self.sidebar_button.set_tooltip_text(app._("toggle_sidebar_tooltip"))
        self.header_bar.pack_start(self.sidebar_button)
        
        self.title_widget = Adw.WindowTitle(title=app._("window_title"))
        self.header_bar.set_title_widget(self.title_widget)
        
        self.open_button = Gtk.Button(icon_name="document-open-symbolic")
        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.header_bar.pack_start(self.open_button)
        
        nav_box = Gtk.Box(spacing=6); nav_box.get_style_context().add_class("linked")
        self.prev_page_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.page_entry_button = Gtk.Button(label="- / -")
        self.page_entry_button.get_style_context().add_class("flat")
        self.next_page_button = Gtk.Button(icon_name="go-next-symbolic")
        nav_box.append(self.prev_page_button)
        nav_box.append(self.page_entry_button)
        nav_box.append(self.next_page_button)
        self.header_bar.pack_start(nav_box)
        
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.header_bar.pack_end(self.menu_button)
        
        self.show_sigs_button = Gtk.Button(icon_name="security-high-symbolic")
        self.show_sigs_button.set_visible(False)
        self.show_sigs_button.set_tooltip_text(app._("show_signatures_tooltip"))
        self.header_bar.pack_end(self.show_sigs_button)
        
        self.certs_button = Gtk.Button(icon_name="dialog-password-symbolic")
        self.header_bar.pack_end(self.certs_button)
        
        self.sign_button = Gtk.Button(icon_name="document-edit-symbolic")
        self.header_bar.pack_end(self.sign_button)
        
        # --- Flap and Content Stack ---
        self.sidebar = Sidebar(); self.flap.set_flap(self.sidebar)
        
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, vexpand=True)
        self.flap.set_content(self.stack)
        
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_property("hscrollbar-policy", Gtk.PolicyType.NEVER)
        self.scrolled_window.set_property("vscrollbar-policy", Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_child(self.drawing_area)
        self.stack.add_named(self.scrolled_window, "pdf_view")
        
        self.welcome_view = WelcomeView()
        self.stack.add_named(self.welcome_view, "welcome_view")

    def _connect_signals(self):
        """Connects UI element signals to their corresponding handlers."""
        app = self.get_application()
        self.open_button.connect("clicked", lambda w: app.activate_action("open"))
        self.sign_button.connect("clicked", lambda w: app.activate_action("sign"))
        self.certs_button.connect("clicked", lambda w: app.activate_action("manage_certs"))
        
        self.show_sigs_button.connect("clicked", lambda w: app.activate_action("show_signatures"))
        
        self.signature_banner.connect("button-clicked", lambda w: app.activate_action("show_signatures"))
        
        self.prev_page_button.connect("clicked", app.on_prev_page_clicked)
        self.next_page_button.connect("clicked", app.on_next_page_clicked)
        self.page_entry_button.connect("clicked", app.on_jump_to_page_clicked)
        self.sidebar_button.connect("toggled", self.on_sidebar_toggled)
        self.flap.connect("notify::reveal-flap", self.on_flap_reveal_changed)
        self.sidebar.connect("page-selected", lambda sb, page_num: app.display_page(page_num))
        self.drawing_area.set_draw_func(self._draw_page_and_rect)
        self.drawing_area.connect("resize", self._on_drawing_area_resize)
        
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", app.on_drag_begin)
        drag.connect("drag-update", app.on_drag_update)
        drag.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_drawing_area_click)
        self.drawing_area.add_controller(click_gesture)

        drop_target = Gtk.DropTarget.new(type=Gio.File, actions=Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_file_drop)
        self.add_controller(drop_target)
        
    def show_signature_info(self, count):
        """Shows the banner for existing signatures."""
        app = self.get_application()
        self.signature_banner.set_title(app._("signatures_found_toast").format(count))
        self.signature_banner.set_button_label(app._("go_to_signatures"))
        self.signature_banner.set_revealed(True)

    def hide_signature_info(self):
        """Hides the banner for existing signatures."""
        self.signature_banner.set_revealed(False)
        
    def _on_file_drop(self, target, value, x, y):
        """Handles a file drop event, opening the PDF if it's a valid file."""
        app = self.get_application()
        file = value.get_file()
        if file and file.get_path().lower().endswith(".pdf"):
            app.open_file_path(file.get_path())
            return True
        return False
    
    def _on_drawing_area_click(self, gesture, n_press, x, y):
        """Handles a click on the drawing area to clear any highlights."""
        app = self.get_application()
        if app.highlight_rect:
            app.highlight_rect = None
            self.drawing_area.queue_draw()

    def on_sidebar_toggled(self, button):
        """Toggles the visibility of the sidebar flap when the button is clicked."""
        self.flap.set_reveal_flap(button.get_active())

    def on_flap_reveal_changed(self, flap, param):
        """Synchronizes the sidebar toggle button's state with the flap's visibility."""
        self.sidebar_button.set_active(flap.get_reveal_flap())

    def update_ui(self, app):
        """Refreshes the entire window UI based on the application's current state."""
        self.welcome_view.update_ui(app)
        self.update_header_bar_state(app)
        self._build_and_set_menu(app)
        self.drawing_area.queue_draw()
            
    def update_header_bar_state(self, app):
        """Updates the state (sensitivity, labels, tooltips) of the header bar widgets."""
        is_doc_loaded = app.doc is not None
        self.stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")
        self.sidebar_button.set_sensitive(is_doc_loaded)
        if not is_doc_loaded and self.flap.get_reveal_flap():
            self.flap.set_reveal_flap(False)

        if is_doc_loaded:
            self.title_widget.set_subtitle(os.path.basename(app.current_file_path) if app.current_file_path else "")
            self.show_sigs_button.set_visible(bool(app.signatures))
        else:
            self.title_widget.set_subtitle("")
            self.show_sigs_button.set_visible(False)
            self.hide_signature_info()
            
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.page_entry_button.set_sensitive(is_doc_loaded)
        if is_doc_loaded:
            self.page_entry_button.set_label(f"{app.current_page + 1} / {len(app.doc)}")
            self.prev_page_button.set_tooltip_text(app._("prev_page"))
            self.next_page_button.set_tooltip_text(app._("next_page"))
            self.page_entry_button.set_tooltip_text(app._("jump_to_page_title"))
        else:
            self.page_entry_button.set_label("- / -")

        can_sign = is_doc_loaded and app.signature_rect and app.active_cert_path
        self.sign_button.set_sensitive(can_sign)
        if can_sign:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_sign"))
        elif not app.active_cert_path:
            self.sign_button.set_tooltip_text(app._("no_cert_selected_error"))
        else:
            self.sign_button.set_tooltip_text(app._("sign_button_tooltip_select_area"))

        if app.active_cert_path:
            cert_details = next((c for c in app.cert_manager.get_all_certificate_details() if c['path'] == app.active_cert_path), None)
            if cert_details:
                self.certs_button.set_tooltip_text(cert_details['subject_cn'])
            else:
                self.certs_button.set_tooltip_text(app._("manage_certificates_tooltip"))

    def _build_and_set_menu(self, app):
        """Creates and sets the main application menu, including recent files."""
        menu = Gio.Menu.new()
        menu.append(app._("open_pdf"), "app.open")
        recent_files = app.config.get_recent_files()
        if recent_files:
            recent_menu = Gio.Menu.new()
            for file_path in recent_files:
                action_string = f"app.open_recent({GLib.shell_quote(file_path)})"
                recent_menu.append(os.path.basename(file_path), action_string)
            menu.append_submenu(app._("open_recent"), recent_menu)
        menu.append_section(None, Gio.Menu.new())
        menu.append(app._("sign_document"), "app.sign")
        menu.append_section(None, Gio.Menu.new())
        menu.append(app._("edit_stamp_templates"), "app.edit_stamps")
        menu.append(app._("preferences"), "app.preferences")
        menu.append_section(None, Gio.Menu.new())
        menu.append(app._("about"), "app.about")
        self.menu_button.set_menu_model(menu)
        
    def _on_drawing_area_resize(self, area, width, height):
        """Handles the resize event for the PDF drawing area, triggering a redraw."""
        app = self.get_application()
        if app.page:
            app.display_pixbuf = None
        GLib.idle_add(self.adjust_scroll_and_viewport)

    def adjust_scroll_and_viewport(self):
        """Adjusts the scrollbar position after a resize to keep the content visible."""
        self.update_drawing_area_size_request()
        adj = self.scrolled_window.get_vadjustment()
        if adj:
            upper = adj.get_upper()
            page_size = adj.get_page_size()
            if upper > page_size and adj.get_value() > upper - page_size:
                adj.set_value(upper - page_size)

    def update_drawing_area_size_request(self):
        """Requests a new size for the drawing area to maintain the PDF's aspect ratio."""
        app = self.get_application()
        if not app.page:
            self.drawing_area.set_size_request(-1, -1)
            return
        width = self.drawing_area.get_width()
        if width > 0 and app.page.rect.width > 0:
            target_h = width * (app.page.rect.height / app.page.rect.width)
            if abs(self.drawing_area.get_property("height-request") - int(target_h)) > 1:
                self.drawing_area.set_size_request(-1, int(target_h))

    def scroll_to_rect(self, pdf_rect):
        """Schedules a scroll operation to bring the specified PDF rectangle into view."""
        def _do_scroll():
            app = self.get_application()
            if not app.page or not pdf_rect:
                return GLib.SOURCE_REMOVE

            vadjustment = self.scrolled_window.get_vadjustment()
            if not vadjustment:
                return GLib.SOURCE_REMOVE

            view_width = self.drawing_area.get_width()
            if view_width <= 0 or app.page.rect.width <= 0:
                return GLib.SOURCE_REMOVE

            scale_factor = view_width / app.page.rect.width
            page_height_pdf = app.page.rect.height
            _, y0, _, y1 = pdf_rect

            # Convert PDF coordinates to view coordinates
            view_y = (page_height_pdf - y1) * scale_factor
            view_h = (y1 - y0) * scale_factor

            # Calculate target position to center the rectangle
            viewport_height = vadjustment.get_page_size()
            target_pos = view_y + view_h / 2 - viewport_height / 2

            # Clamp the position to be within the valid range
            upper_bound = vadjustment.get_upper() - viewport_height
            clamped_pos = max(0, min(target_pos, upper_bound))

            vadjustment.set_value(clamped_pos)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_do_scroll)

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        """Draw callback for the main canvas; renders the PDF page and the signature rectangle."""
        app = self.get_application()

        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width
                matrix = fitz.Matrix(zoom, zoom)
                pix = app.page.get_pixmap(matrix=matrix, alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0)
            cr.paint()
            
        if app.highlight_rect:
            if app.page and width > 0:
                scale_factor = width / app.page.rect.width
                pdf_rect = app.highlight_rect
                
                page_height_pdf = app.page.rect.height
                x0, y0, x1, y1 = pdf_rect
                
                view_x = x0 * scale_factor
                view_y = (page_height_pdf - y1) * scale_factor
                view_w = (x1 - x0) * scale_factor
                view_h = (y1 - y0) * scale_factor

                cr.set_source_rgba(1.0, 1.0, 0.0, 0.25) 
                cr.rectangle(view_x, view_y, view_w, view_h)
                cr.fill()
                
                cr.set_source_rgb(0.9, 0.8, 0.0)  
                cr.set_line_width(1.0)
                cr.rectangle(view_x, view_y, view_w, view_h)
                cr.stroke()
        
        rect_to_draw = app.signature_rect or ((min(app.start_x, app.end_x), min(app.start_y, app.end_y), abs(app.end_x - app.start_x), abs(app.end_y - app.start_y)) if app.start_x != -1 else None)
        if not rect_to_draw: return

        x, y, w, h = rect_to_draw
        
        if w < 5 or h < 5:
            cr.set_source_rgba(0.0, 0.5, 0.0, 0.5); cr.set_line_width(1.0); cr.rectangle(x, y, w, h); cr.fill()
            return
            
        cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.rectangle(x, y, w, h); cr.stroke_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8); cr.fill()

        if w > 20 and h > 20 and app.active_cert_path:
            password = Secret.password_lookup_sync(app.cert_manager.KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
            if not password: return
            
            _, certificate_pyca = app.cert_manager.get_credentials(app.active_cert_path, password)
            if not certificate_pyca: return

            from stamp_creator import HtmlStamp, pango_to_html

            parsed_pango_text = app.get_parsed_stamp_text(certificate_pyca)
            html_content = pango_to_html(parsed_pango_text)

            view_width = self.drawing_area.get_width()
            scale = app.page.rect.width / view_width if view_width > 0 else 1
            
            stamp_creator = HtmlStamp(
                html_content=html_content,
                width=w * scale,  
                height=h * scale 
            )
            
            stamp_pixbuf = stamp_creator.get_pixbuf(int(w), int(h))

            if stamp_pixbuf:
                Gdk.cairo_set_source_pixbuf(cr, stamp_pixbuf, x, y)
                cr.paint()

    def _on_toast_dismissed(self, toast):
        """Callback for a toast's 'dismissed' signal."""
        if toast in self.active_toasts:
            self.active_toasts.remove(toast)

    def show_toast(self, text, button_label=None, callback=None, timeout=4):
        """Displays a short-lived notification toast."""
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