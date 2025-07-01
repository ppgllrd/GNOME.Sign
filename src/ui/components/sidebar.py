# ui/components/sidebar.py
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf, GLib, GObject
import fitz

THUMBNAIL_WIDTH = 120

class Sidebar(Gtk.ScrolledWindow):
    __gsignals__ = { 'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,)), 'signature-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)) }
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_vexpand(True)
        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); self.set_child(self.main_vbox)
        self.pages_listbox = Gtk.ListBox(); self.pages_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.pages_listbox.connect("row-selected", self._on_page_row_selected); self.main_vbox.append(self.pages_listbox)
        self.signatures_separator = Gtk.Separator(); self.main_vbox.append(self.signatures_separator)
        self.signatures_listbox = Gtk.ListBox(); self.signatures_listbox.set_selection_mode(Gtk.SelectionMode.NONE); self.main_vbox.append(self.signatures_listbox)
        self.block_signal = False

    def populate(self, doc, signatures):
        self.pages_listbox.remove_all(); self.signatures_listbox.remove_all()
        if not doc: self.signatures_separator.set_visible(False); return
        for page_num in range(len(doc)):
            row = Gtk.ListBoxRow(); page = doc.load_page(page_num); page_rect = page.rect
            if page_rect.width == 0: continue
            zoom = THUMBNAIL_WIDTH / page_rect.width; matrix = fitz.Matrix(zoom, zoom)
            thumbnail_height = page_rect.height * zoom
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
            picture = Gtk.Picture.new_for_pixbuf(pixbuf); picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_size_request(THUMBNAIL_WIDTH, thumbnail_height)
            label = Gtk.Label.new(str(page_num + 1))
            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); item_box.set_size_request(THUMBNAIL_WIDTH, -1)
            item_box.set_halign(Gtk.Align.CENTER); item_box.set_margin_top(5); item_box.set_margin_bottom(5)
            item_box.append(picture); item_box.append(label); row.set_child(item_box); self.pages_listbox.append(row)
        if signatures:
            self.signatures_separator.set_visible(True)
            for sig in signatures:
                row = Adw.ActionRow.new(); row.set_title(sig.signer_name); row.set_subtitle(sig.sign_time.strftime('%Y-%m-%d %H:%M:%S'))
                row.set_activatable(True); icon_name = "security-high-symbolic" if sig.valid else "security-low-symbolic"
                icon = Gtk.Image.new_from_icon_name(icon_name); row.add_prefix(icon)
                row.connect("activated", self._on_signature_row_activated, sig); self.signatures_listbox.append(row)
        else: self.signatures_separator.set_visible(False)
            
    def select_page(self, page_num):
        self.block_signal = True
        row = self.pages_listbox.get_row_at_index(page_num)
        if row:
            self.pages_listbox.select_row(row)
            # --- CORRECCIÓN SINCRONIZACIÓN: HACEMOS LA FILA VISIBLE ---
            row.grab_focus()
        self.block_signal = False

    def _on_page_row_selected(self, listbox, row):
        if row and not self.block_signal: self.emit("page-selected", row.get_index())
    def _on_signature_row_activated(self, row, sig_obj): self.emit("signature-selected", sig_obj)
    def focus_on_signatures(self):
        sig_list_alloc = self.signatures_listbox.get_allocation()
        adj = self.get_vadjustment()
        if adj: adj.set_value(sig_list_alloc.y)