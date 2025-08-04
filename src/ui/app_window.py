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
        self.signature_popover = None
        self.popover_active_for_sig = None
        self.signature_view_rects = []
        self.stamp_preview_pixbuf = None
        self.cached_credentials = None
        self.set_default_size(900, 700); self.set_icon_name("org.pepeg.GnomeSign")
        self.set_hide_on_close(False)
        self._build_ui(Sidebar, WelcomeView); self._connect_signals()

    def _build_ui(self, Sidebar, WelcomeView):
        """Constructs the main UI layout and widgets."""
        app = self.get_application()
        self.view_stacker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header_bar = Adw.HeaderBar()
        self.view_stacker.append(self.header_bar)
        self.signature_banner = Adw.Banner.new(""); self.signature_banner.set_revealed(False)
        self.view_stacker.append(self.signature_banner)
        self.flap = Adw.Flap(); self.view_stacker.append(self.flap)
        self.toast_overlay = Adw.ToastOverlay.new(); self.toast_overlay.set_child(self.view_stacker)
        self.set_content(self.toast_overlay)

        self.sidebar_button = Gtk.ToggleButton(icon_name="view-list-symbolic"); self.header_bar.pack_start(self.sidebar_button)
        self.title_widget = Adw.WindowTitle(title=app._("window_title")); self.header_bar.set_title_widget(self.title_widget)
        self.open_button = Gtk.Button(icon_name="document-open-symbolic"); self.header_bar.pack_start(self.open_button)
        self.nav_box = Gtk.Box(spacing=6); self.nav_box.get_style_context().add_class("linked")
        self.prev_page_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.page_entry_button = Gtk.Button(label="- / -"); self.page_entry_button.get_style_context().add_class("flat")
        self.next_page_button = Gtk.Button(icon_name="go-next-symbolic")
        self.nav_box.append(self.prev_page_button); self.nav_box.append(self.page_entry_button); self.nav_box.append(self.next_page_button)
        self.header_bar.pack_start(self.nav_box)
        
        self.activity_spinner = Gtk.Spinner(); self.header_bar.pack_end(self.activity_spinner)
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic"); self.header_bar.pack_end(self.menu_button)
        self.show_sigs_button = Gtk.Button(icon_name="security-high-symbolic", visible=False); self.header_bar.pack_end(self.show_sigs_button)
        self.certs_button = Gtk.Button(icon_name="dialog-password-symbolic"); self.header_bar.pack_end(self.certs_button)
        self.sign_button = Gtk.Button(icon_name="document-edit-symbolic"); self.header_bar.pack_end(self.sign_button)
        
        self.sidebar = Sidebar(); self.flap.set_flap(self.sidebar)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, vexpand=True); self.flap.set_content(self.stack)
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic"); self.scrolled_window.set_child(self.drawing_area)
        self.stack.add_named(self.scrolled_window, "pdf_view")
        self.welcome_view = WelcomeView(); self.stack.add_named(self.welcome_view, "welcome_view")

        self.signature_popover = Gtk.Popover.new()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        self.popover_content_label = Gtk.Label(xalign=0, wrap=True); popover_box.append(self.popover_content_label)
        self.signature_popover.set_child(popover_box); self.signature_popover.set_autohide(False) 
        
        self._on_document_changed(app, app.doc)
        self._on_language_changed(app)

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
        self.sidebar.connect("page-selected", self._on_sidebar_page_selected)
        self.flap.connect("notify::reveal-flap", self.on_flap_reveal_changed)
        
        self.drawing_area.set_draw_func(self._draw_page_and_rect)
        self.drawing_area.connect("resize", self._on_drawing_area_resize)
        self.connect("map", self._on_window_map)
        
        drag = Gtk.GestureDrag.new(); drag.connect("drag-begin", app.on_drag_begin); drag.connect("drag-update", app.on_drag_update); drag.connect("drag-end", app.on_drag_end)
        self.drawing_area.add_controller(drag)
        click_gesture = Gtk.GestureClick.new(); click_gesture.connect("released", self._on_drawing_area_click)
        self.drawing_area.add_controller(click_gesture)
        drop_target = Gtk.DropTarget.new(type=Gio.File, actions=Gdk.DragAction.COPY); drop_target.connect("drop", self._on_file_drop)
        self.add_controller(drop_target)
        
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self._on_drawing_area_motion)
        motion_controller.connect("leave", self._on_drawing_area_leave)
        self.drawing_area.add_controller(motion_controller)

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        
        app.connect("document-changed", self._on_document_changed)
        app.connect("page-changed", self._on_page_changed)
        app.connect("signature-state-changed", self._on_signature_state_changed)
        app.connect("signatures-found", self._on_signatures_found)
        app.connect("toast-request", self._on_toast_request)
        app.connect("language-changed", self._on_language_changed)
        app.connect("highlight-rect-changed", lambda app, rect: self.drawing_area.queue_draw())
        app.connect("certificates-changed", self._on_certificates_changed)

    def _on_document_changed(self, app, doc):
        """Handles the 'document-changed' signal, updating the main view."""
        is_doc_loaded = doc is not None
        self.stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")
        self.sidebar_button.set_sensitive(is_doc_loaded)
        self.nav_box.set_sensitive(is_doc_loaded)
        if not is_doc_loaded and self.flap.get_reveal_flap(): self.flap.set_reveal_flap(False)
        self.title_widget.set_subtitle(os.path.basename(app.current_file_path) if is_doc_loaded and app.current_file_path else "")
        self.sidebar.populate(doc, app.signatures)
        self.welcome_view.update_ui(app)
        self.hide_signature_info()
        self._on_signature_state_changed(app)

    def _on_sidebar_page_selected(self, sidebar, page_num):
        """Handles the 'page-selected' signal from the sidebar."""
        self.get_application().display_page(page_num)

    def _on_page_changed(self, app, page, current_page, total_pages, keep_sidebar_view):
        """Handles the 'page-changed' signal, updating page navigation widgets."""
        self._update_signature_view_rects()
        self.page_entry_button.set_label(f"{current_page + 1} / {total_pages}")
        self.prev_page_button.set_sensitive(current_page > 0)
        self.next_page_button.set_sensitive(current_page < total_pages - 1)
        self.page_entry_button.set_sensitive(True)
        self.drawing_area.queue_draw()
        GLib.idle_add(self.adjust_scroll_and_viewport)

        if not keep_sidebar_view:
            self.sidebar.select_page(current_page)
    
    def _on_signature_state_changed(self, app):
        """Handles the 'signature-state-changed' signal, updating the sign button."""
        can_sign = app.doc is not None and app.signature_rect and app.active_cert_path
        self.sign_button.set_sensitive(can_sign)
        if can_sign: self.sign_button.set_tooltip_text(app._("sign_button_tooltip_sign"))
        elif not app.active_cert_path: self.sign_button.set_tooltip_text(app._("no_cert_selected_error"))
        else: self.sign_button.set_tooltip_text(app._("sign_button_tooltip_select_area"))
        self.drawing_area.queue_draw()
    
    def _on_signatures_found(self, app, signatures):
        """Handles the 'signatures-found' signal, showing the info banner."""
        self.show_signature_info(len(signatures))
        self.show_sigs_button.set_visible(bool(signatures))
    
    def _on_toast_request(self, app, message, button_label, callback_func):
        """Handles the 'toast-request' signal."""
        callback = (lambda: callback_func()) if callback_func else None
        self.show_toast(message, button_label, callback)

    def _on_language_changed(self, app):
        """Handles the 'language-changed' signal, updating all translatable texts."""
        self._build_and_set_menu(app)
        self.sidebar_button.set_tooltip_text(app._("toggle_sidebar_tooltip"))
        self.open_button.set_tooltip_text(app._("open_pdf"))
        self.prev_page_button.set_tooltip_text(app._("prev_page"))
        self.next_page_button.set_tooltip_text(app._("next_page"))
        self.page_entry_button.set_tooltip_text(app._("jump_to_page_title"))
        self.show_sigs_button.set_tooltip_text(app._("show_signatures_tooltip"))
        self._update_certs_button_tooltip()
        self._on_signature_state_changed(app)
    
    def _on_certificates_changed(self, app):
        """Handles the 'certificates-changed' signal."""
        self.cached_credentials = None
        self.stamp_preview_pixbuf = None
        self._update_certs_button_tooltip()
        self._on_signature_state_changed(app)

    def _update_certs_button_tooltip(self):
        """Updates the tooltip of the certificates button with the active certificate's name."""
        app = self.get_application()
        tooltip = app._("manage_certificates_tooltip")
        if app.active_cert_path:
            if cert_details := next((c for c in app.cert_manager.get_all_certificate_details() if c['path'] == app.active_cert_path), None):
                tooltip = cert_details['subject_cn']
        self.certs_button.set_tooltip_text(tooltip)
    
    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handles key press events for page navigation and scrolling."""
        app = self.get_application()
        if not app.doc: return False
        
        SCROLL_STEP = 40.0 
        if keyval == Gdk.KEY_Page_Down:
            app.on_next_page_clicked(None); return True
        elif keyval == Gdk.KEY_Page_Up:
            app.on_prev_page_clicked(None); return True
        elif keyval == Gdk.KEY_Down:
            if adj := self.scrolled_window.get_vadjustment():
                adj.set_value(min(adj.get_value() + SCROLL_STEP, adj.get_upper() - adj.get_page_size())); return True
        elif keyval == Gdk.KEY_Up:
            if adj := self.scrolled_window.get_vadjustment():
                adj.set_value(max(adj.get_value() - SCROLL_STEP, adj.get_lower())); return True
        return False

    def show_signature_info(self, count):
        """Shows the banner for existing signatures."""
        app = self.get_application()
        self.signature_banner.set_title(app._("signatures_found_toast").format(count)); self.signature_banner.set_button_label(app._("go_to_signatures")); self.signature_banner.set_revealed(True)

    def hide_signature_info(self):
        """Hides the banner for existing signatures."""
        self.signature_banner.set_revealed(False)
        
    def _on_file_drop(self, target, value, x, y):
        """Handles a file drop event, opening the PDF if it's a valid file."""
        app = self.get_application()
        if file := value.get_file():
            if file.get_path().lower().endswith(".pdf"):
                app.open_file_path(file.get_path()); return True
        return False
    
    def _on_drawing_area_click(self, gesture, n_press, x, y):
        """Handles a click on the drawing area to clear highlights or show signature details."""
        app = self.get_application()
        for rect, sig_details in self.signature_view_rects:
            if rect.contains_point(x, y):
                app.on_signature_selected(self.sidebar, sig_details)
                return
        if app.highlight_rect:
            app.highlight_rect = None
            app.emit("highlight-rect-changed", None)

    def on_sidebar_toggled(self, button):
        """Toggles the visibility of the sidebar flap."""
        self.flap.set_reveal_flap(button.get_active())

    def on_flap_reveal_changed(self, flap, param):
        """Synchronizes the sidebar toggle button's state with the flap's visibility."""
        self.sidebar_button.set_active(flap.get_reveal_flap())

    def _build_and_set_menu(self, app):
        """Creates and sets the main application menu, including recent files."""
        menu = Gio.Menu.new(); menu.append(app._("open_pdf"), "app.open")
        if recent_files := app.config.get_recent_files():
            recent_menu = Gio.Menu.new()
            for file_path in recent_files: recent_menu.append(os.path.basename(file_path), f"app.open_recent({GLib.shell_quote(file_path)})")
            menu.append_submenu(app._("open_recent"), recent_menu)
        menu.append_section(None, Gio.Menu.new()); menu.append(app._("sign_document"), "app.sign"); menu.append_section(None, Gio.Menu.new())
        menu.append(app._("edit_stamp_templates"), "app.edit_stamps"); menu.append(app._("preferences"), "app.preferences"); menu.append_section(None, Gio.Menu.new())
        menu.append(app._("about"), "app.about")
        self.menu_button.set_menu_model(menu)
        
    def _on_drawing_area_resize(self, area, width, height):
        """Handles the resize event for the PDF drawing area, triggering a redraw."""
        app = self.get_application()
        if app.page: app.display_pixbuf = None
        self._update_signature_view_rects()
        GLib.idle_add(self.adjust_scroll_and_viewport)

    def adjust_scroll_and_viewport(self):
        """Adjusts the scrollbar position after a resize to keep the content visible."""
        self.update_drawing_area_size_request()

    def update_drawing_area_size_request(self):
        """Requests a new size for the drawing area to maintain the PDF's aspect ratio."""
        app = self.get_application()
        if not app.page: self.drawing_area.set_size_request(-1, -1); return
        width = self.drawing_area.get_width()
        if width > 0 and app.page.rect.width > 0:
            target_h = width * (app.page.rect.height / app.page.rect.width)
            if abs(self.drawing_area.get_property("height-request") - int(target_h)) > 1:
                self.drawing_area.set_size_request(-1, int(target_h))

    def scroll_to_rect(self, pdf_rect):
        """Schedules a scroll operation to bring the specified PDF rectangle into view."""
        GLib.idle_add(self._do_scroll_to_rect, pdf_rect)

    def _do_scroll_to_rect(self, pdf_rect):
        """Performs the actual scrolling to a rectangle."""
        app = self.get_application()
        if not all([app.page, pdf_rect]): return GLib.SOURCE_REMOVE
        vadjustment = self.scrolled_window.get_vadjustment(); view_width = self.drawing_area.get_width()
        if not all([vadjustment, view_width > 0, app.page.rect.width > 0]): return GLib.SOURCE_REMOVE
        scale_factor = view_width / app.page.rect.width
        _, y0, _, y1 = pdf_rect; view_y = (app.page.rect.height - y1) * scale_factor; view_h = (y1 - y0) * scale_factor
        target_pos = view_y + view_h / 2 - vadjustment.get_page_size() / 2
        clamped_pos = max(0, min(target_pos, vadjustment.get_upper() - vadjustment.get_page_size()))
        vadjustment.set_value(clamped_pos); return GLib.SOURCE_REMOVE

    def _update_and_cache_stamp_preview(self, width, height):
        """
        Generates and caches the signature stamp preview pixbuf.
        This is an expensive operation and should only be called when necessary.
        """
        app = self.get_application()

        if self.stamp_preview_pixbuf and self.stamp_preview_pixbuf.get_width() == int(width) and self.stamp_preview_pixbuf.get_height() == int(height):
            return

        self.stamp_preview_pixbuf = None

        if not app.active_cert_path or not app.page or width <= 20 or height <= 20:
            return

        if not self.cached_credentials:
            password = Secret.password_lookup_sync(
                app.cert_manager.KEYRING_SCHEMA, {"path": app.active_cert_path}, None
            )
            if not password:
                return

            credentials = app.cert_manager.get_credentials(app.active_cert_path, password)
            if not credentials or not credentials[1]:
                return
            self.cached_credentials = credentials[1]

        certificate_pyca = self.cached_credentials

        try:
            from stamp_creator import HtmlStamp, pango_to_html
            parsed_pango_text = app.get_parsed_stamp_text(certificate_pyca)
            html_content = pango_to_html(parsed_pango_text)

            scale = app.page.rect.width / self.drawing_area.get_width() if self.drawing_area.get_width() > 0 else 1

            stamp_creator = HtmlStamp(html_content=html_content, width=width * scale, height=height * scale)

            self.stamp_preview_pixbuf = stamp_creator.get_pixbuf(int(width), int(height))
        except Exception as e:
            print(f"Error generating stamp preview: {e}")
            self.stamp_preview_pixbuf = None

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
        """Draw callback for the main canvas; renders the PDF page and the signature rectangle."""
        app = self.get_application()
        if app.page and width > 0:
            if not app.display_pixbuf or app.display_pixbuf.get_width() != width:
                zoom = width / app.page.rect.width
                pix = app.page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                app.display_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            Gdk.cairo_set_source_pixbuf(cr, app.display_pixbuf, 0, 0); cr.paint()
        if app.highlight_rect and app.page and width > 0:
            scale_factor = width / app.page.rect.width
            x0, y0, x1, y1 = app.highlight_rect
            view_x, view_y = x0 * scale_factor, (app.page.rect.height - y1) * scale_factor
            view_w, view_h = (x1 - x0) * scale_factor, (y1 - y0) * scale_factor
            cr.set_source_rgba(1.0, 1.0, 0.0, 0.25); cr.rectangle(view_x, view_y, view_w, view_h); cr.fill()
            cr.set_source_rgb(0.9, 0.8, 0.0); cr.set_line_width(1.0); cr.rectangle(view_x, view_y, view_w, view_h); cr.stroke()
        if rect_to_draw := app.signature_rect or ((min(app.start_x, app.end_x), min(app.start_y, app.end_y), abs(app.end_x - app.start_x), abs(app.end_y - app.start_y)) if app.start_x != -1 else None):
            x, y, w, h = rect_to_draw
            if w < 5 or h < 5: cr.set_source_rgba(0.0, 0.5, 0.0, 0.5); cr.rectangle(x, y, w, h); cr.fill(); return
            cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.rectangle(x, y, w, h); cr.stroke_preserve(); cr.set_source_rgba(1.0, 1.0, 1.0, 0.8); cr.fill()
            if w > 20 and h > 20 and app.active_cert_path:
                # Preview generation is now cached. We just draw the pixbuf if it exists.
                if self.stamp_preview_pixbuf:
                    Gdk.cairo_set_source_pixbuf(cr, self.stamp_preview_pixbuf, x, y)
                    cr.paint()

    def _on_toast_dismissed(self, toast):
        """Callback for a toast's 'dismissed' signal."""
        if toast in self.active_toasts: self.active_toasts.remove(toast)

    def show_toast(self, text, button_label=None, callback=None, timeout=4):
        """Displays a short-lived notification toast."""
        toast = Adw.Toast.new(text)
        toast.connect("dismissed", self._on_toast_dismissed)
        if button_label and callback:
            toast.set_button_label(button_label); toast.connect("button-clicked", lambda t: (t.dismiss(), callback()))
        elif timeout > 0: GLib.timeout_add_seconds(timeout, lambda: toast.dismiss() or GLib.SOURCE_REMOVE)
        self.active_toasts.append(toast); self.toast_overlay.add_toast(toast)

    def _on_window_map(self, widget):
        """Sets the popover's parent once the window is mapped."""
        if not self.signature_popover.get_parent(): self.signature_popover.set_parent(self)

    def _update_signature_view_rects(self):
        """Calculates and caches the view coordinates of signature rectangles for the current page."""
        self.signature_view_rects.clear()
        app = self.get_application()
        if not app.page or not app.signatures: return
        width = self.drawing_area.get_width()
        if width <= 0 or app.page.rect.width <= 0: return
        scale_factor = width / app.page.rect.width
        for sig in app.signatures:
            if sig.page_num == app.current_page and sig.rect:
                x0, y0, x1, y1 = sig.rect
                view_x, view_y = x0 * scale_factor, (app.page.rect.height - y1) * scale_factor
                view_w, view_h = (x1 - x0) * scale_factor, (y1 - y0) * scale_factor
                gdk_rect = Gdk.Rectangle(); gdk_rect.x, gdk_rect.y = int(view_x), int(view_y); gdk_rect.width, gdk_rect.height = int(view_w), int(view_h)
                self.signature_view_rects.append((gdk_rect, sig))

    def _update_popover_content(self, sig_details):
        """Prepares the signature details text for the popover."""
        app = self.get_application(); validity_text = f"<b><span color='green'>{app._('sig_integrity_ok')}</span></b>" if sig_details.valid and sig_details.intact else f"<b><span color='red'>{app._('sig_integrity_error')}</span></b>"
        signer_esc = GLib.markup_escape_text(sig_details.signer_name); date_str = sig_details.sign_time.strftime('%Y-%m-%d %H:%M:%S %Z') if sig_details.sign_time else 'N/A'
        self.popover_content_label.set_markup(f"{validity_text}\n<b>{app._('signer')}:</b> {signer_esc}\n<b>{app._('sign_date')}:</b> {date_str}")

    def _on_drawing_area_leave(self, controller):
        """Hides the popover when the mouse leaves the drawing area."""
        if self.signature_popover.is_visible(): self.signature_popover.popdown()
        self.popover_active_for_sig = None

    def _on_drawing_area_motion(self, controller, x, y):
        """Handles mouse motion over the drawing area to show the signature popover."""
        found_sig_tuple = None
        for rect, sig in self.signature_view_rects:
            if rect.contains_point(x, y):
                found_sig_tuple = (rect, sig); break
        if found_sig_tuple:
            rect_da, sig = found_sig_tuple
            if self.popover_active_for_sig is sig: return
            self.popover_active_for_sig = sig
            self._update_popover_content(sig)
            
            dest_x, dest_y = self.drawing_area.translate_coordinates(self, rect_da.x, rect_da.y)
            
            pointing_rect = Gdk.Rectangle()
            pointing_rect.x, pointing_rect.y = dest_x, dest_y
            pointing_rect.width, pointing_rect.height = rect_da.width, rect_da.height
            
            self.signature_popover.set_pointing_to(pointing_rect)
            self.signature_popover.popup()
        else:
            if self.popover_active_for_sig is not None:
                self.popover_active_for_sig = None
                self.signature_popover.popdown()