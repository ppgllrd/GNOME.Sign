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
        self.set_default_size(900, 700); self.set_icon_name("org.pepeg.GnomeSign")
        self.set_hide_on_close(False)
        self._build_ui(Sidebar, WelcomeView); self._connect_signals()

    def _build_ui(self, Sidebar, WelcomeView):
        """Constructs the main UI layout and widgets."""
        app = self.get_application()
        
        self.view_stacker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header_bar = Adw.HeaderBar()
        self.view_stacker.append(self.header_bar)
        
        self.signature_banner = Adw.Banner.new("")
        self.signature_banner.set_revealed(False)
        self.view_stacker.append(self.signature_banner)
        
        self.flap = Adw.Flap()
        self.view_stacker.append(self.flap)
        
        self.toast_overlay = Adw.ToastOverlay.new()
        self.toast_overlay.set_child(self.view_stacker)
        self.set_content(self.toast_overlay)

        # HeaderBar Content
        self.sidebar_button = Gtk.ToggleButton(icon_name="view-list-symbolic")
        self.header_bar.pack_start(self.sidebar_button)
        self.title_widget = Adw.WindowTitle(title=app._("window_title"))
        self.header_bar.set_title_widget(self.title_widget)
        self.open_button = Gtk.Button(icon_name="document-open-symbolic")
        self.header_bar.pack_start(self.open_button)
        nav_box = Gtk.Box(spacing=6); nav_box.get_style_context().add_class("linked")
        self.prev_page_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.page_entry_button = Gtk.Button(label="- / -")
        self.page_entry_button.get_style_context().add_class("flat")
        self.next_page_button = Gtk.Button(icon_name="go-next-symbolic")
        nav_box.append(self.prev_page_button); nav_box.append(self.page_entry_button); nav_box.append(self.next_page_button)
        self.header_bar.pack_start(nav_box)
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.header_bar.pack_end(self.menu_button)
        self.show_sigs_button = Gtk.Button(icon_name="security-high-symbolic", visible=False)
        self.header_bar.pack_end(self.show_sigs_button)
        self.certs_button = Gtk.Button(icon_name="dialog-password-symbolic")
        self.header_bar.pack_end(self.certs_button)
        self.sign_button = Gtk.Button(icon_name="document-edit-symbolic")
        self.header_bar.pack_end(self.sign_button)
        
        # Flap and Content Stack
        self.sidebar = Sidebar(); self.flap.set_flap(self.sidebar)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, vexpand=True)
        self.flap.set_content(self.stack)
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic")
        self.scrolled_window.set_child(self.drawing_area)
        self.stack.add_named(self.scrolled_window, "pdf_view")
        self.welcome_view = WelcomeView()
        self.stack.add_named(self.welcome_view, "welcome_view")

        # Popover Creation
        self.signature_popover = Gtk.Popover.new()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        self.popover_content_label = Gtk.Label(xalign=0, wrap=True)
        popover_box.append(self.popover_content_label)
        self.signature_popover.set_child(popover_box)
        self.signature_popover.set_autohide(False) 
        
    def _connect_signals(self):
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
        
        # Conectar a la señal "map" de la VENTANA para configurar el padre del popover
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
        
    def show_signature_info(self, count):
        app = self.get_application()
        self.signature_banner.set_title(app._("signatures_found_toast").format(count)); self.signature_banner.set_button_label(app._("go_to_signatures")); self.signature_banner.set_revealed(True)

    def hide_signature_info(self): self.signature_banner.set_revealed(False)
        
    def _on_file_drop(self, target, value, x, y):
        app = self.get_application()
        file = value.get_file()
        if file and file.get_path().lower().endswith(".pdf"):
            app.open_file_path(file.get_path()); return True
        return False
    
    def _on_drawing_area_click(self, gesture, n_press, x, y):
        app = self.get_application()
        if app.highlight_rect: app.highlight_rect = None; self.drawing_area.queue_draw()

    def on_sidebar_toggled(self, button): self.flap.set_reveal_flap(button.get_active())
    def on_flap_reveal_changed(self, flap, param): self.sidebar_button.set_active(flap.get_reveal_flap())
    def update_ui(self, app): self.welcome_view.update_ui(app); self.update_header_bar_state(app); self._build_and_set_menu(app); self.drawing_area.queue_draw()
            
    def update_header_bar_state(self, app):
        is_doc_loaded = app.doc is not None
        self.stack.set_visible_child_name("pdf_view" if is_doc_loaded else "welcome_view")
        self.sidebar_button.set_sensitive(is_doc_loaded)
        if not is_doc_loaded and self.flap.get_reveal_flap(): self.flap.set_reveal_flap(False)
        self.title_widget.set_subtitle(os.path.basename(app.current_file_path) if is_doc_loaded and app.current_file_path else "")
        self.show_sigs_button.set_visible(is_doc_loaded and bool(app.signatures))
        if not is_doc_loaded: self.hide_signature_info()
        self.prev_page_button.set_sensitive(is_doc_loaded and app.current_page > 0)
        self.next_page_button.set_sensitive(is_doc_loaded and app.current_page < len(app.doc) - 1)
        self.page_entry_button.set_sensitive(is_doc_loaded)
        self.page_entry_button.set_label(f"{app.current_page + 1} / {len(app.doc)}" if is_doc_loaded else "- / -")
        self.sign_button.set_sensitive(is_doc_loaded and app.signature_rect and app.active_cert_path)

    def _build_and_set_menu(self, app):
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
        app = self.get_application()
        if app.page: app.display_pixbuf = None
        self._update_signature_view_rects()
        GLib.idle_add(self.adjust_scroll_and_viewport)

    def adjust_scroll_and_viewport(self): self.update_drawing_area_size_request()
        
    def update_drawing_area_size_request(self):
        app = self.get_application()
        if not app.page: self.drawing_area.set_size_request(-1, -1); return
        width = self.drawing_area.get_width()
        if width > 0 and app.page.rect.width > 0:
            target_h = width * (app.page.rect.height / app.page.rect.width)
            if abs(self.drawing_area.get_property("height-request") - int(target_h)) > 1: self.drawing_area.set_size_request(-1, int(target_h))

    def scroll_to_rect(self, pdf_rect): GLib.idle_add(self._do_scroll_to_rect, pdf_rect)

    def _do_scroll_to_rect(self, pdf_rect):
        app = self.get_application()
        if not all([app.page, pdf_rect]): return GLib.SOURCE_REMOVE
        vadjustment = self.scrolled_window.get_vadjustment(); view_width = self.drawing_area.get_width()
        if not all([vadjustment, view_width > 0, app.page.rect.width > 0]): return GLib.SOURCE_REMOVE
        scale_factor = view_width / app.page.rect.width
        _, y0, _, y1 = pdf_rect; view_y = (app.page.rect.height - y1) * scale_factor; view_h = (y1 - y0) * scale_factor
        target_pos = view_y + view_h / 2 - vadjustment.get_page_size() / 2
        clamped_pos = max(0, min(target_pos, vadjustment.get_upper() - vadjustment.get_page_size()))
        vadjustment.set_value(clamped_pos); return GLib.SOURCE_REMOVE

    def _draw_page_and_rect(self, drawing_area, cr, width, height):
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
                if password := Secret.password_lookup_sync(app.cert_manager.KEYRING_SCHEMA, {"path": app.active_cert_path}, None):
                        _, certificate_pyca = app.cert_manager.get_credentials(app.active_cert_path, password)
                        if certificate_pyca: # Tu corrección
                            from stamp_creator import HtmlStamp, pango_to_html
                            parsed_pango_text = app.get_parsed_stamp_text(certificate_pyca)
                            html_content = pango_to_html(parsed_pango_text)
                            scale = app.page.rect.width / self.drawing_area.get_width() if self.drawing_area.get_width() > 0 else 1
                            stamp_creator = HtmlStamp(html_content=html_content, width=w * scale, height=h * scale)
                            if stamp_pixbuf := stamp_creator.get_pixbuf(int(w), int(h)): Gdk.cairo_set_source_pixbuf(cr, stamp_pixbuf, x, y); cr.paint()

    def _on_toast_dismissed(self, toast):
        if toast in self.active_toasts: self.active_toasts.remove(toast)

    def show_toast(self, text, button_label=None, callback=None, timeout=4):
        toast = Adw.Toast.new(text)
        toast.connect("dismissed", self._on_toast_dismissed)
        if button_label and callback:
            toast.set_button_label(button_label); toast.connect("button-clicked", lambda t: (t.dismiss(), callback()))
        elif timeout > 0: GLib.timeout_add_seconds(timeout, lambda: toast.dismiss() or GLib.SOURCE_REMOVE)
        self.active_toasts.append(toast); self.toast_overlay.add_toast(toast)

    def _on_window_map(self, widget):
        """Se ejecuta una vez cuando la VENTANA está lista para ser mostrada."""
        if not self.signature_popover.get_parent():
            self.signature_popover.set_parent(self)

    def _update_signature_view_rects(self):
        """Calcula y cachea las coordenadas de los rectángulos de firma para la página actual."""
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
                gdk_rect = Gdk.Rectangle()
                gdk_rect.x, gdk_rect.y = int(view_x), int(view_y)
                gdk_rect.width, gdk_rect.height = int(view_w), int(view_h)
                self.signature_view_rects.append((gdk_rect, sig))

    def _update_popover_content(self, sig_details):
        app = self.get_application(); validity_text = f"<b><span color='green'>{app._('sig_integrity_ok')}</span></b>" if sig_details.valid and sig_details.intact else f"<b><span color='red'>{app._('sig_integrity_error')}</span></b>"
        signer_esc = GLib.markup_escape_text(sig_details.signer_name); date_str = sig_details.sign_time.strftime('%Y-%m-%d %H:%M:%S %Z') if sig_details.sign_time else 'N/A'
        self.popover_content_label.set_markup(f"{validity_text}\n<b>{app._('signer')}:</b> {signer_esc}\n<b>{app._('sign_date')}:</b> {date_str}")

    def _on_drawing_area_leave(self, controller):
        if self.signature_popover.is_visible(): self.signature_popover.popdown()
        self.popover_active_for_sig = None

    def _on_drawing_area_motion(self, controller, x, y):
        """Comprueba el movimiento del ratón contra la caché y muestra el popover."""
        found_sig_tuple = None
        for rect, sig in self.signature_view_rects:
            if rect.contains_point(x, y):
                found_sig_tuple = (rect, sig)
                break

        if found_sig_tuple:
            rect_da, sig = found_sig_tuple
            if self.popover_active_for_sig is sig: return
            
            self.popover_active_for_sig = sig
            self._update_popover_content(sig)
            
            # Traducir el rectángulo del DrawingArea a la ventana principal
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