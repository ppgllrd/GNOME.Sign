# ui/dialogs.py

import gi
gi.require_version("Secret", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo, Gdk, Secret, GLib, Gio
import os
from datetime import datetime

# La función create_stamp_editor_dialog ha sido eliminada y movida a su propia clase.

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
        nonlocal response_id; response_id = res
        d.destroy()
        if loop.is_running(): loop.quit()
    dialog.connect("response", on_response)
    dialog.present()
    if dialog.is_visible(): loop.run()
    return response_id