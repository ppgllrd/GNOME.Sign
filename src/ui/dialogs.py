import gi
gi.require_version("Secret", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo, Gdk, Secret, GLib, Gio
import os
import uuid
import copy
import re
from certificate_manager import KEYRING_SCHEMA
from datetime import datetime, timedelta, timezone

def create_about_dialog(parent, i18n_func):
    """Creates and shows the About dialog."""
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True)
    dialog.set_program_name("GnomeSign")
    dialog.set_version("1.0")
    dialog.set_comments(i18n_func("sign_reason"))
    dialog.set_logo_icon_name("org.pepeg.GnomeSign") 
    dialog.set_website("https://github.com/ppgllrd/GNOME.Sign")
    dialog.set_authors(["Pepe Gallardo", "Gemini"])
    dialog.present()

def create_cert_details_dialog(parent, i18n_func, cert_details):
    """Shows a dialog with certificate details after successful loading."""
    message = i18n_func("cert_load_success_details_message").format(
        cert_details['subject_cn'],
        cert_details['issuer_cn'],
        cert_details['serial'],
        cert_details['expires'].strftime('%Y-%m-%d %H:%M:%S UTC')
    )
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=i18n_func("cert_load_success_title"),
        secondary_text=message,
        secondary_use_markup=True
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.present()

def create_cert_selector_dialog(parent, app):
    """Creates a dialog to select and manage certificates."""
    i18n_func = app._
    dialog = Gtk.Dialog(title=i18n_func("select_certificate"), transient_for=parent, modal=True)
    dialog.set_default_size(550, 300) 
    
    dialog.add_button(i18n_func("cancel"), Gtk.ResponseType.CANCEL)
    add_button = dialog.add_button(i18n_func("add_certificate"), Gtk.ResponseType.APPLY)
    add_button.get_style_context().add_class("suggested-action")
    
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    cert_details_list = app.cert_manager.get_all_certificate_details()
    active_row = None

    def on_delete_cert_clicked(button, row_to_delete):
        """Handles the click on the delete button for a certificate row."""
        cert_path = row_to_delete.cert_path
        confirm_dialog = Gtk.MessageDialog(transient_for=dialog, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=i18n_func("confirm_delete_cert_title"), secondary_text=i18n_func("confirm_delete_cert_message"))
        def on_confirm_response(conf_d, res):
            """Handles the response from the confirmation dialog."""
            if res == Gtk.ResponseType.YES:
                app.cert_manager.remove_credentials_from_keyring(cert_path)
                app.config.remove_cert_path(cert_path)
                app.cert_manager.remove_cert_path(cert_path)
                
                listbox.remove(row_to_delete)
                if app.active_cert_path == cert_path:
                    app.active_cert_path = None
                app.update_ui()
            conf_d.destroy()
        confirm_dialog.connect("response", on_confirm_response)
        confirm_dialog.present()

    for cert in cert_details_list:
        row = Gtk.ListBoxRow()
        row.cert_path = cert['path']

        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        main_hbox.append(item_box)

        delete_button = Gtk.Button.new_from_icon_name("edit-delete-symbolic")
        delete_button.set_valign(Gtk.Align.CENTER)
        delete_button.connect("clicked", on_delete_cert_clicked, row)
        main_hbox.append(delete_button)
        
        subject_label = Gtk.Label(xalign=0)
        subject_label.set_markup(f"<b><big>{cert['subject_cn']}</big></b>")
        item_box.append(subject_label)

        now = datetime.now(timezone.utc)
        expires = cert['expires']
        
        if expires < now:
            expiry_markup = f"<span color='red'><b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')} (Expired)</span>"
        elif expires < (now + timedelta(days=30)):
            expiry_markup = f"<span color='orange'><b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')}</span>"
        else:
            expiry_markup = f"<b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')}"

        details_label = Gtk.Label(xalign=0); details_label.set_wrap(True); details_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        details_text = (f"<small>{expiry_markup}\n<i>{i18n_func('issuer')}:</i> {cert['issuer_cn']}\n<i>{i18n_func('serial')}:</i> {cert['serial']}\n<i>{i18n_func('path')}:</i> {cert['path']}</small>")
        details_label.set_markup(details_text)
        item_box.append(details_label)
        
        row.set_child(main_hbox)
        listbox.append(row)

        if cert['path'] == app.active_cert_path:
            active_row = row
    
    if active_row: listbox.select_row(active_row)

    def on_row_activated(box, row):
        """Sets the selected certificate as active and closes the dialog."""
        if row:
            app.active_cert_path = row.cert_path
            app.update_ui()
            dialog.response(Gtk.ResponseType.OK)

    listbox.connect("row-activated", on_row_activated)
    
    scrolled = Gtk.ScrolledWindow(hscrollbar_policy="never", vexpand=True, hexpand=True)
    scrolled.set_child(listbox)
    dialog.get_content_area().append(scrolled)
    
    def on_dialog_response(d, response_id):
        """Handles dialog responses, triggering the add certificate action if needed."""
        if response_id == Gtk.ResponseType.APPLY:
            d.destroy() 
            app.activate_action("load_cert")
        else:
            d.destroy()

    dialog.connect("response", on_dialog_response)
    dialog.show()

def create_password_dialog(parent, i18n_func, pkcs12_path, callback):
    """Creates a dialog to request the password for a PKCS#12 file."""
    dialog = Gtk.Dialog(title=i18n_func("password"), transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    ok_button.get_style_context().add_class("suggested-action")
    dialog.set_default_widget(ok_button)
    content_area = dialog.get_content_area()
    content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
    content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
    password_entry = Gtk.Entry(visibility=False, placeholder_text=i18n_func("password"))
    content_area.append(password_entry)
    password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
    def on_response(d, response_id):
        """Passes the entered password to the callback upon dialog completion."""
        password = password_entry.get_text() if response_id == Gtk.ResponseType.OK else None
        callback(password)
        d.destroy()
    dialog.connect("response", on_response)
    dialog.present()

def show_message_dialog(parent, title, message, message_type, buttons=Gtk.ButtonsType.OK):
    """Displays a simple, modal message dialog and returns the user's response."""
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=message_type, buttons=buttons, text=title, secondary_text=message)
    response_id = Gtk.ResponseType.NONE
    loop = GLib.MainLoop()
    def on_response(d, res):
        """Captures the response and quits the local main loop."""
        nonlocal response_id; response_id = res
        d.destroy()
        if loop.is_running(): loop.quit()
    dialog.connect("response", on_response)
    dialog.present()
    if dialog.is_visible(): loop.run()
    return response_id

def create_jump_to_page_dialog(parent, app, callback):
    """Creates a dialog for jumping to a specific page number in the document."""
    i18n_func = app._; current_page = app.current_page + 1; max_page = len(app.doc)
    dialog = Gtk.Dialog(title=i18n_func("jump_to_page_title"), transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    content_area = dialog.get_content_area()
    content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
    content_area.append(Gtk.Label(label=i18n_func("jump_to_page_prompt").format(max_page)))
    adjustment = Gtk.Adjustment(value=current_page, lower=1, upper=max_page, step_increment=1, page_increment=10, page_size=0)
    spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
    content_area.append(spin_button)
    dialog.set_default_widget(spin_button)
    spin_button.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
    def on_response(d, response_id):
        """Calls the callback with the selected page number upon confirmation."""
        page_num = spin_button.get_value_as_int() - 1 if response_id == Gtk.ResponseType.OK else None
        callback(page_num)
        d.destroy()
    dialog.connect("response", on_response)
    dialog.present()

def create_stamp_editor_dialog(parent, app, config):
    """Creates a comprehensive dialog for creating, editing, and managing signature stamp templates."""
    i18n_func = app._
    dialog = Gtk.Dialog(title=i18n_func("edit_stamp_templates"), transient_for=parent, modal=True, width_request=700, height_request=600)
    dialog.add_button(i18n_func("close_button"), Gtk.ResponseType.CLOSE)
    
    main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
    dialog.get_content_area().append(main_box)

    left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=220); main_box.append(left_pane)
    right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True); main_box.append(right_pane)

    left_pane.append(Gtk.Label(label=f"<b>{i18n_func('templates')}</b>", use_markup=True, xalign=0))
    template_combo = Gtk.ComboBoxText(); left_pane.append(template_combo)
    
    btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12); left_pane.append(btn_box)
    new_btn = Gtk.Button.new_with_label(i18n_func("new")); duplicate_btn = Gtk.Button.new_with_label(i18n_func("duplicate"))
    save_btn = Gtk.Button.new_with_label(i18n_func("save")); delete_btn = Gtk.Button.new_with_label(i18n_func("delete"))
    set_active_btn = Gtk.Button.new_with_label(i18n_func("set_as_active"))
    btn_box.append(new_btn); btn_box.append(duplicate_btn); btn_box.append(save_btn); btn_box.append(delete_btn); btn_box.append(set_active_btn)

    right_pane.append(Gtk.Label(label=f"<b>{i18n_func('template_name')}</b>", use_markup=True, xalign=0))
    name_entry = Gtk.Entry(); right_pane.append(name_entry)

    state = {"current_id": None, "block_combo_changed": False, "initial_form_data": None, "loaded_cert": None, "last_focused_view": None}
    text_es_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    text_en_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    state["last_focused_view"] = text_es_view

    def get_focused_buffer_and_bounds():
        """Gets the buffer and selection bounds of the currently focused TextView."""
        view = state.get("last_focused_view");
        if not view: return None, None, None
        buffer = view.get_buffer()
        bounds = buffer.get_selection_bounds()
        if not bounds: return None, None, None
        return buffer, *bounds

    def toggle_pango_tag(tag):
        """Toggles a simple Pango tag (like <b> or <i>) around the selected text."""
        buffer, start, end = get_focused_buffer_and_bounds()
        if not buffer or not start: return
        text = buffer.get_text(start, end, True)
        if text.strip().startswith(f"<{tag}>") and text.strip().endswith(f"</{tag}>"):
            unwrapped_text = re.sub(f'^\\s*<{tag}>(.*?)</{tag}>\\s*$', r'\1', text, flags=re.DOTALL)
            buffer.delete(start, end); buffer.insert(start, unwrapped_text)
        else:
            buffer.delete(start, end); buffer.insert(start, f"<{tag}>{text}</{tag}>")

    def apply_span_tag(attribute, value):
        """Applies a Pango <span> tag with a specific attribute to the selected text."""
        buffer, start, end = get_focused_buffer_and_bounds()
        if not buffer or not start: return
        text = buffer.get_text(start, end, True)
        buffer.delete(start, end); buffer.insert(start, f'<span {attribute}="{value}">{text}</span>')

    def _rgba_to_hex(rgba):
        """Converts a Gdk.RGBA color to a hex string (e.g., #RRGGBB)."""
        return f"#{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"

    toolbar = Gtk.Box(spacing=6)
    bold_btn = Gtk.Button.new_from_icon_name("format-text-bold-symbolic"); bold_btn.connect("clicked", lambda b: toggle_pango_tag("b"))
    italic_btn = Gtk.Button.new_from_icon_name("format-text-italic-symbolic"); italic_btn.connect("clicked", lambda b: toggle_pango_tag("i"))
    font_combo = Gtk.ComboBoxText.new()
    safe_fonts = ["Times-Roman", "Helvetica", "Courier"]
    font_combo.append("placeholder_id", i18n_func("font"))
    for font in safe_fonts: font_combo.append_text(font)
    font_combo.set_active_id("placeholder_id")
    def on_font_changed(combo):
        """Applies the selected font to the text selection."""
        if combo.get_active_id() == "placeholder_id": return
        apply_span_tag("font_family", combo.get_active_text())
    font_combo.connect("changed", on_font_changed)

    size_combo = Gtk.ComboBoxText.new()
    pango_size_map = {i18n_func("size_small"): "small", i18n_func("size_normal"): "medium", i18n_func("size_large"): "large", i18n_func("size_huge"): "x-large"}
    size_combo.append("placeholder_id", i18n_func("size"))
    for label in pango_size_map: size_combo.append_text(label)
    size_combo.set_active_id("placeholder_id")
    def on_size_changed(combo):
        """Applies the selected size to the text selection."""
        if combo.get_active_id() == "placeholder_id": return
        pango_size = pango_size_map.get(combo.get_active_text())
        if pango_size: apply_span_tag("size", pango_size)
    size_combo.connect("changed", on_size_changed)

    color_btn = Gtk.ColorButton.new(); color_btn.connect("color-set", lambda b: apply_span_tag("color", _rgba_to_hex(b.get_rgba())))
    toolbar.append(bold_btn); toolbar.append(italic_btn); toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)); toolbar.append(font_combo); toolbar.append(size_combo); toolbar.append(color_btn)

    def on_view_focus(widget, param_spec):
        """Tracks which text view (ES or EN) last had focus."""
        if widget.get_property("has-focus"): state["last_focused_view"] = widget
    
    text_es_view.connect("notify::has-focus", on_view_focus); text_en_view.connect("notify::has-focus", on_view_focus)    
    text_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); right_pane.append(toolbar); right_pane.append(text_box_container)
    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_es')}</b>", use_markup=True, xalign=0))
    scrolled_es = Gtk.ScrolledWindow(vexpand=True, hexpand=True, child=text_es_view, hscrollbar_policy="never", min_content_height=80); text_box_container.append(scrolled_es)
    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_en')}</b>", use_markup=True, xalign=0))
    scrolled_en = Gtk.ScrolledWindow(vexpand=True, hexpand=True, child=text_en_view, hscrollbar_policy="never", min_content_height=80); text_box_container.append(scrolled_en)

    preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=True); right_pane.append(preview_container)
    preview_container.append(Gtk.Label(label=f"<b>{i18n_func('preview')}</b>", use_markup=True, xalign=0))
    preview_area = Gtk.DrawingArea(vexpand=True, hexpand=True); preview_area.get_style_context().add_class("view"); preview_container.append(preview_area)
    
    if app.active_cert_path:
        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
        if password: _, state["loaded_cert"] = app.cert_manager.get_credentials(app.active_cert_path, password)

    def draw_preview(area, cr, width, h):
        """Draw callback for the preview area, rendering the current template."""
        cr.save(); cr.set_source_rgb(0.9, 0.9, 0.9); cr.paint()
        text_buffer = text_es_view.get_buffer() if app.i18n.get_language() == "es" else text_en_view.get_buffer()
        text = text_buffer.get_text(text_buffer.get_start_iter(), text_buffer.get_end_iter(), False)
        if state["loaded_cert"]: preview_text = app.get_parsed_stamp_text(state["loaded_cert"], override_template=text)
        else: preview_text = re.sub(r'\$\$SIGNDATE=.*?Z\$\$', "24/12/2025", text.replace("$$SUBJECTCN$$", "Subject Name").replace("$$ISSUERCN$$", "Issuer Name").replace("$$CERTSERIAL$$", "123456789"))
        cr.rectangle(10, 10, width - 20, h - 20); cr.set_source_rgb(1.0, 1.0, 1.0); cr.fill_preserve(); cr.set_source_rgb(0.0, 0.5, 0.0); cr.set_line_width(1.5); cr.stroke()
        layout = PangoCairo.create_layout(cr); layout.set_width(Pango.units_from_double(width - 40)); layout.set_alignment(Pango.Alignment.CENTER); layout.set_markup(preview_text if preview_text else " ", -1)
        ink, logical = layout.get_pixel_extents()
        scale = min((width - 40) / logical.width if logical.width > 0 else 1, (h - 20) / logical.height if logical.height > 0 else 1, 1.0)
        final_w, final_h = logical.width * scale, logical.height * scale; start_x, start_y = (width - final_w) / 2, (h - final_h) / 2
        cr.translate(start_x - (logical.x * scale), start_y - (logical.y * scale)); cr.scale(scale, scale)
        cr.set_source_rgb(0, 0, 0); PangoCairo.show_layout(cr, layout); cr.restore()
    preview_area.set_draw_func(draw_preview); preview_area.connect("resize", lambda a, w, h: a.queue_draw())

    def get_current_form_state():
        """Returns a dictionary with the current data from the form fields."""
        return {"name": name_entry.get_text(), "template_es": text_es_view.get_buffer().get_text(*text_es_view.get_buffer().get_bounds(), False), "template_en": text_en_view.get_buffer().get_text(*text_en_view.get_buffer().get_bounds(), False)}

    def is_form_dirty():
        """Checks if the form data has changed since it was last loaded or saved."""
        return state.get("initial_form_data") is not None and state["initial_form_data"] != get_current_form_state()

    text_es_view.get_buffer().connect("changed", lambda b: preview_area.queue_draw()); text_en_view.get_buffer().connect("changed", lambda b: preview_area.queue_draw()); name_entry.connect("changed", lambda e: preview_area.queue_draw())

    def load_templates_to_combo():
        """Populates the template combo box with all available templates."""
        state["block_combo_changed"] = True; template_combo.remove_all()
        for t in config.get_signature_templates(): template_combo.append(t['id'], t['name'])
        active_id = config.get_active_template_id()
        if active_id: template_combo.set_active_id(active_id)
        else: template_combo.set_active(0)
        state["block_combo_changed"] = False; on_template_changed(template_combo)

    def clear_fields():
        """Clears all input fields in the editor."""
        name_entry.set_text(""); text_es_view.get_buffer().set_text(""); text_en_view.get_buffer().set_text("")

    def load_template_data(template_id):
        """Loads the data for a specific template into the editor fields."""
        template = config.get_template_by_id(template_id)
        state["block_combo_changed"] = True
        if template:
            state["current_id"] = template_id; name_entry.set_text(template['name'])
            text_es_view.get_buffer().set_text(template.get('template_es', '')); text_en_view.get_buffer().set_text(template.get('template_en', ''))
            delete_btn.set_sensitive(len(config.get_signature_templates()) > 1)
            set_active_btn.set_sensitive(config.get_active_template_id() != template_id)
        else: clear_fields()
        state["block_combo_changed"] = False; state["initial_form_data"] = get_current_form_state(); preview_area.queue_draw()

    def on_template_changed(combo):
        """Handles the selection change in the template combo box, checking for unsaved changes."""
        if state["block_combo_changed"]: return
        if is_form_dirty():
            target_id = combo.get_active_id()
            confirm_dialog = Gtk.MessageDialog(transient_for=dialog, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=i18n_func("unsaved_changes_title"), secondary_text=i18n_func("unsaved_changes_message"))
            def on_confirm_response(conf_d, res):
                if res == Gtk.ResponseType.YES: load_template_data(target_id)
                else:
                    state["block_combo_changed"] = True; combo.set_active_id(state["current_id"]); state["block_combo_changed"] = False
                conf_d.destroy()
            confirm_dialog.connect("response", on_confirm_response); confirm_dialog.present()
        else:
            active_id = combo.get_active_id()
            if active_id: load_template_data(active_id)

    def on_new_clicked(btn):
        """Handles the 'New' button click, preparing the form for a new template."""
        if is_form_dirty(): pass
        state["current_id"] = uuid.uuid4().hex; clear_fields()
        name_entry.set_text(i18n_func("new") + " " + i18n_func("templates")[:-1])
        state["initial_form_data"] = get_current_form_state(); name_entry.grab_focus()

    def on_duplicate_clicked(btn):
        """Handles the 'Duplicate' button click, creating a copy of the current template."""
        if not state["current_id"]: return
        state["current_id"] = uuid.uuid4().hex
        name_entry.set_text(name_entry.get_text() + f" ({i18n_func('copy')})")
        state["initial_form_data"] = get_current_form_state()

    def on_save_clicked(btn):
        """Handles the 'Save' button click, saving the current template data."""
        if not state["current_id"]: return
        template_data = {"id": state["current_id"], **get_current_form_state()}; config.save_template(template_data)
        state["initial_form_data"] = get_current_form_state()
        load_templates_to_combo(); template_combo.set_active_id(state["current_id"])

    def on_delete_clicked(btn):
        """Handles the 'Delete' button click, removing the current template after confirmation."""
        if not state["current_id"] or len(config.get_signature_templates()) <= 1: return
        config.delete_template(state["current_id"]); state["current_id"] = None; load_templates_to_combo()

    def on_set_active_clicked(btn):
        """Handles the 'Set as Active' button click, marking the current template for signing."""
        if not state["current_id"]: return
        config.set_active_template_id(state["current_id"]); set_active_btn.set_sensitive(False); app.update_ui()

    new_btn.connect("clicked", on_new_clicked); duplicate_btn.connect("clicked", on_duplicate_clicked); save_btn.connect("clicked", on_save_clicked); delete_btn.connect("clicked", on_delete_clicked); set_active_btn.connect("clicked", on_set_active_clicked)
    template_combo.connect("changed", on_template_changed)

    def on_close_request(d):
        """Handles the dialog close request, checking for unsaved changes before closing."""
        if not is_form_dirty(): return False
        confirm_dialog = Gtk.MessageDialog(transient_for=d, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=i18n_func("unsaved_changes_title"), secondary_text=i18n_func("confirm_close_message"))
        def on_confirm_response(conf_d, res):
            if res == Gtk.ResponseType.YES: d.destroy()
            conf_d.destroy()
        confirm_dialog.connect("response", on_confirm_response); confirm_dialog.present()
        return True

    def on_dialog_response(d, response_id):
        """Handles the main dialog response, specifically the close button."""
        if response_id == Gtk.ResponseType.CLOSE: d.close()

    dialog.connect("response", on_dialog_response)
    dialog.connect("close-request", on_close_request)
    
    load_templates_to_combo()
    dialog.present()
