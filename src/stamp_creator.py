# stamp_creator.py
import fitz
import re
from io import BytesIO
from pyhanko.stamp import StaticStampStyle
from html.parser import HTMLParser
from pyhanko.pdf_utils import layout
from pyhanko.pdf_utils.layout import AxisAlignment, Margins
from pyhanko.pdf_utils.content import ImportedPdfPage
from pyhanko.pdf_utils.reader import PdfFileReader
import uuid 
from binascii import hexlify 

def pango_to_html(pango_text: str) -> str:
    converter = PangoToHtmlConverter(); converter.feed(pango_text)
    html_content = converter.get_html()
    full_html = f"""
    <div style="width:100%; height:100%; display:table; text-align:center; line-height:1.2; box-sizing: border-box;">
        <div style="display:table-cell; vertical-align:middle;">
            {html_content}
        </div>
    </div>
    """
    print(f"Converted Pango to HTML: {html_content}")  # Debugging output
    return full_html


class PangoToHtmlConverter(HTMLParser):
    def __init__(self):
        super().__init__(); self.html_parts = []; self.style_stack = [{}]
        self.font_map = {'sans': 'sans-serif', 'serif': 'serif', 'mono': 'monospace'}
        self.size_map = {'small': '8pt', 'normal': '10pt', 'large': '13pt', 'x-large': '16pt'}
    def get_current_styles(self) -> dict: return self.style_stack[-1]
    
    def handle_starttag(self, tag, attrs):
        new_styles = self.get_current_styles().copy()
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        if tag_lower == 'b':
            new_styles['font-weight'] = 'bold'
        elif tag_lower == 'i':
            new_styles['font-style'] = 'italic'
        elif tag_lower == 'u':
            new_styles['text-decoration'] = 'underline'
        elif tag_lower in ('span', 'font'):
            for attr, value in attrs_dict.items():
                attr_lower = attr.lower()
                if attr_lower == 'font_family':
                    new_styles['font-family'] = self.font_map.get(value.lower(), value)
                elif attr_lower in ('color', 'foreground'):
                    new_styles['color'] = value
                elif attr_lower == 'size':
                    new_styles['font-size'] = self.size_map.get(value.lower(), '10pt')
                elif attr_lower == 'weight':
                    new_styles['font-weight'] = value
                elif attr_lower == 'style':
                    new_styles['font-style'] = value
                elif attr_lower == 'underline':
                    if value.lower() != 'none':
                        new_styles['text-decoration'] = 'underline'
        
        self.style_stack.append(new_styles)

    def handle_endtag(self, tag):
        if len(self.style_stack) > 1: self.style_stack.pop()
    def handle_data(self, data):
        if not data.strip(): self.html_parts.append(data); return
        styles = self.get_current_styles(); escaped_data = data.replace('&', '&').replace('<', '<').replace('>', '>')
        if styles: style_str = "; ".join(f"{k}: {v}" for k, v in styles.items()); self.html_parts.append(f'<span style="{style_str}">{escaped_data}</span>')
        else: self.html_parts.append(escaped_data)
    def get_html(self) -> str: return "".join(self.html_parts).replace('\n', '<br/>')

class InMemoryPdfPage(ImportedPdfPage):
    def __init__(self, pdf_bytes: bytes, page_ix=0):
        self.name = hexlify(uuid.uuid4().bytes).decode('ascii')
        super().__init__(self.name, page_ix=page_ix)
        self.pdf_bytes = pdf_bytes

    def render(self) -> bytes:
        """
        Override the render method to use the in-memory buffer.
        IMPORTANT: We do not modify self.box. The size is already defined
        by the container of the stamp (StaticContentStamp).
        """
        w = self._ensure_writer
        r = PdfFileReader(BytesIO(self.pdf_bytes))
        
        xobj_ref = w.import_page_as_xobject(r, page_ix=self.page_ix)
        
        resource_name = b'/Import' + self.name.encode('ascii')
        self.resources.xobject[resource_name.decode('ascii')] = xobj_ref

        return resource_name + b' Do'

class HtmlStamp:
    def __init__(self, html_content: str, width: float, height: float):
        self.pdf_buffer = self._render_html_to_pdf(html_content, width, height)

    def _render_html_to_pdf(self, html: str, width: float, height: float) -> BytesIO:
        temp_doc = fitz.open()
        page_rect = fitz.Rect(0, 0, width, height)
        page = temp_doc.new_page(width=width, height=height)
        page.insert_htmlbox(page_rect, html, rotate=0)
        pdf_bytes = temp_doc.tobytes()
        temp_doc.close()
        return BytesIO(pdf_bytes)

    def get_pixbuf(self, width: int, height: int):
        if not self.pdf_buffer or width <= 0 or height <= 0: return None
        self.pdf_buffer.seek(0)
        doc = fitz.open(stream=self.pdf_buffer.read(), filetype="pdf"); page = doc.load_page(0)
        zoom = width / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        from gi.repository import GdkPixbuf, GLib 
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pix.samples), GdkPixbuf.Colorspace.RGB, False, 8, pix.width, pix.height, pix.stride)
        doc.close(); return pixbuf

    def get_style(self) -> StaticStampStyle:
        """
        Gets a StaticStampStyle from pyHanko based on the PDF rendered
        directly from memory, ensuring it has no internal margins.
        """
        pdf_bytes = self.pdf_buffer.getvalue()
        stamp_style_background = InMemoryPdfPage(pdf_bytes)

        background_layout_rule = layout.SimpleBoxLayoutRule(
            x_align=AxisAlignment.ALIGN_MID,
            y_align=AxisAlignment.ALIGN_MID,
            margins=Margins.uniform(0)  
        )
        
        return StaticStampStyle(
            background=stamp_style_background, 
            border_width=0,
            background_layout=background_layout_rule 
        )