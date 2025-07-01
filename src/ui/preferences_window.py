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
        
    def _on_cert_toggled(self, button, path):
        """Handles the selection of an active certificate."""
        if button.get_active():
            self.app.active_cert_path = path
            self.app.config.set_active_cert_path(path)
            self.app.update_ui()
    
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

    def _on_delete_cert_clicked(self, button, path):
        """Handles the deletion of a certificate after user confirmation."""
        confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.app._("confirm_delete_cert_title"), secondary_text=self.app._("confirm_delete_cert_message"))
        def on_confirm(d, res):
            if res == Gtk.ResponseType.YES:
                self.app.cert_manager.remove_credentials_from_keyring(path); self.app.config.remove_cert_path(path)
                self.app.cert_manager.remove_cert_path(path)
                if self.app.active_cert_path == path:
                    certs = self.app.cert_manager.get_all_certificate_details()
                    new_path = certs[0]['path'] if certs else None
                    self.app.active_cert_path = new_path; self.app.config.set_active_cert_path(new_path)
                self.app.emit("certificates-changed") 
            d.destroy()
        confirm_dialog.connect("response", on_confirm); confirm_dialog.present()

    def _process_certificate_selection(self, pkcs12_path):
        """Processes the selected certificate file, requesting a password and storing it."""
        def on_password_response(password):
            if password is None: return
            common_name = self.app.cert_manager.test_certificate(pkcs12_path, password)
            if common_name:
                Secret.password_store_sync(KEYRING_SCHEMA, {"path": pkcs12_path}, Secret.COLLECTION_DEFAULT, f"Certificate password for {common_name}", password, None)
                self.app.config.add_cert_path(pkcs12_path); self.app.config.set_last_folder(os.path.dirname(pkcs12_path)); self.app.config.save()
                self.app.cert_manager.add_cert_path(pkcs12_path)
                self.app.active_cert_path = pkcs12_path; self.app.config.set_active_cert_path(pkcs12_path)
                self.app.emit("certificates-changed")
            else:
                if self.app.window: self.app.window.show_toast(self.app._("bad_password_or_file"))
        dialog = Gtk.Dialog(title=self.app._("password"), transient_for=self, modal=True)
        dialog.add_buttons(self.i18n._("cancel"), Gtk.ResponseType.CANCEL, self.i18n._("accept"), Gtk.ResponseType.OK)
        ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK); ok_button.get_style_context().add_class("suggested-action"); dialog.set_default_widget(ok_button)
        content_area = dialog.get_content_area(); content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
        content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
        password_entry = Gtk.Entry(visibility=False, placeholder_text=self.app._("password")); content_area.append(password_entry)
        password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        def on_response(d, res):
            on_password_response(password_entry.get_text() if res == Gtk.ResponseType.OK else None)
            d.destroy()
        dialog.connect("response", on_response); dialog.present()
