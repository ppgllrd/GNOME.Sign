# ui/dialogs.py

import gi
gi.require_version("Secret", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo, Gdk, Secret, GLib, Gio
import os

def create_about_dialog(parent, i18n_func):
    """Creates and shows the About dialog."""
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True)
    dialog.set_program_name("GnomeSign")
    dialog.set_version("1.0")
    dialog.set_comments(i18n_func("sign_reason"))
    dialog.set_logo_icon_name("io.github.ppgllrd.GNOME-Sign")
    dialog.set_website("https://github.com/ppgllrd/GNOME.Sign")
    dialog.set_authors(["Pepe Gallardo", "Gemini"])
    dialog.present()

def create_password_dialog(parent, title, message, i18n_func, callback):
    """Creates a generic dialog to request a password for a given action."""
    dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    dialog.add_buttons(i18n_func("cancel"), Gtk.ResponseType.CANCEL, i18n_func("accept"), Gtk.ResponseType.OK)
    ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    ok_button.get_style_context().add_class("suggested-action")
    dialog.set_default_widget(ok_button)
    
    content_area = dialog.get_content_area()
    content_area.set_spacing(10)
    content_area.set_margin_top(10); content_area.set_margin_bottom(10)
    content_area.set_margin_start(10); content_area.set_margin_end(10)
    
    content_area.append(Gtk.Label(label=f"<b>{message}</b>", use_markup=True))
    password_entry = Gtk.Entry(visibility=False, placeholder_text=i18n_func("password"))
    content_area.append(password_entry)
    password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))

    def on_response(d, response_id):
        password = password_entry.get_text() if response_id == Gtk.ResponseType.OK else None
        callback(password)
        d.destroy()

    dialog.connect("response", on_response)
    dialog.present()

def show_error_dialog(parent, title, message):
    """Displays a simple, modal error dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title
    )
    dialog.set_secondary_text(message)
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.present()