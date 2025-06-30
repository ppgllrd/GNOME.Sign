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
            expiry_markup = f"<span color='red'><b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')} (Expired)</span>"
        elif expires < (now + timedelta(days=30)):
            expiry_markup = f"<span color='orange'><b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')}</span>"
        else:
            expiry_markup = f"<b>{i18n_func('expires')}:</b> {expires.strftime('%Y-%m-%d')}"

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
    
    def on_dialog_close_request(editor_dialog, *args):
        if not state["dirty"]:
            return False # False permite que el cierre continúe.

        # Si hay cambios, mostramos un diálogo de confirmación.
        confirm_dialog = Gtk.MessageDialog(
            transient_for=editor_dialog,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=i18n_func("unsaved_changes_title"),
            secondary_text=i18n_func("confirm_close_message")
        )

        # Esta es la función que se ejecuta cuando el usuario responde a la confirmación.
        def on_confirm_response(conf_d, confirm_res_id):
            # Si el usuario dice SÍ, queremos cerrar.
            if confirm_res_id == Gtk.ResponseType.YES:
                # Forzamos la destrucción del diálogo editor original.
                editor_dialog.destroy()
            
            # En cualquier caso, el diálogo de confirmación ya ha cumplido su misión.
            conf_d.destroy()

        confirm_dialog.connect("response", on_confirm_response)
        confirm_dialog.present()

        return True

    # Cambiamos la señal a la que nos conectamos
    dialog.connect("close-request", on_dialog_close_request)
    
    # También necesitamos un manejador simple para el botón "Cerrar" explícito
    def on_explicit_close_button(d, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            # Emulamos lo que haría el usuario al cerrar la ventana
            if not d.close():
                # Si close() devuelve False, significa que se puede destruir.
                d.destroy()
        else:
             # Para otras respuestas (si las hubiera), simplemente destruimos.
            d.destroy()

    # Reemplazamos la conexión anterior de "response" por esta
    dialog.connect("response", on_explicit_close_button)

    load_templates_to_combo()
    dialog.present()

def create_password_dialog(parent, i18n_func, pkcs12_path, callback):
    """Creates a dialog to ask for a certificate's password."""
    dialog = Gtk.Dialog(title=i18n_func("password"), transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    
    ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    ok_button.get_style_context().add_class("suggested-action")
    dialog.set_default_widget(ok_button)

    content_area = dialog.get_content_area()
    content_area.set_spacing(10)
    content_area.set_margin_top(10)
    content_area.set_margin_bottom(10)
    content_area.set_margin_start(10)
    content_area.set_margin_end(10)
    
    content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
    password_entry = Gtk.Entry(visibility=False, placeholder_text=i18n_func("password"))
    content_area.append(password_entry)
    
    password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))

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
    Displays a simple message dialog and returns the response synchronously (GTK4 compatible).
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=message_type,
        buttons=buttons,
        text=title,
        secondary_text=message
    )
    
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
    
    if dialog.is_visible():
        loop.run()

    return response_id

def create_jump_to_page_dialog(parent, app, callback):
    """Creates a dialog to jump to a specific page."""
    i18n_func = app._
    current_page = app.current_page + 1
    max_page = len(app.doc)

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
    
    dialog.set_default_widget(spin_button)
    spin_button.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))

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
    dialog.add_button(i18n_func("close_button"), Gtk.ResponseType.CLOSE)
    
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

    # --- State and Helper Functions for Editor ---
    state = {
        "current_id": None, "block_combo_changed": False, "dirty": False, 
        "loaded_cert": None, "last_focused_view": None
    }
    
    text_es_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    text_en_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    state["last_focused_view"] = text_es_view

    def get_focused_buffer_and_bounds():
        view = state.get("last_focused_view")
        if not view: return None, None, None
        buffer = view.get_buffer()
        bounds = buffer.get_selection_bounds()
        if not bounds: return None, None, None
        return buffer, *bounds

    def toggle_pango_tag(tag):
        buffer, start, end = get_focused_buffer_and_bounds()
        if not buffer: return
        
        text = buffer.get_text(start, end, True)
        if text.strip().startswith(f"<{tag}>") and text.strip().endswith(f"</{tag}>"):
            unwrapped_text = re.sub(f'^\\s*<{tag}>(.*?)</{tag}>\\s*$', r'\1', text, flags=re.DOTALL)
            buffer.delete(start, end)
            buffer.insert(start, unwrapped_text)
        else:
            buffer.delete(start, end)
            buffer.insert(start, f"<{tag}>{text}</{tag}>")

    def apply_span_tag(attribute, value):
        buffer, start, end = get_focused_buffer_and_bounds()
        if not buffer: return
        text = buffer.get_text(start, end, True)
        buffer.delete(start, end)
        buffer.insert(start, f'<span {attribute}="{value}">{text}</span>')

    def _rgba_to_hex(rgba):
        return f"#{int(rgba.red * 255):02x}{int(rgba.green * 255):02x}{int(rgba.blue * 255):02x}"

    # --- Editor Toolbar ---
    toolbar = Gtk.Box(spacing=6)
    
    bold_btn = Gtk.Button.new_from_icon_name("format-text-bold-symbolic")
    bold_btn.set_tooltip_text(i18n_func("bold_tooltip"))
    bold_btn.connect("clicked", lambda b: toggle_pango_tag("b"))

    italic_btn = Gtk.Button.new_from_icon_name("format-text-italic-symbolic")
    italic_btn.set_tooltip_text(i18n_func("italic_tooltip"))
    italic_btn.connect("clicked", lambda b: toggle_pango_tag("i"))
    
    font_combo = Gtk.ComboBoxText.new()
    font_combo.set_tooltip_text(i18n_func("font_tooltip"))
    
    font_combo.append("placeholder_id", i18n_func("font")) # 1. Añadir item placeholder
    safe_fonts = ["Times-Roman", "Helvetica", "Courier"]
    for font in safe_fonts:
        font_combo.append_text(font)
    font_combo.set_active_id("placeholder_id") # 2. Seleccionarlo por defecto
    
    def on_font_changed(combo):
        font_name = combo.get_active_text()
        active_id = combo.get_active_id()
        
        # 3. Ignorar si se selecciona el placeholder
        if not font_name or active_id == "placeholder_id":
            return
            
        apply_span_tag("font_family", font_name)
        # Opcional: resetear para que vuelva a mostrar "Fuente"
        GLib.idle_add(combo.set_active_id, "placeholder_id")

    font_combo.connect("changed", on_font_changed)


    size_combo = Gtk.ComboBoxText.new()
    size_combo.set_tooltip_text(i18n_func("size_tooltip"))
    
    size_combo.append("placeholder_id", i18n_func("size")) # 1. Añadir item placeholder
    pango_size_map = {
        i18n_func("size_small"): "small",
        i18n_func("size_normal"): "medium",
        i18n_func("size_large"): "large",
        i18n_func("size_huge"): "x-large"
    }
    for label in pango_size_map.keys():
        size_combo.append_text(label)
    size_combo.set_active_id("placeholder_id") # 2. Seleccionarlo por defecto

    def on_size_changed(combo):
        active_text = combo.get_active_text()
        active_id = combo.get_active_id()

        # 3. Ignorar si se selecciona el placeholder
        if not active_text or active_id == "placeholder_id":
            return
            
        pango_size = pango_size_map.get(active_text)
        if pango_size:
            apply_span_tag("size", pango_size)
        
        # Opcional: resetear para que vuelva a mostrar "Tamaño"
        GLib.idle_add(combo.set_active_id, "placeholder_id")
    
    size_combo.connect("changed", on_size_changed)
    
    color_btn = Gtk.ColorButton.new()
    color_btn.set_tooltip_text(i18n_func("color_tooltip"))
    color_btn.connect("color-set", lambda b: apply_span_tag("color", _rgba_to_hex(b.get_rgba())))
    
    toolbar.append(bold_btn)
    toolbar.append(italic_btn)
    toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
    toolbar.append(font_combo)
    toolbar.append(size_combo)
    toolbar.append(color_btn)

    # --- Text Views ---
    def on_view_focus(widget, param_spec):
        if widget.get_property("has-focus"):
            state["last_focused_view"] = widget

    text_es_view.connect("notify::has-focus", on_view_focus)
    text_en_view.connect("notify::has-focus", on_view_focus)
    
    text_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=False)
    right_pane.append(toolbar) 
    right_pane.append(text_box_container)
    
    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_es')}</b>", use_markup=True, xalign=0))
    scrolled_es = Gtk.ScrolledWindow(child=text_es_view, hscrollbar_policy="never", min_content_height=80)
    text_box_container.append(scrolled_es)

    text_box_container.append(Gtk.Label(label=f"<b>{i18n_func('template_en')}</b>", use_markup=True, xalign=0))
    scrolled_en = Gtk.ScrolledWindow(child=text_en_view, hscrollbar_policy="never", min_content_height=80)
    text_box_container.append(scrolled_en)
    
    # --- Preview Area and Logic ---
    preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, vexpand=True, hexpand=True)
    right_pane.append(preview_container)
    preview_container.append(Gtk.Label(label=f"<b>{i18n_func('preview')}</b>", use_markup=True, xalign=0))
    preview_area = Gtk.DrawingArea(vexpand=True, hexpand=True)
    preview_area.get_style_context().add_class("view")
    preview_container.append(preview_area)
    
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
            preview_text = app.get_parsed_stamp_text(state["loaded_cert"], override_template=text)
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
            if res != Gtk.ResponseType.YES:
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

    # --- UBICACIÓN: DENTRO DE create_stamp_editor_dialog en ui/dialogs.py ---

# Borra las implementaciones anteriores de on_dialog_response, on_explicit_close_button, y on_dialog_close_request.
# Reemplázalas por esta única función y su conexión.

    def on_dialog_response(d, response_id):
        # La 'X' de la ventana emite DELETE_EVENT, el botón "Cerrar" emite CLOSE.
        is_close_action = (response_id == Gtk.ResponseType.CLOSE or response_id == Gtk.ResponseType.DELETE_EVENT)

        # Si hay cambios sin guardar y el usuario intenta cerrar...
        if state["dirty"] and is_close_action:
            
            # ¡LA CLAVE! Detenemos la señal AHORA.
            # Esto evita que el manejador por defecto destruya el diálogo bajo nuestros pies.
            d.stop_emission_by_name("response")

            # Ahora podemos mostrar nuestro diálogo de confirmación de forma segura.
            confirm_dialog = Gtk.MessageDialog(
                transient_for=d,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=i18n_func("unsaved_changes_title"),
                secondary_text=i18n_func("confirm_close_message")
            )

            def on_confirm_response(conf_d, confirm_res_id):
                # Si el usuario confirma que quiere cerrar...
                if confirm_res_id == Gtk.ResponseType.YES:
                    # ...ahora sí, destruimos el diálogo editor original.
                    d.destroy()
                
                # En cualquier caso, el diálogo de confirmación ya ha cumplido su misión.
                conf_d.destroy()

            confirm_dialog.connect("response", on_confirm_response)
            confirm_dialog.present()
        else:
            # Si no hay cambios o la acción no es de cierre, simplemente destruimos el diálogo.
            d.destroy()

    # Conecta SOLAMENTE esta función a la señal "response".
    # Esta única conexión manejará todos los casos de cierre.
    dialog.connect("response", on_dialog_response)

    # Elimina cualquier otra conexión a "close-request" o "response" que hayas añadido antes.
    
    load_templates_to_combo()
    dialog.present()