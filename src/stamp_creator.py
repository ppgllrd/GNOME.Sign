# stamp_creator.py
import fitz  # PyMuPDF
import re
from io import BytesIO
from pyhanko.stamp import StaticStampStyle
import tempfile
import os
from html.parser import HTMLParser
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GLib


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
    return full_html


class PangoToHtmlConverter(HTMLParser):
    def __init__(self):
        super().__init__(); self.html_parts = []; self.style_stack = [{}]
        self.font_map = {'sans': 'sans-serif', 'serif': 'serif', 'mono': 'monospace'}
        self.size_map = {'small': '8pt', 'normal': '10pt', 'large': '12pt', 'x-large': '14pt', 'extra large': '14pt'}
    def get_current_styles(self) -> dict: return self.style_stack[-1]
    def handle_starttag(self, tag, attrs):
        new_styles = self.get_current_styles().copy(); attrs_dict = dict(attrs)
        tag_lower = tag.lower()
        if tag_lower == 'b': new_styles['font-weight'] = 'bold'
        elif tag_lower == 'i': new_styles['font-style'] = 'italic'
        elif tag_lower == 'u': new_styles['text-decoration'] = 'underline'
        elif tag_lower in ('span', 'font'):
            font_family = attrs_dict.get('font_family');
            if font_family: new_styles['font-family'] = self.font_map.get(font_family.lower(), font_family)
            color = attrs_dict.get('color');
            if color: new_styles['color'] = color
            size = attrs_dict.get('size');
            if size: new_styles['font-size'] = self.size_map.get(size.lower(), '10pt')
        self.style_stack.append(new_styles)
    def handle_endtag(self, tag):
        if len(self.style_stack) > 1: self.style_stack.pop()
    def handle_data(self, data):
        if not data.strip(): self.html_parts.append(data); return
        styles = self.get_current_styles(); escaped_data = data.replace('&', '&').replace('<', '<').replace('>', '>')
        if styles: style_str = "; ".join(f"{k}: {v}" for k, v in styles.items()); self.html_parts.append(f'<span style="{style_str}">{escaped_data}</span>')
        else: self.html_parts.append(escaped_data)
    def get_html(self) -> str: return "".join(self.html_parts).replace('\n', '<br/>')


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

    def get_pixbuf(self, width: int, height: int) -> GdkPixbuf.Pixbuf:
        """
        Renders the PDF of the stamp in memory to a GdkPixbuf for preview.
        """
        if not self.pdf_buffer or width <= 0 or height <= 0:
            return None
        
        self.pdf_buffer.seek(0)
        doc = fitz.open(stream=self.pdf_buffer.read(), filetype="pdf")
        page = doc.load_page(0)

        zoom = width / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(pix.samples),
            GdkPixbuf.Colorspace.RGB,
            False, 8, pix.width, pix.height, pix.stride
        )
        doc.close()
        return pixbuf
    
    def get_style_and_path(self) -> tuple[StaticStampStyle, str]:
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_f:
                temp_file_path = temp_f.name
                self.pdf_buffer.seek(0)
                temp_f.write(self.pdf_buffer.read())
            style = StaticStampStyle.from_pdf_file(temp_file_path, border_width=0)
            return style, temp_file_path
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                pass