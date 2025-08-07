# ui/components/welcome.py
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw

class WelcomeView(Gtk.Box):
    """The view displayed when no document is open, prompting the user for an action."""
    def __init__(self, **kwargs):
        """Initializes the welcome view widget."""
        super().__init__(**kwargs)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        
        # An Adw.StatusPage is used for the main presentation.
        self.status_page = Adw.StatusPage.new()
        self.status_page.set_icon_name("io.github.ppgllrd.GNOME-Sign")
        self.status_page.add_css_class("compact")
        
        self.append(self.status_page)

        # Action buttons are created for user interaction.
        self.open_button = Gtk.Button()
        self.open_button.get_style_context().add_class("suggested-action")
        self.open_button.connect("clicked", self._on_open_clicked)

        self.prefs_button = Gtk.Button()
        self.prefs_button.connect("clicked", self._on_prefs_clicked)
        
        # Buttons are placed in a vertically centered box.
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        button_box.set_hexpand(False)
        button_box.set_halign(Gtk.Align.CENTER)
        
        button_box.append(self.open_button)
        button_box.append(self.prefs_button)
        self.status_page.set_child(button_box)
        
    def update_ui(self, app):
        """Updates titles and button labels based on whether any certificates are configured."""
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        
        if certs_exist:
            self.status_page.set_title(app._("welcome_prompt_cert_ok"))
            self.open_button.set_label(app._("welcome_button"))
            self.prefs_button.set_label(app._("select_certificate"))
        else:
            self.status_page.set_title(app._("welcome_prompt_no_cert"))
            self.open_button.set_label(app._("add_certificate"))
            self.prefs_button.set_label(app._("about"))

    def _on_open_clicked(self, button):
        """Handles the main action button click, either opening a file or the preferences."""
        app = self.get_ancestor(Adw.ApplicationWindow).get_application()
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        if certs_exist:
            app.activate_action("open")
        else:
            app.activate_action("manage_certs")

    def _on_prefs_clicked(self, button):
        """Handles the secondary action button click, opening preferences or the about dialog."""
        app = self.get_ancestor(Adw.ApplicationWindow).get_application()
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        if certs_exist:
            app.activate_action("manage_certs") 
        else:
            app.activate_action("about")
