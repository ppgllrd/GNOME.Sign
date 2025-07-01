import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf, GLib, GObject, Adw
import fitz

THUMBNAIL_WIDTH = 120

# --- INICIO CAMBIOS: REFACTOR COMPLETO DE LA CLASE ---
class Sidebar(Gtk.Paned):
    """
    A sidebar widget that displays page thumbnails and a list of existing signatures
    in two separate, resizable panes.
    """
    __gsignals__ = { 
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,)), 
        'signature-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)) 
    }
    
    def __init__(self, **kwargs):
        """Initializes the sidebar widget with a vertical Paned layout."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.set_wide_handle(True)

        # Create top pane for page thumbnails
        self.pages_scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic")
        self.set_start_child(self.pages_scrolled_window)
        self.pages_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.pages_listbox.connect("row-selected", self._on_page_row_selected)
        self.pages_scrolled_window.set_child(self.pages_listbox)

        # Create bottom pane for signatures
        self.signatures_scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy="never", vscrollbar_policy="automatic")
        self.set_end_child(self.signatures_scrolled_window)
        self.signatures_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.signatures_scrolled_window.set_child(self.signatures_listbox)
        
        self.block_signal = False

    def populate(self, doc, signatures):
        """Fills the sidebar panes with page thumbnails and signature information."""
        # Clear previous content
        self.pages_listbox.unselect_all()
        while (row := self.pages_listbox.get_row_at_index(0)):
            self.pages_listbox.remove(row)
        while (row := self.signatures_listbox.get_row_at_index(0)):
            self.signatures_listbox.remove(row)

        # Hide the entire pane if there's no document
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
            item_box.append(picture)
            item_box.append(label)
            row.set_child(item_box)
            self.pages_listbox.append(row)

        # Populate signatures and control pane visibility
        if signatures:
            self.signatures_scrolled_window.set_visible(True)
            for sig in signatures:
                row = Adw.ActionRow.new()
                row.set_title(sig.signer_name)
                row.set_subtitle(sig.sign_time.strftime('%Y-%m-%d %H:%M:%S') if sig.sign_time else "No timestamp")
                row.set_activatable(True)
                icon_name = "security-high-symbolic" if sig.valid else "security-low-symbolic"
                icon = Gtk.Image.new_from_icon_name(icon_name)
                row.add_prefix(icon)
                row.connect("activated", self._on_signature_row_activated, sig)
                self.signatures_listbox.append(row)
            # Set initial position of the divider
            self.set_position(self.get_height() - 200 if self.get_height() > 300 else self.get_height() // 2)
        else: 
            self.signatures_scrolled_window.set_visible(False)
            
    def select_page(self, page_num):
        """Programmatically selects a specific page in the thumbnail list and ensures it is visible."""
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

    def focus_on_signatures(self):
        """Scrolls the view to make the list of signatures visible and gives it focus."""
        if self.signatures_scrolled_window.is_visible():
            self.signatures_listbox.grab_focus()
            adj = self.signatures_scrolled_window.get_vadjustment()
            if adj: 
                adj.set_value(0) # Scroll to the top of the signature list
