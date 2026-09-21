"""Independent ReportLab fixtures and PDFium raster inspection for tests."""
from io import BytesIO
from contextlib import closing
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas
import pypdfium2 as pdfium

class FixturePage:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.rect = (0, 0, width, height)
        self.rotation = 0
        self.buffer = BytesIO()
        self.canvas = Canvas(self.buffer, pagesize=(width, height))
    def set_rotation(self, rotation):
        self.rotation = rotation
    def draw_rect(self, rect, fill, color=None):
        x0,y0,x1,y1=rect
        self.canvas.setFillColorRGB(*fill)
        self.canvas.rect(x0,self.height-y1,x1-x0,y1-y0,stroke=0,fill=1)
    def insert_text(self, position, text):
        self.canvas.drawString(position[0], self.height-position[1],text)

class FixtureDocument:
    def __init__(self):
        self.pages=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def new_page(self, width=612, height=792):
        page=FixturePage(width,height);self.pages.append(page);return page
    def save(self,path, encryption=None, owner_pw='', user_pw=''):
        writer=PdfWriter()
        for fixture in self.pages:
            fixture.canvas.showPage();fixture.canvas.save()
            page=writer.add_page(PdfReader(fixture.buffer).pages[0])
            if fixture.rotation: page.rotate(fixture.rotation)
        if encryption: writer.encrypt(user_pw, owner_pw)
        writer.write(path)


def image(path, index=0, scale=2):
    with pdfium.PdfDocument(str(path)) as doc:
        with closing(doc[index]) as page:
            with closing(page.render(scale=scale)) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()


def text(path):
    with pdfium.PdfDocument(str(path)) as doc:
        with closing(doc[0]) as page:
            with closing(page.get_textpage()) as textpage:
                return textpage.get_text_range()


def overlay_operations(path):
    page=PdfReader(path).pages[0]
    return page.get_contents().operations
