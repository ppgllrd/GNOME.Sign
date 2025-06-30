# ui/components/sidebar.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gdk, GLib, GObject, GdkPixbuf
import fitz

THUMBNAIL_WIDTH = 180

# --- SOLUCIÓN DEFINITIVA: La clase hereda de Gtk.ScrolledWindow ---
class Sidebar(Gtk.ScrolledWindow):
    __gsignals__ = {
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # El ScrolledWindow se expande para ocupar el espacio vertical disponible
        self.set_vexpand(True) 
        self.set_size_request(THUMBNAIL_WIDTH + 24, -1)
        
        # El ListBox es el HIJO DIRECTO del ScrolledWindow
        self.pages_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.pages_listbox.add_css_class("boxed-list")
        
        # El ListBox NO se expande. Su altura será la suma de sus filas.
        # Esto es lo que permite que el ScrolledWindow funcione correctamente.
        self.pages_listbox.set_vexpand(False) 
        self.set_child(self.pages_listbox)
        
        self.pages_listbox.connect("row-selected", self._on_page_row_selected)
        
        self.block_signal = False
        self.doc = None

    def populate(self, doc):
        self.doc = None
        while child := self.pages_listbox.get_first_child():
            self.pages_listbox.remove(child)

        if not doc: return
        
        self.doc = doc
        for page_num in range(len(doc)):
            row = Gtk.ListBoxRow()
            row.page_num = page_num
            row.thumbnail_loaded = False
            
            # Placeholder con altura fija para evitar saltos en la UI
            page = doc.load_page(page_num)
            h = page.rect.height * (THUMBNAIL_WIDTH / page.rect.width)
            placeholder = Gtk.Box(width_request=THUMBNAIL_WIDTH, height_request=int(h), margin_top=5, margin_bottom=5)
            
            row.set_child(placeholder)
            row.connect("map", self._on_row_mapped)
            self.pages_listbox.append(row)

    def _on_row_mapped(self, row):
        if not self.doc or row.thumbnail_loaded: return
        row.thumbnail_loaded = True
        GLib.idle_add(self._render_thumbnail, row, row.page_num)

    def _render_thumbnail(self, row, page_num):
        if not row.get_parent(): return GLib.SOURCE_REMOVE

        page = self.doc.load_page(page_num)
        zoom = THUMBNAIL_WIDTH / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
        
        picture = Gtk.Picture.new_for_pixbuf(pixbuf)
        picture.set_margin_top(5); picture.set_margin_bottom(5)
        
        row.set_child(picture)
        return GLib.SOURCE_REMOVE

    def select_page(self, page_num):
        self.block_signal = True
        row = self.pages_listbox.get_row_at_index(page_num)
        if row: self.pages_listbox.select_row(row)
        self.block_signal = False

    def _on_page_row_selected(self, listbox, row):
        if row and not self.block_signal: self.emit("page-selected", row.get_index())