# ui/dialogs.py
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
import os

def create_about_dialog(parent, i18n_func):
    """Creates and shows the About dialog."""
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True)
    dialog.set_program_name("GnomeSign")
    dialog.set_version("1.1")
    dialog.set_comments(i18n_func("sign_reason"))
    dialog.set_logo_icon_name("org.pepeg.GnomeSign") # Assuming you have an icon with this name
    dialog.set_website("https://github.com/your-repo-here")
    dialog.set_authors(["pepeg"])
    dialog.present()

def create_cert_selector_dialog(parent, i18n_func, cert_map, callback):
    """
    Creates a dialog to select a certificate from a list.

    Args:
        parent: The parent window.
        i18n_func: The translation function.
        cert_map (dict): A dictionary mapping common names to file paths.
        callback: The function to call with the selected path on activation.
    """
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
    """
    Creates a dialog to ask for a certificate's password.

    Args:
        parent: The parent window.
        i18n_func: The translation function.
        pkcs12_path (str): The path to the certificate file.
        callback: The function to call with the entered password.
    """
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
