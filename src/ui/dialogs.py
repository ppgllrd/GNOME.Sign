import gi
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo, Gdk, Secret, GLib
import os
import uuid
import copy
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
        cert_path = row_to_delete.cert_path
        response = show_message_dialog(dialog, i18n_func("confirm_delete_cert_title"), 
                                       i18n_func("confirm_delete_cert_message"), 
                                       Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
        
        if response == Gtk.ResponseType.YES:
            app.cert_manager.remove_credentials_from_keyring(cert_path)
            app.config.remove_cert_path(cert_path)
            app.cert_manager.remove_cert_path(cert_path)
            
            listbox.remove(row_to_delete)
            if app.active_cert_path == cert_path:
                app.active_cert_path = None
            app.update_ui()

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
            expiry_markup = f"<span color='red'><b>Expires:</b> {expires.strftime('%Y-%m-%d')} (Expired)</span>"
        elif expires < (now + timedelta(days=30)):
            expiry_markup = f"<span color='orange'><b>Expires:</b> {expires.strftime('%Y-%m-%d')}</span>"
        else:
            expiry_markup = f"<b>Expires:</b> {expires.strftime('%Y-%m-%d')}"

        details_label = Gtk.Label(xalign=0)
        details_label.set_wrap(True)
        details_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        details_text = (
            f"<small>{expiry_markup}\n"
            f"<i>{i18n_func('issuer')}:</i> {cert['issuer_cn']}\n"
            f"<i>{i18n_func('serial')}:</i> {cert['serial']}\n"
            f"<i>{i18n_func('path')}:</i> {cert['path']}</small>"
        )
        details_label.set_markup(details_text)
        item_box.append(details_label)
        
        row.set_child(main_hbox)
        listbox.append(row)

        if cert['path'] == app.active_cert_path:
            active_row = row
    
    if active_row:
        listbox.select_row(active_row)

    def on_row_activated(box, row):
        if row:
            app.active_cert_path = row.cert_path
            app.update_ui()
            dialog.response(Gtk.ResponseType.OK)

    listbox.connect("row-activated", on_row_activated)
    
    scrolled = Gtk.ScrolledWindow(hscrollbar_policy="never", vexpand=True, hexpand=True)
    scrolled.set_child(listbox)
    dialog.get_content_area().append(scrolled)
    
    def on_dialog_response(d, response_id):
        if response_id == Gtk.ResponseType.APPLY:
            app.on_load_certificate_clicked(None, None)
        d.destroy()

    dialog.connect("response", on_dialog_response)
    dialog.show()

def create_password_dialog(parent, i18n_func, pkcs12_path, callback):
    """Creates a dialog to ask for a certificate's password."""
    dialog = Gtk.Dialog(title=i18n_func("password"), transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    
    content_area = dialog.get_content_area()
    content_area.set_spacing(10)
    content_area.set_margin_top(10)
    content_area.set_margin_bottom(10)
    content_area.set_margin_start(10)
    content_area.set_margin_end(10)
    
    content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
    password_entry = Gtk.Entry(visibility=False, placeholder_text=i18n_func("password"))
    content_area.append(password_entry)
    
    def on_response(d, response_id):
        password = None
        if response_id == Gtk.ResponseType.OK:
            password = password_entry.get_text()
        callback(password)
        d.destroy()

    dialog.connect("response", on_response)
    dialog.present()
    
def show_message_dialog(parent, title, message, message_type, buttons=Gtk.ButtonsType.OK):
    """
    Displays a simple message dialog and returns the response synchronously.
    This is a helper for simple confirmation dialogs.
    """
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=message_type, buttons=buttons, text=title, secondary_text=message)
    
    response_id = Gtk.ResponseType.NONE
    loop = GLib.MainLoop()

    def on_response(d, res):
        nonlocal response_id
        response_id = res
        d.destroy()
        if loop.is_running():
            loop.quit()

    dialog.connect("response", on_response)
    dialog.present()
    loop.run()

    return response_id

def create_jump_to_page_dialog(parent, i18n_func, current_page, max_page, callback):
    """Creates a dialog to jump to a specific page."""
    dialog = Gtk.Dialog(title=i18n_func("jump_to_page_title"), transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    
    content_area = dialog.get_content_area()
    content_area.set_spacing(10)
    content_area.set_margin_top(10)
    content_area.set_margin_bottom(10)
    content_area.set_margin_start(10)
    content_area.set_margin_end(10)
    
    content_area.append(Gtk.Label(label=i18n_func("jump_to_page_prompt").format(max_page)))
    
    adjustment = Gtk.Adjustment(value=current_page, lower=1, upper=max_page, step_increment=1, page_increment=10, page_size=0)
    spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
    content_area.append(spin_button)
    
    def on_response(d, response_id):
        page_num = None
        if response_id == Gtk.ResponseType.OK:
            page_num = spin_button.get_value_as_int() - 1 
        callback(page_num)
        d.destroy()

    dialog.connect("response", on_response)
    dialog.present()

def create_stamp_editor_dialog(parent, app, config):
    """Creates the signature stamp template editor dialog."""
    i18n_func = app._
    dialog = Gtk.Dialog(title=i18n_func("edit_stamp_templates"), transient_for=parent, modal=True, width_request=700, height_request=600)
    dialog.add_button("_Close", Gtk.ResponseType.CLOSE)
    
    main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
    dialog.get_content_area().append(main_box)

    left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=220)
    main_box.append(left_pane)

    right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
    main_box.append(right_pane)

    # --- Left Pane ---
    left_pane.append(Gtk.Label(label=f"<b>{i18n_func('templates')}</b>", use_markup=True, xalign=0))
    template_combo = Gtk.ComboBoxText()
    left_pane.append(template_combo)
    
    btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12)
    left_pane.append(btn_box)
    new_btn = Gtk.Button.new_with_label(i18n_func("new"))
    duplicate_btn = Gtk.Button.new_with_label(i18n_func("duplicate"))
    save_btn = Gtk.Button.new_with_label(i18n_func("save"))
    delete_btn = Gtk.Button.new_with_label(i18n_func("delete"))
    set_active_btn = Gtk.Button.new_with_label(i18n_func("set_as_active"))
    btn_box.append(new_btn)
    btn_box.append(duplicate_btn)
    btn_box.append(save_btn)
    btn_box.append(delete_btn)
    btn_box.append(set_active_btn)

    # --- Right Pane ---
    right_pane.append(Gtk.Label(label=f"<b>{i18n_func('template_name')}</b>", use_markup=True, xalign=0))
    name_entry = Gtk.Entry()
    right_pane.append(name_entry)

    text_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=False)
    right_pane.append(text_box_container)

    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_es')}</b>", use_markup=True, xalign=0))
    text_es_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    scrolled_es = Gtk.ScrolledWindow(child=text_es_view, hscrollbar_policy="never", min_content_height=80)
    text_box_container.append(scrolled_es)

    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_en')}</b>", use_markup=True, xalign=0))
    text_en_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    scrolled_en = Gtk.ScrolledWindow(child=text_en_view, hscrollbar_policy="never", min_content_height=80)
    text_box_container.append(scrolled_en)
    
    preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=True, hexpand=True)
    right_pane.append(preview_container)
    preview_container.append(Gtk.Label(label=f"<b>{i18n_func('preview')}</b>", use_markup=True, xalign=0))
    preview_area = Gtk.DrawingArea(vexpand=True, hexpand=True)
    preview_area.get_style_context().add_class("view")
    preview_container.append(preview_area)
    
    state = {"current_id": None, "block_combo_changed": False, "dirty": False, "loaded_cert": None}

    if app.active_cert_path:
        password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": app.active_cert_path}, None)
        if password:
            _, state["loaded_cert"] = app.cert_manager.get_credentials(app.active_cert_path, password)

    def draw_preview(area, cr, width, h):
        cr.save()
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.paint()
        
        get_buffer = lambda view: view.get_buffer()
        text_buffer = get_buffer(text_es_view) if app.i18n.get_language() == "es" else get_buffer(text_en_view)
        text = text_buffer.get_text(text_buffer.get_start_iter(), text_buffer.get_end_iter(), False)

        if state["loaded_cert"]:
            preview_text = app.get_parsed_stamp_text(state["loaded_cert"], for_html=False, override_template=text)
        else:
            preview_text = text.replace("$$SUBJECTCN$$", "Subject Name").replace("$$ISSUERCN$$", "Issuer Name")
            preview_text = preview_text.replace("$$CERTSERIAL$$", "123456789").replace("$$SIGNDATE=dd/MM/yyyy$$", "24/12/2025")

        cr.rectangle(10, 10, width - 20, h - 20)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.5, 0.0)
        cr.set_line_width(1.5)
        cr.stroke()
        
        layout = PangoCairo.create_layout(cr)
        layout.set_width(Pango.units_from_double(width - 40))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_markup(preview_text if preview_text else " ", -1)
        
        ink_rect, logical_rect = layout.get_pixel_extents()
        
        scale = min((width - 40) / logical_rect.width if logical_rect.width > 0 else 1, 
                    (h - 20) / logical_rect.height if logical_rect.height > 0 else 1, 1.0)
        
        final_w = logical_rect.width * scale
        final_h = logical_rect.height * scale
        start_x = (width - final_w) / 2
        start_y = (h - final_h) / 2
        
        cr.translate(start_x - (logical_rect.x * scale), start_y - (logical_rect.y * scale))
        cr.scale(scale, scale)

        cr.set_source_rgb(0, 0, 0)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    preview_area.set_draw_func(draw_preview)
    preview_area.connect("resize", lambda area, w, h: area.queue_draw())

    def get_current_form_state():
        return {
            "name": name_entry.get_text(),
            "template_es": text_es_view.get_buffer().get_text(*text_es_view.get_buffer().get_bounds(), False),
            "template_en": text_en_view.get_buffer().get_text(*text_en_view.get_buffer().get_bounds(), False)
        }

    def on_field_changed(*args):
        if state["block_combo_changed"]: return
        state["dirty"] = True
        preview_area.queue_draw()

    text_es_view.get_buffer().connect("changed", on_field_changed)
    text_en_view.get_buffer().connect("changed", on_field_changed)
    name_entry.connect("changed", on_field_changed)

    def load_templates_to_combo():
        state["block_combo_changed"] = True
        template_combo.remove_all()
        templates = config.get_signature_templates()
        active_id = config.get_active_template_id()
        active_idx = -1
        for i, t in enumerate(templates):
            template_combo.append(t['id'], t['name'])
            if t['id'] == active_id:
                active_idx = i
        if active_idx != -1:
            template_combo.set_active(active_idx)
        state["block_combo_changed"] = False
        on_template_changed(template_combo)

    def load_template_data(template_id):
        template = config.get_template_by_id(template_id)
        state["block_combo_changed"] = True
        if not template: 
            clear_fields()
        else:
            state["current_id"] = template_id
            name_entry.set_text(template['name'])
            text_es_view.get_buffer().set_text(template.get('template_es', ''))
            text_en_view.get_buffer().set_text(template.get('template_en', ''))
            delete_btn.set_sensitive(len(config.get_signature_templates()) > 1)
            set_active_btn.set_sensitive(config.get_active_template_id() != template_id)
        state["block_combo_changed"] = False
        state["dirty"] = False
        preview_area.queue_draw()

    def clear_fields():
        name_entry.set_text("")
        text_es_view.get_buffer().set_text("")
        text_en_view.get_buffer().set_text("")

    def on_template_changed(combo):
        if state["block_combo_changed"]: return
        if state["dirty"]:
            res = show_message_dialog(dialog, i18n_func("unsaved_changes_title"), i18n_func("unsaved_changes_message"), Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
            if res == Gtk.ResponseType.NO:
                state["block_combo_changed"] = True
                for i, t in enumerate(config.get_signature_templates()):
                    if t['id'] == state["current_id"]:
                        combo.set_active(i)
                        break
                state["block_combo_changed"] = False
                return
        active_id = combo.get_active_id()
        if active_id:
            load_template_data(active_id)

    def on_new_clicked(btn):
        state["current_id"] = uuid.uuid4().hex
        clear_fields()
        name_entry.set_text(i18n_func("new") + " " + i18n_func("templates")[:-1])
        state["dirty"] = True
        name_entry.grab_focus()

    def on_duplicate_clicked(btn):
        if not state["current_id"]: return
        form_data = get_current_form_state()
        state["current_id"] = uuid.uuid4().hex
        name_entry.set_text(form_data["name"] + f" ({i18n_func('copy')})")
        state["dirty"] = True

    def on_save_clicked(btn):
        if not state["current_id"]: return
        template_data = { "id": state["current_id"], **get_current_form_state() }
        config.save_template(template_data)
        state["dirty"] = False
        current_selection_id = state["current_id"]
        load_templates_to_combo()
        state["block_combo_changed"] = True
        for i, t in enumerate(config.get_signature_templates()):
            if t['id'] == current_selection_id:
                template_combo.set_active(i)
                break
        state["block_combo_changed"] = False
        on_template_changed(template_combo)
        
    def on_delete_clicked(btn):
        if not state["current_id"] or len(config.get_signature_templates()) <= 1: return
        config.delete_template(state["current_id"])
        state["current_id"] = None
        load_templates_to_combo()

    def on_set_active_clicked(btn):
        if not state["current_id"]: return
        config.set_active_template_id(state["current_id"])
        set_active_btn.set_sensitive(False)
        app.update_ui()

    new_btn.connect("clicked", on_new_clicked)
    duplicate_btn.connect("clicked", on_duplicate_clicked)
    save_btn.connect("clicked", on_save_clicked)
    delete_btn.connect("clicked", on_delete_clicked)
    set_active_btn.connect("clicked", on_set_active_clicked)
    template_combo.connect("changed", on_template_changed)

    def on_dialog_response(d, response_id):
        should_close = True
        if state["dirty"] and (response_id == Gtk.ResponseType.CLOSE or response_id == Gtk.ResponseType.DELETE_EVENT):
            res = show_message_dialog(d, i18n_func("unsaved_changes_title"), i18n_func("confirm_close_message"), Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
            if res == Gtk.ResponseType.NO:
                should_close = False
        
        if should_close:
            d.destroy()
        else:
            d.stop_emission_by_name("response")

    dialog.connect("response", on_dialog_response)

    load_templates_to_combo()
    dialog.present()