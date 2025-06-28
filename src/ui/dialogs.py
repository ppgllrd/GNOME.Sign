import gi
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo, Gdk
import os
import uuid

def create_about_dialog(parent, i18n_func):
    """Creates and shows the About dialog."""
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True)
    dialog.set_program_name("GnomeSign")
    dialog.set_version("1.2")
    dialog.set_comments(i18n_func("sign_reason"))
    dialog.set_logo_icon_name("org.pepeg.GnomeSign") 
    dialog.set_website("https://github.com/your-repo-here")
    dialog.set_authors(["pepeg"])
    dialog.present()

def create_cert_selector_dialog(parent, i18n_func, cert_map, callback):
    """Creates a dialog to select a certificate from a list."""
    dialog = Gtk.Dialog(title=i18n_func("select_certificate"), transient_for=parent, modal=True)
    dialog.add_button(i18n_func("cancel"), Gtk.ResponseType.CANCEL)
    
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    for name in cert_map.keys():
        listbox.append(Gtk.Label(label=name, xalign=0, margin_start=10, margin_top=5, margin_bottom=5))
    
    def on_row_activated(box, row):
        selected_name = row.get_child().get_label()
        selected_path = cert_map.get(selected_name)
        callback(selected_path)
        dialog.response(Gtk.ResponseType.OK)

    listbox.connect("row-activated", on_row_activated)
    
    scrolled = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic", min_content_height=200, max_content_height=400, child=listbox)
    dialog.get_content_area().append(scrolled)
    dialog.show()
    dialog.connect("response", lambda d, r: d.destroy())

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
    
def show_message_dialog(parent, title, message, message_type):
    """Displays a simple message dialog."""
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=message_type, buttons=Gtk.ButtonsType.OK, text=title, secondary_text=message)
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.present()

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

def create_stamp_editor_dialog(parent, app, i18n_func, config):
    """Creates the signature stamp template editor dialog."""
    dialog = Gtk.Dialog(title=i18n_func("edit_stamp_templates"), transient_for=parent, modal=True, width_request=700)
    dialog.add_button("_Close", Gtk.ResponseType.CLOSE)

    main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
    dialog.get_content_area().append(main_box)

    # --- Left Pane (Template List and Controls) ---
    left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=200)
    main_box.append(left_pane)

    left_pane.append(Gtk.Label(label="<b>Templates</b>", use_markup=True, xalign=0))
    template_combo = Gtk.ComboBoxText()
    left_pane.append(template_combo)

    # --- Right Pane (Editor and Preview) ---
    right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
    main_box.append(right_pane)

    # Editor fields
    right_pane.append(Gtk.Label(label="<b>Template Name</b>", use_markup=True, xalign=0))
    name_entry = Gtk.Entry()
    right_pane.append(name_entry)

    right_pane.append(Gtk.Label(label="<b>Spanish Template (Pango Markup)</b>", use_markup=True, xalign=0))
    text_es_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
    scrolled_es = Gtk.ScrolledWindow(child=text_es_view, hscrollbar_policy="never", min_content_height=100)
    right_pane.append(scrolled_es)

    right_pane.append(Gtk.Label(label="<b>English Template (Pango Markup)</b>", use_markup=True, xalign=0))
    text_en_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
    scrolled_en = Gtk.ScrolledWindow(child=text_en_view, hscrollbar_policy="never", min_content_height=100)
    right_pane.append(scrolled_en)
    
    # --- Preview Area ---
    right_pane.append(Gtk.Label(label="<b>Preview</b>", use_markup=True, xalign=0))
    preview_area = Gtk.DrawingArea(height_request=100, vexpand=False, hexpand=True)
    preview_area.get_style_context().add_class("view")
    right_pane.append(preview_area)

    def draw_preview(area, cr, width, h):
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.paint()
        
        get_buffer = lambda view: view.get_buffer()
        text_buffer = get_buffer(text_es_view) if app.language == "es" else get_buffer(text_en_view)
        text = text_buffer.get_text(text_buffer.get_start_iter(), text_buffer.get_end_iter(), False)

        # Simplified parsing for preview
        preview_text = text.replace("$$SUBJECTCN$$", "Subject Name")
        preview_text = preview_text.replace("$$ISSUERCN$$", "Issuer Name")
        preview_text = preview_text.replace("$$CERTSERIAL$$", "123456789")
        preview_text = preview_text.replace("$$SIGNDATE=dd-MM-yyyy$$", "24-12-2025")
        preview_text = preview_text.replace("$$SIGNDATE=yyyy-MM-dd$$", "2025-12-24")

        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(10, 10, width - 20, h - 20)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.5, 0.0)
        cr.set_line_width(1.5)
        cr.stroke()
        
        layout = PangoCairo.create_layout(cr)
        layout.set_width(Pango.units_from_double(width - 40))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_markup(preview_text, -1)
        
        _, text_height = layout.get_pixel_size()
        cr.move_to(20, 10 + (h - 20 - text_height) / 2)
        cr.set_source_rgb(0, 0, 0)
        PangoCairo.show_layout(cr, layout)

    preview_area.set_draw_func(draw_preview)

    def on_text_changed(buffer):
        preview_area.queue_draw()
    
    text_es_view.get_buffer().connect("changed", on_text_changed)
    text_en_view.get_buffer().connect("changed", on_text_changed)

    # --- Control Buttons ---
    btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    left_pane.append(btn_box)

    new_btn = Gtk.Button.new_with_label("New")
    save_btn = Gtk.Button.new_with_label("Save")
    delete_btn = Gtk.Button.new_with_label("Delete")
    set_active_btn = Gtk.Button.new_with_label("Set as Active")
    btn_box.append(new_btn)
    btn_box.append(save_btn)
    btn_box.append(delete_btn)
    btn_box.append(set_active_btn)

    # --- Functions and State ---
    state = {"current_id": None, "block_combo_changed": False}

    def load_templates_to_combo():
        state["block_combo_changed"] = True
        template_combo.remove_all()
        templates = config.get_signature_templates()
        active_id = config.get_active_template_id()
        for i, t in enumerate(templates):
            template_combo.append(t['id'], t['name'])
            if t['id'] == active_id:
                template_combo.set_active(i)
        state["block_combo_changed"] = False
        on_template_changed(template_combo)

    def load_template_data(template_id):
        template = config.get_template_by_id(template_id)
        if not template: 
            clear_fields()
            return
        state["current_id"] = template_id
        name_entry.set_text(template['name'])
        text_es_view.get_buffer().set_text(template.get('template_es', ''))
        text_en_view.get_buffer().set_text(template.get('template_en', ''))
        delete_btn.set_sensitive(len(config.get_signature_templates()) > 1)
        set_active_btn.set_sensitive(config.get_active_template_id() != template_id)
        preview_area.queue_draw()

    def clear_fields():
        state["current_id"] = None
        name_entry.set_text("")
        text_es_view.get_buffer().set_text("")
        text_en_view.get_buffer().set_text("")

    def on_template_changed(combo):
        if state["block_combo_changed"]: return
        active_id = combo.get_active_id()
        if active_id:
            load_template_data(active_id)

    def on_new_clicked(btn):
        clear_fields()
        state["current_id"] = uuid.uuid4().hex
        name_entry.set_text("New Template")
        name_entry.grab_focus()

    def on_save_clicked(btn):
        if not state["current_id"]: return
        template_data = {
            "id": state["current_id"],
            "name": name_entry.get_text() or "Untitled",
            "template_es": text_es_view.get_buffer().get_text(text_es_view.get_buffer().get_start_iter(), text_es_view.get_buffer().get_end_iter(), False),
            "template_en": text_en_view.get_buffer().get_text(text_en_view.get_buffer().get_start_iter(), text_en_view.get_buffer().get_end_iter(), False),
        }
        config.save_template(template_data)
        load_templates_to_combo()
        # Reselect the saved template
        for i in range(len(template_combo.get_model())):
            if template_combo.get_model()[i][0] == state["current_id"]:
                template_combo.set_active(i)
                break

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

    # --- Connect signals ---
    template_combo.connect("changed", on_template_changed)
    new_btn.connect("clicked", on_new_clicked)
    save_btn.connect("clicked", on_save_clicked)
    delete_btn.connect("clicked", on_delete_clicked)
    set_active_btn.connect("clicked", on_set_active_clicked)

    # --- Initial Load ---
    load_templates_to_combo()
    
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.present()