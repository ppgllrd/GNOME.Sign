import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf, GLib, GObject, Adw
import fitz

THUMBNAIL_WIDTH = 150

class Sidebar(Gtk.Box):
    """
    A sidebar widget that displays page thumbnails or a list of existing signatures,
    switchable via a button group at the bottom.
    """
    __gsignals__ = { 
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,)), 
        'signature-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)) 
    }
    
    def __init__(self, **kwargs):
        """Initializes the sidebar widget with a vertical Box layout."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        
        # --- Main View Stack ---
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.append(self.stack)

        # --- Pages View ---
        self.pages_scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic", vexpand=True)
        self.pages_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.pages_listbox.connect("row-selected", self._on_page_row_selected)
        self.pages_scrolled_window.set_child(self.pages_listbox)
        self.stack.add_named(self.pages_scrolled_window, "pages")

        # --- Signatures View ---
        self.signatures_scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic", vexpand=True)
        self.signatures_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.signatures_scrolled_window.set_child(self.signatures_listbox)
        self.stack.add_named(self.signatures_scrolled_window, "signatures")

        # --- Search View ---
        self.search_scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic", vexpand=True)
        self.search_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.search_listbox.connect("row-selected", self._on_search_result_selected)
        self.search_scrolled_window.set_child(self.search_listbox)
        self.stack.add_named(self.search_scrolled_window, "search")
        
        # --- View Switcher Buttons ---
        switcher_box = Gtk.Box()
        switcher_box.get_style_context().add_class("linked")
        switcher_box.set_halign(Gtk.Align.CENTER)
        self.append(switcher_box)

        self.pages_button = Gtk.ToggleButton(icon_name="view-paged-symbolic")
        self.pages_button.connect("toggled", self._on_view_switched, "pages")
        switcher_box.append(self.pages_button)

        self.signatures_button = Gtk.ToggleButton(icon_name="security-high-symbolic")
        self.signatures_button.set_group(self.pages_button)
        self.signatures_button.connect("toggled", self._on_view_switched, "signatures")
        switcher_box.append(self.signatures_button)

        self.search_button = Gtk.ToggleButton(icon_name="edit-find-symbolic")
        self.search_button.set_group(self.pages_button)
        self.search_button.connect("toggled", self._on_view_switched, "search")
        switcher_box.append(self.search_button)

        self.block_signal = False
        self.connect("realize", self._on_realize)
        
    def _on_realize(self, widget):
        """Called when the widget is first realized (i.e., added to a toplevel window)."""
        app = self.get_ancestor(Adw.ApplicationWindow).get_application()
        app.connect("search-results-changed", self._on_search_results_changed)
        self.pages_button.set_tooltip_text(_("Page Thumbnails"))
        self.signatures_button.set_tooltip_text(_("Show existing signatures in the document"))
        self.search_button.set_tooltip_text(_("Search Document"))
    
    def _on_view_switched(self, button, view_name):
        """Callback to switch the visible child of the Gtk.Stack."""
        if button.get_active():
            self.stack.set_visible_child_name(view_name)
    
    def populate(self, doc, signatures):
        """Fills the sidebar panes with page thumbnails and signature information."""
        # Clear previous content
        self.pages_listbox.unselect_all()
        while (row := self.pages_listbox.get_row_at_index(0)):
            self.pages_listbox.remove(row)
        while (row := self.signatures_listbox.get_row_at_index(0)):
            self.signatures_listbox.remove(row)

        if not doc: 
            self.set_visible(False)
            return
        
        self.set_visible(True)

        # Populate page thumbnails
        for page_num in range(len(doc)):
            row = Gtk.ListBoxRow()
            page = doc.load_page(page_num)
            page_rect = page.rect
            if page_rect.width == 0: continue
            zoom = THUMBNAIL_WIDTH / page_rect.width
            matrix = fitz.Matrix(zoom, zoom)
            thumbnail_height = page_rect.height * zoom
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            picture = Gtk.Picture.new_for_pixbuf(pixbuf)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_size_request(THUMBNAIL_WIDTH, thumbnail_height)
            label = Gtk.Label.new(str(page_num + 1))
            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            item_box.set_size_request(THUMBNAIL_WIDTH, -1)
            item_box.set_halign(Gtk.Align.CENTER)
            item_box.set_margin_top(5)
            item_box.set_margin_bottom(5)
            item_box.set_margin_start(5)
            item_box.set_margin_end(5)
            item_box.append(picture)
            item_box.append(label)
            row.set_child(item_box)
            self.pages_listbox.append(row)

        # Populate signatures and control switcher visibility
        if signatures:
            self.signatures_button.set_visible(True)
            for sig in signatures:
                row = Adw.ActionRow.new()
                row.sig_object = sig 
                row.set_title(sig.signer_name)
                row.set_subtitle(sig.sign_time.strftime('%Y-%m-%d %H:%M:%S') if sig.sign_time else "No timestamp")
                row.set_activatable(True)
                icon_name = "security-high-symbolic" if sig.valid else "security-low-symbolic"
                icon = Gtk.Image.new_from_icon_name(icon_name)
                row.add_prefix(icon)
                row.connect("activated", self._on_signature_row_activated, sig)
                self.signatures_listbox.append(row)
        else: 
            self.signatures_button.set_visible(False)

        # Always default to showing pages, and ensure the button is active
        self.pages_button.set_active(True)
        self.stack.set_visible_child_name("pages")
            
    def select_page(self, page_num):
        """Programmatically selects a specific page in the thumbnail list and ensures it is visible."""
        # Ensure the pages view is visible before selecting
        self.stack.set_visible_child_name("pages")
        self.pages_button.set_active(True)
        
        self.block_signal = True
        row = self.pages_listbox.get_row_at_index(page_num)
        if row:
            self.pages_listbox.select_row(row)
            def scroll_to_row():
                adj = self.pages_scrolled_window.get_vadjustment()
                if adj and row.get_allocated_height() > 0:
                    row_y = row.get_allocation().y
                    adj.set_value(row_y - adj.get_page_size() / 2 + row.get_allocated_height() / 2)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(scroll_to_row)
        self.block_signal = False

    def _on_page_row_selected(self, listbox, row):
        """Emits the 'page-selected' signal when a user clicks a page thumbnail."""
        if row and not self.block_signal: 
            self.emit("page-selected", row.get_index())

    def _on_signature_row_activated(self, row, sig_obj):
        """Emits the 'signature-selected' signal when a signature row is activated."""
        self.emit("signature-selected", sig_obj)

    def _on_search_results_changed(self, app, results):
        """Handles the 'search-results-changed' signal from the application."""
        self.populate_search_results(results)

    def _on_search_result_selected(self, listbox, row):
        """Emits the 'page-selected' signal when a user clicks a search result."""
        if row:
            self.emit("page-selected", row.page_num)

    def populate_search_results(self, results):
        """Fills the search results listbox with search results."""
        while (row := self.search_listbox.get_row_at_index(0)):
            self.search_listbox.remove(row)

        if results:
            self.search_button.set_visible(True)
            for page_num, rect in results:
                row = Adw.ActionRow.new()
                row.page_num = page_num
                row.set_title(f"Page {page_num + 1}")
                row.set_subtitle(f"({rect.x0:.2f}, {rect.y0:.2f})")
                row.set_activatable(True)
                self.search_listbox.append(row)
        else:
            self.search_button.set_visible(False)

    def focus_on_signatures(self):
        """Scrolls the view to make the list of signatures visible and gives it focus."""
        if self.signatures_button.is_visible():
            self.stack.set_visible_child_name("signatures")
            self.signatures_button.set_active(True)
            self.signatures_listbox.grab_focus()
            adj = self.signatures_scrolled_window.get_vadjustment()
            if adj: 
                adj.set_value(0) # Scroll to the top of the signature list

    def select_signature(self, sig_to_select):
        """Programmatically selects a signature in the list and ensures it's visible."""
        # 1. Asegurarse de que la vista de firmas está activa
        self.stack.set_visible_child_name("signatures")
        self.signatures_button.set_active(True)

        # --- INICIO CORRECCIÓN: Iteración correcta sobre Gtk.ListBox ---
        target_row = None
        # Obtenemos el primer hijo y vamos iterando hasta que no haya más.
        current_row = self.signatures_listbox.get_row_at_index(0)
        while current_row:
            if hasattr(current_row, 'sig_object') and current_row.sig_object is sig_to_select:
                target_row = current_row
                break
            # Avanzamos al siguiente "hermano" en la lista
            current_row = current_row.get_next_sibling()
        # --- FIN CORRECCIÓN ---
        
        # 3. Seleccionar la fila y hacer scroll hacia ella
        if target_row:
            target_row.grab_focus()

            def scroll_to_row():
                adj = self.signatures_scrolled_window.get_vadjustment()
                if adj and target_row.get_allocated_height() > 0:
                    row_y = target_row.get_allocation().y
                    adj.set_value(row_y - adj.get_page_size() / 2 + target_row.get_allocated_height() / 2)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(scroll_to_row)