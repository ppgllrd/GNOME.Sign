import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw

# CAMBIO CLAVE: Ya no heredamos de Adw.StatusPage, sino de Gtk.Box.
class WelcomeView(Gtk.Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_valign(Gtk.Align.CENTER)

        # CREAMOS UNA INSTANCIA de Adw.StatusPage en lugar de ser una.
        self.status_page = Adw.StatusPage.new()
        self.status_page.set_icon_name("org.pepeg.GnomeSign")
        self.status_page.add_css_class("compact")
        
        # Añadimos el status_page al Gtk.Box
        self.append(self.status_page)

        # Creamos los botones como antes
        self.open_button = Gtk.Button()
        self.open_button.get_style_context().add_class("suggested-action")
        self.open_button.connect("clicked", self._on_open_clicked)

        self.prefs_button = Gtk.Button()
        self.prefs_button.connect("clicked", self._on_prefs_clicked)

        # Los añadimos a un contenedor y lo ponemos como hijo del status_page
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        button_box.set_hexpand(False)

        # 2. Le decimos al Gtk.Box que se alinee al centro del espacio horizontal
        #    que le otorga su padre (el Adw.StatusPage).
        button_box.set_halign(Gtk.Align.CENTER)
        
        button_box.append(self.open_button)
        button_box.append(self.prefs_button)
        self.status_page.set_child(button_box)
        
    def update_ui(self, app):
        """Updates titles and buttons based on app state."""
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        
        # AHORA modificamos self.status_page, no self
        if certs_exist:
            self.status_page.set_title(app._("welcome_prompt_cert_ok"))
            self.open_button.set_label(app._("welcome_button"))
            self.prefs_button.set_label(app._("select_certificate"))
        else:
            self.status_page.set_title(app._("welcome_prompt_no_cert"))
            self.open_button.set_label(app._("add_certificate"))
            self.prefs_button.set_label(app._("about"))

    def _on_open_clicked(self, button):
        # La forma de obtener la app sigue funcionando
        app = self.get_ancestor(Adw.ApplicationWindow).get_application()
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        if certs_exist:
            app.activate_action("open")
        else:
            app.activate_action("preferences")

    def _on_prefs_clicked(self, button):
        app = self.get_ancestor(Adw.ApplicationWindow).get_application()
        certs_exist = bool(app.cert_manager.get_all_certificate_details())
        if certs_exist:
            app.activate_action("preferences")
        else:
            app.activate_action("about")