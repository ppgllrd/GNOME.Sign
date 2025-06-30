# ui/preferences_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib, Secret
from datetime import datetime, timezone, timedelta
import os
from certificate_manager import KEYRING_SCHEMA

class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = self.get_application()
        self.set_transient_for(self.app.window)
        self.set_hide_on_close(True)
        self.set_search_enabled(False)
        self._build_ui()
        self.update_all_texts() 

    def _build_ui(self):
        self.page_general = Adw.PreferencesPage.new()
        self.add(self.page_general)
        lang_group = Adw.PreferencesGroup.new()
        self.page_general.add(lang_group)
        model = Gtk.StringList.new(["Español", "English"])
        
        self.lang_row = Adw.ComboRow.new()
        self.lang_row.set_model(model)
        
        self.lang_row.connect("notify::selected", self._on_language_changed)
        lang_group.add(self.lang_row)

        self.page_certs = Adw.PreferencesPage.new()
        self.add(self.page_certs)
        self.certs_group = None

    def update_all_texts(self):
        """SOLUCIÓN DEFINITIVA: Actualiza todos los textos de esta ventana."""
        self.set_title(self.app._("preferences"))
        self.page_general.set_title(self.app._("general"))
        self.page_general.set_icon_name("preferences-system-symbolic")
        self.lang_row.set_title(self.app._("language"))
        self.page_certs.set_title(self.app._("certificates"))
        self.page_certs.set_icon_name("dialog-password-symbolic")
        
        current_lang_code = self.app.i18n.get_language()
        with self.lang_row.freeze_notify():
            self.lang_row.set_selected(0 if current_lang_code == "es" else 1)
        self._rebuild_certs_list()
        
    def _rebuild_certs_list(self):
        if self.certs_group: self.page_certs.remove(self.certs_group)
        new_certs_group = Adw.PreferencesGroup.new()
        self.page_certs.add(new_certs_group)
        self.certs_group = new_certs_group

        cert_details_list = self.app.cert_manager.get_all_certificate_details()
        if not cert_details_list:
             label = Gtk.Label(label=self.app._("welcome_prompt_no_cert"), margin_top=12, margin_bottom=12); label.add_css_class("dim-label"); self.certs_group.add(label)
        else:
            radio_group = None
            for cert in cert_details_list:
                row = Adw.ActionRow(title=cert['subject_cn'])
                now = datetime.now(timezone.utc); expires = cert['expires']
                if expires < now: expiry_text = f"({self.app._('expired')})"; row.add_css_class("error")
                elif expires < (now + timedelta(days=30)): expiry_text = f"({self.app._('expires_soon')})"; row.add_css_class("warning")
                else: expiry_text = ""
                row.set_subtitle(f"{self.app._('expires')}: {expires.strftime('%Y-%m-%d')} {expiry_text}")
                check = Gtk.CheckButton(group=radio_group)
                if radio_group is None: radio_group = check
                check.set_active(cert['path'] == self.app.active_cert_path); check.connect("toggled", self._on_cert_toggled, cert['path'])
                row.add_prefix(check); row.set_activatable_widget(check)
                delete_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER); delete_button.get_style_context().add_class("destructive-action"); delete_button.connect("clicked", self._on_delete_cert_clicked, cert['path'])
                row.add_suffix(delete_button); self.certs_group.add(row)

        add_button = Gtk.Button(label=self.app._("add_certificate")); add_button.get_style_context().add_class("suggested-action"); add_button.connect("clicked", self._on_add_cert_clicked)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, margin_top=12, margin_bottom=6); button_box.append(add_button); self.certs_group.add(button_box)
        
    def _on_language_changed(self, combo_row, param):
        if not combo_row.get_property("has-focus"): return
        selected_idx = combo_row.get_selected(); lang_code = "es" if selected_idx == 0 else "en"
        if self.app.i18n.get_language() != lang_code:
            action = self.app.lookup_action("change_lang"); action.change_state(GLib.Variant('s', lang_code))

    def _on_cert_toggled(self, button, path):
        if button.get_active(): self.app.set_active_certificate(path)
    
    def _on_add_cert_clicked(self, button):
        dialog = Gtk.FileDialog.new(); dialog.set_title(self.app._("open_cert_dialog_title"))
        filters = Gio.ListStore.new(Gtk.FileFilter); filter_p12 = Gtk.FileFilter.new()
        filter_p12.set_name(self.app._("p12_files")); filter_p12.add_pattern("*.p12"); filter_p12.add_pattern("*.pfx")
        filters.append(filter_p12); dialog.set_filters(filters); dialog.open(self, None, self._on_add_cert_finish)

    def _on_add_cert_finish(self, dialog, result):
        try: 
            file = dialog.open_finish(result)
            if file: self._process_certificate_selection(file.get_path())
        except GLib.Error: pass
            
    def _on_delete_cert_clicked(self, button, path):
        confirm_dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=self.app._("confirm_delete_cert_title"), secondary_text=self.app._("confirm_delete_cert_message"))
        def on_confirm(d, res):
            if res == Gtk.ResponseType.YES:
                self.app.cert_manager.remove_credentials_from_keyring(path)
                self.app.config.remove_cert_path(path)
                self.app.cert_manager.remove_cert_path(path)
                self.app._ensure_active_certificate()
                self.app.update_ui()
            d.destroy()
        confirm_dialog.connect("response", on_confirm); confirm_dialog.present()

    def _process_certificate_selection(self, pkcs12_path):
        def on_password_response(password):
            if password is None: return
            common_name = self.app.cert_manager.test_certificate(pkcs12_path, password)
            if common_name:
                Secret.password_store_sync(KEYRING_SCHEMA, {"path": pkcs12_path}, Secret.COLLECTION_DEFAULT, f"Certificate password for {common_name}", password, None)
                self.app.config.add_cert_path(pkcs12_path); self.app.config.set_last_folder(os.path.dirname(pkcs12_path)); self.app.config.save(); self.app.cert_manager.add_cert_path(pkcs12_path)
                self.app.set_active_certificate(pkcs12_path)
            else: self.app.window.show_toast(self.app._("bad_password_or_file"))
        
        dialog = Gtk.Dialog(title=self.app._("password"), transient_for=self, modal=True); dialog.add_buttons(self.app._("cancel"), Gtk.ResponseType.CANCEL, self.app._("accept"), Gtk.ResponseType.OK)
        ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK); ok_button.get_style_context().add_class("suggested-action"); dialog.set_default_widget(ok_button)
        content_area = dialog.get_content_area(); content_area.set_spacing(10); content_area.set_margin_top(10); content_area.set_margin_bottom(10); content_area.set_margin_start(10); content_area.set_margin_end(10)
        content_area.append(Gtk.Label(label=f"<b>{os.path.basename(pkcs12_path)}</b>", use_markup=True))
        password_entry = Gtk.Entry(visibility=False, placeholder_text=self.app._("password")); content_area.append(password_entry)
        password_entry.connect("activate", lambda w: dialog.response(Gtk.ResponseType.OK))
        def on_response(d, res):
            on_password_response(password_entry.get_text() if res == Gtk.ResponseType.OK else None); d.destroy()
        dialog.connect("response", on_response); dialog.present()