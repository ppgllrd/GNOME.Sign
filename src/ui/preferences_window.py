# ui/preferences_window.py
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib
from datetime import datetime, timezone, timedelta
import os

class PreferencesWindow(Adw.PreferencesWindow):
    """A window for managing application preferences, including language and certificates."""
    def __init__(self, initial_page_name=None, **kwargs): 
        """Initializes the preferences window."""
        super().__init__(**kwargs)
        self.app = self.get_application()
        self.i18n = self.app.i18n

        self.set_transient_for(self.app.window)

        self.set_destroy_with_parent(True)
        self.set_modal(False) 
        self.set_hide_on_close(True)
        
        self._build_ui()
        self._update_texts() 
        self.update_ui()

        self.app.connect("language-changed", self._on_language_changed)
        self.app.connect("certificates-changed", self._on_certificates_changed) 

        if initial_page_name:
            self.set_visible_page_name(initial_page_name) 

        # Save config when the window is destroyed (closed)
        self.connect("destroy", lambda w: self.app.config.save())
        
    def _on_certificates_changed(self, app): 
        """Callback for the 'certificates-changed' signal to refresh the list."""
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
        self.set_title(_("Preferences"))
        self.page_general.set_title(_("General"))
        self.page_general.set_icon_name("preferences-system-symbolic")
        self.lang_group.set_title(_("Language"))
        self.lang_row.set_title(_("Language"))
        self.signing_group.set_title(_("Signature Settings"))
        self.reason_row.set_title(_("Default signing reason"))
        self.reason_row.set_tooltip_text(_("e.g., I agree to the terms"))
        self.location_row.set_title(_("Default signing location"))
        self.location_row.set_tooltip_text(_("e.g., Madrid, Spain"))
        self.certs_page.set_title(_("Certificates"))
        self.certs_page.set_icon_name("dialog-password-symbolic")
        self.update_ui()

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
        if hasattr(self, 'certs_group') and self.certs_group.get_parent():
            self.certs_page.remove(self.certs_group)
        
        self.certs_group = Adw.PreferencesGroup()
        self.certs_page.add(self.certs_group)

        self.reason_row.set_text(self.app.config.get_signature_reason())
        self.location_row.set_text(self.app.config.get_signature_location())
        
        cert_details_list = self.app.cert_manager.get_all_certificate_details()
        cert_details_list = sorted(cert_details_list, key=lambda cert: cert['subject_cn'].lower())
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
            if expires < now: expiry_text = f"({_('Expired')})"; row.add_css_class("error")
            elif expires < (now + timedelta(days=30)): expiry_text = f"({_('Expires soon')})"; row.add_css_class("warning")
            else: expiry_text = ""
            row.set_subtitle(f"{_('Expires')}: {expires.strftime('%Y-%m-%d')} {expiry_text}")
            
            details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6)
            details_box.append(Gtk.Label(label=f"<b>{_('Issuer')}:</b> {cert['issuer_cn']}", use_markup=True, xalign=0, wrap=True))
            details_box.append(Gtk.Label(label=f"<b>{_('Serial')}:</b> {cert['serial']}", use_markup=True, xalign=0, wrap=True))
            details_box.append(Gtk.Label(label=f"<b>{_('Path')}:</b> <small>{cert['path']}</small>", use_markup=True, xalign=0, wrap=True))
            row.add_row(details_box)

            delete_button = Gtk.Button.new_with_label(_("Delete")); delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.get_style_context().add_class("destructive-action")
            delete_button.connect("clicked", self._on_delete_cert_clicked, cert['path'])
            delete_row = Adw.ActionRow.new(); delete_row.add_prefix(delete_button); row.add_row(delete_row)
            self.certs_group.add(row)

        add_button = Gtk.Button.new_with_label(_("Add Certificate..."))
        add_button.get_style_context().add_class("suggested-action")
        add_button.connect("clicked", self._on_add_cert_clicked)
        add_row = Adw.ActionRow.new(); add_row.set_halign(Gtk.Align.CENTER); add_row.add_prefix(add_button)
        self.certs_group.add(add_row)
    
    def _on_add_cert_clicked(self, button):
        """Asks the main application to initiate the add certificate flow."""
        self.app.request_add_new_certificate()

    def _on_cert_toggled(self, button, path):
        """Notifies the main application that the active certificate has changed."""
        if button.get_active():
            self.app.set_active_certificate(path)
    
    def _on_delete_cert_clicked(self, button, path):
        """Asks the main application to remove a certificate, after confirmation."""
        confirm_dialog = Gtk.MessageDialog(
            transient_for=self, 
            modal=True, 
            message_type=Gtk.MessageType.QUESTION, 
            buttons=Gtk.ButtonsType.YES_NO, 
            text=_("Confirm Deletion"),
            secondary_text=_("Are you sure you want to permanently delete this certificate and its saved password?")
        )
        def on_confirm(d, res):
            if res == Gtk.ResponseType.YES:
                self.app.remove_certificate(path)
            d.destroy()
        confirm_dialog.connect("response", on_confirm)
        confirm_dialog.present()

    def _on_reason_changed(self, entry_row, param):
        """Updates the signature reason in the configuration (in-memory)."""
        self.app.config.set_signature_reason(entry_row.get_text())

    def _on_location_changed(self, entry_row, param):
        """Updates the signature location in the configuration (in-memory)."""
        self.app.config.set_signature_location(entry_row.get_text())