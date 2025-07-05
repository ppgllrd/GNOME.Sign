# ui/preferences_window.py
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Secret
from datetime import datetime, timezone, timedelta
import os
from certificate_manager import KEYRING_SCHEMA

class PreferencesWindow(Adw.PreferencesWindow):
    """A window for managing application preferences, including language and certificates."""
    def __init__(self, initial_page_name=None, **kwargs): 
        """Initializes the preferences window."""
        super().__init__(**kwargs)
        self.app = self.get_application()
        self.i18n = self.app.i18n
        self.set_destroy_with_parent(True)
        self.set_modal(False)
        self.set_hide_on_close(False)
        
        self._build_ui()
        self._update_texts() 
        self.update_ui()

        self.app.connect("language-changed", self._on_language_changed)
        self.app.connect("certificates-changed", self._on_certificates_changed) 

        if initial_page_name:
            self.set_visible_page_name(initial_page_name) 


        self.connect("destroy", self.on_preferences_window_destroyed)
        
    def on_preferences_window_destroyed(self, widget):
        print("Preferences window closed") 

    def _on_certificates_changed(self, app): 
        """Callback for the 'certificates-changed' signal."""
        self.update_ui()

    def _build_ui(self):
        """Constructs the static parts of the preferences UI."""
        self.page_general = Adw.PreferencesPage.new()
        self.page_general.set_name("general") 
        self.add(self.page_general)
        
        self.lang_group = Adw.PreferencesGroup.new()
        self.page_general.add(self.lang_group)
        
        model = Gtk.StringList.new(["Español", "English"])
        self.lang_row = Adw.ComboRow.new()
        self.lang_row.set_model(model)
        current_lang_code = self.i18n.get_language()
        self.lang_row.set_selected(0 if current_lang_code == "es" else 1)
        self.lang_row.connect("notify::selected", self._on_language_changed_selection)
        self.lang_group.add(self.lang_row)

        self.signing_group = Adw.PreferencesGroup.new()
        self.page_general.add(self.signing_group)

        self.reason_row = Adw.EntryRow.new()
        self.reason_row.connect("notify::text", self._on_reason_changed)
        self.signing_group.add(self.reason_row)

        self.location_row = Adw.EntryRow.new()
        self.location_row.connect("notify::text", self._on_location_changed)
        self.signing_group.add(self.location_row)
        
        self.certs_page = Adw.PreferencesPage.new()
        self.certs_page.set_name("certificates") 
        self.add(self.certs_page)

    def _update_texts(self):
        """Updates all translatable text elements in the window."""
        self.set_title(self.i18n._("preferences"))
        self.page_general.set_title(self.i18n._("general"))
        self.page_general.set_icon_name("preferences-system-symbolic")
        self.lang_group.set_title(self.i18n._("language"))
        self.lang_row.set_title(self.i18n._("language"))
        self.signing_group.set_title(self.i18n._("signature_settings"))
        self.reason_row.set_title(self.i18n._("signature_reason"))
        self.reason_row.set_tooltip_text(self.i18n._("reason_placeholder"))
        self.location_row.set_title(self.i18n._("signature_location"))
        self.location_row.set_tooltip_text(self.i18n._("location_placeholder"))
        self.certs_page.set_title(self.i18n._("certificates"))
        self.certs_page.set_icon_name("dialog-password-symbolic")
        self.update_ui() # Re-build the dynamic certificate list with new translations

    def _on_language_changed(self, app):
        """Callback for the 'language-changed' signal from the application."""
        self._update_texts()

    def _on_language_changed_selection(self, combo_row, param):
        """Handles the language selection change."""
        selected_idx = combo_row.get_selected()
        lang_code = "es" if selected_idx == 0 else "en"
        self.app.change_action_state("change_lang", GLib.Variant('s', lang_code))

    def update_ui(self):
        """Updates the UI, primarily by rebuilding the dynamic list of certificates."""
        # Rebuilding the group is a robust way to handle dynamic content.
        if hasattr(self, 'certs_group') and self.certs_group.get_parent():
            self.certs_page.remove(self.certs_group)
        
        self.certs_group = Adw.PreferencesGroup()
        self.certs_page.add(self.certs_group)

        self.reason_row.set_text(self.app.config.get_signature_reason())
        self.location_row.set_text(self.app.config.get_signature_location())
        
        cert_details_list = self.app.cert_manager.get_all_certificate_details()
        radio_group = None

        for cert in cert_details_list:
            row = Adw.ExpanderRow.new()
            row.set_title(cert['subject_cn'])
            
            check_button = Gtk.CheckButton.new()
            if radio_group: check_button.set_group(radio_group)
            else: radio_group = check_button
            
            check_button.set_active(cert['path'] == self.app.active_cert_path)
            check_button.connect("toggled", self._on_cert_toggled, cert['path'])
            row.add_prefix(check_button)
            row.set_activatable(False)
            
            now = datetime.now(timezone.utc); expires = cert['expires']
            if expires < now: expiry_text = f"({self.app._('expired')})"; row.add_css_class("error")
            elif expires < (now + timedelta(days=30)): expiry_text = f"({self.app._('expires_soon')})"; row.add_css_class("warning")
            else: expiry_text = ""
            row.set_subtitle(f"{self.app._('expires')}: {expires.strftime('%Y-%m-%d')} {expiry_text}")
            
            details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6)
            details_box.append(Gtk.Label(label=f"<b>{self.app._('issuer')}:</b> {cert['issuer_cn']}", use_markup=True, xalign=0, wrap=True))
            details_box.append(Gtk.Label(label=f"<b>{self.app._('serial')}:</b> {cert['serial']}", use_markup=True, xalign=0, wrap=True))
            details_box.append(Gtk.Label(label=f"<b>{self.app._('path')}:</b> <small>{cert['path']}</small>", use_markup=True, xalign=0, wrap=True))
            row.add_row(details_box)

            delete_button = Gtk.Button.new_with_label(self.app._("delete")); delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.get_style_context().add_class("destructive-action")
            delete_button.connect("clicked", self._on_delete_cert_clicked, cert['path'])
            delete_row = Adw.ActionRow.new(); delete_row.add_prefix(delete_button); row.add_row(delete_row)
            self.certs_group.add(row)

        add_button = Gtk.Button.new_with_label(self.app._("add_certificate"))
        add_button.get_style_context().add_class("suggested-action")
        add_button.connect("clicked", self._on_add_cert_clicked)
        add_row = Adw.ActionRow.new(); add_row.set_halign(Gtk.Align.CENTER); add_row.add_prefix(add_button)
        self.certs_group.add(add_row)
    
    def _on_add_cert_clicked(self, button):
        """Opens a file chooser to add a new certificate."""
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file: self._process_certificate_selection(file.get_path())
        
        # Use Gtk.FileChooserNative for better desktop integration
        file_chooser = Gtk.FileChooserNative.new(
            self.app._("open_cert_dialog_title"), # title
            self,                                 # transient_for (this window)
            Gtk.FileChooserAction.OPEN,           # action
            self.app._("open"),                   # accept_label
            self.app._("cancel")                  # cancel_label
        )

        filter_p12 = Gtk.FileFilter()
        filter_p12.set_name(self.app._("p12_files"))
        filter_p12.add_pattern("*.p12")
        filter_p12.add_pattern("*.pfx")
        file_chooser.add_filter(filter_p12)
        
        file_chooser.connect("response", on_response)
        file_chooser.show()

    def _on_cert_toggled(self, button, path):
        """Notifica a la app que se ha seleccionado un nuevo certificado activo."""
        if button.get_active():
            # Correcto: Llama al método centralizado en la app.
            self.app.set_active_certificate(path)
    
    def _on_delete_cert_clicked(self, button, path):
        """Pide a la app que elimine un certificado, después de confirmación."""
        confirm_dialog = Gtk.MessageDialog(
            transient_for=self, 
            modal=True, 
            message_type=Gtk.MessageType.QUESTION, 
            buttons=Gtk.ButtonsType.YES_NO, 
            text=self.app._("confirm_delete_cert_title"), 
            secondary_text=self.app._("confirm_delete_cert_message")
        )
        
        def on_confirm(d, res):
            if res == Gtk.ResponseType.YES:
                # Correcto: La ventana solo pide la acción, no la ejecuta.
                self.app.remove_certificate(path)
            d.destroy()
            
        confirm_dialog.connect("response", on_confirm)
        confirm_dialog.present()

    def _process_certificate_selection(self, pkcs12_path):
        """
        Muestra un diálogo para pedir la contraseña y luego pide a la app 
        que añada el certificado.
        """
        dialog = Gtk.Dialog(title=self.app._("password"), transient_for=self, modal=True)
        dialog.add_buttons(self.i18n._("cancel"), Gtk.ResponseType.CANCEL, self.i18n._("accept"), Gtk.ResponseType.OK)
        ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        ok_button.get_style_context().add_class("suggested-action")
        dialog.set_default_widget(ok_button)
        
        content_area = dialog.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_top(10); content_area.set_margin_bottom(10)
        content_area.set_margin_start(10); content_area.set_margin_end(10)
        
        content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
        password_entry = Gtk.Entry(visibility=False, placeholder_text=self.app._("password"))
        content_area.append(password_entry)
        password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))

        def on_response(d, res):
            if res == Gtk.ResponseType.OK:
                # Pide a la app que realice la acción de añadir.
                self.app.add_certificate(pkcs12_path, password_entry.get_text())
            d.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_reason_changed(self, entry_row, param):
        """Saves the reason when it's changed by the user."""
        self.app.config.set_signature_reason(entry_row.get_text())
        self.app.config.save()

    def _on_location_changed(self, entry_row, param):
        """Saves the location when it's changed by the user."""
        self.app.config.set_signature_location(entry_row.get_text())
        self.app.config.save()