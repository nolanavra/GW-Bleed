"""Private PDF library boundary. Coordinates leaving this module are physical points."""
from io import BytesIO
from contextlib import closing
import math
from pathlib import Path
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.errors import DependencyError
from pypdf.generic import RectangleObject, NameObject, NumberObject, DecodedStreamObject
import pypdfium2 as pdfium

MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_PAGES = 1000
MAX_PAGE_POINTS = 14400


def read_source(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError('PDF exceeds the 256 MiB supported limit.')
    return data


def reader_for(data):
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError('Password-protected PDFs are not supported yet.')
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError('Select a PDF containing between 1 and 1,000 pages.')
        return reader
    except DependencyError as exc:
        raise ValueError('Password-protected PDFs are not supported yet.') from exc
    except Exception as exc:
        raise ValueError(f'Unable to read PDF: {exc}') from exc


def page_geometry(page):
    media, crop = page.mediabox, page.cropbox
    box = (max(float(media.left), float(crop.left)), max(float(media.bottom), float(crop.bottom)),
           min(float(media.right), float(crop.right)), min(float(media.top), float(crop.top)))
    unit = float(page.get('/UserUnit', 1))
    raw_rotation = float(page.get('/Rotate', 0))
    if not math.isfinite(raw_rotation) or raw_rotation % 90:
        raise ValueError('Unsupported PDF page rotation.')
    rotation = int(raw_rotation) % 360
    w, h = (box[2]-box[0])*unit, (box[3]-box[1])*unit
    if rotation not in (0, 90, 180, 270) or not all(math.isfinite(v) for v in (*box, unit, w, h)) or unit <= 0 or not (0 < w <= MAX_PAGE_POINTS and 0 < h <= MAX_PAGE_POINTS):
        raise ValueError('Unsupported PDF page dimensions, rotation, or UserUnit.')
    return box, unit, rotation, (h, w) if rotation in (90, 270) else (w, h)


def normalized_page(data, index):
    reader = reader_for(data)
    if type(index) is not int or not 0 <= index < len(reader.pages):
        raise ValueError('Selected source page is unavailable.')
    page = reader.pages[index]
    original = page_geometry(page)
    form = reader.trailer['/Root'].get('/AcroForm')
    if form:
        form = form.get_object()
        if form.get('/XFA') or bool(form.get('/NeedAppearances', False)):
            raise ValueError('Dynamic or stale form appearances are unsupported. Flatten in the source application first.')
    annotations = page.get('/Annots', [])
    visible = []
    for ref in annotations:
        annotation = ref.get_object()
        if int(annotation.get('/F', 0)) & 35 or annotation.get('/Subtype') == '/Popup':
            continue
        appearance = annotation.get('/AP')
        if annotation.get('/Subtype') == '/Link' and not appearance:
            border = annotation.get('/Border', [0, 0, 0])
            style = annotation.get('/BS', {})
            style = style.get_object() if hasattr(style, 'get_object') else style
            if float(style.get('/W', border[2] if len(border) > 2 else 0)) == 0:
                continue
        if not appearance or not appearance.get_object().get('/N'):
            raise ValueError('An annotation or form has no supported appearance. Flatten it in the source application first.')
        visible.append(annotation)
    if visible:
        with pdfium.PdfDocument(data) as document:
            document.init_forms()
            with closing(document[index]) as native_page:
                status = native_page.flatten()
                if status != pdfium.raw.FLATTEN_SUCCESS:
                    raise ValueError('Unable to flatten PDF appearances without changing artwork.')
            buffer = BytesIO()
            document.save(buffer)
        reader = reader_for(buffer.getvalue())
        page = reader.pages[index]
    owner = PdfWriter()
    copy_document_rendering_metadata(reader, owner)
    page = owner.add_page(page)
    box, unit, rotation, size = page_geometry(page)
    page.cropbox = RectangleObject(box)
    if rotation:
        page.transfer_rotation_to_content()
    box = page.cropbox
    page.add_transformation(Transformation().translate(-float(box.left), -float(box.bottom)).scale(unit))
    w, h = original[3]
    for key in ('/MediaBox', '/CropBox', '/TrimBox', '/BleedBox', '/ArtBox'):
        page[NameObject(key)] = RectangleObject((0, 0, w, h))
    page[NameObject('/Rotate')] = NumberObject(0)
    page[NameObject('/UserUnit')] = NumberObject(1)
    for key in ('/Annots', '/AA'):
        page.pop(key, None)
    return page, w, h


def normalized_bytes(data, index):
    page, width, height = normalized_page(data, index)
    writer = PdfWriter()
    writer.add_page(page)
    copy_document_rendering_metadata(page.indirect_reference.pdf, writer)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue(), width, height


def render_image(data, index, max_pixels=1600, scale_limit=2):
    content, width, height = normalized_bytes(data, index)
    with pdfium.PdfDocument(content) as document:
        with closing(document[0]) as page:
            with closing(page.render(scale=min(scale_limit, max_pixels/max(width, height)))) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()


def content_stream(data):
    stream = DecodedStreamObject()
    stream.set_data(data)
    return stream


def copy_document_rendering_metadata(reader, writer):
    """Preserve color intent and optional-content defaults, never scripts/actions."""
    root = reader._root_object if isinstance(reader, PdfWriter) else reader.trailer['/Root']
    for key in ('/OutputIntents', '/OCProperties'):
        if key in root:
            writer._root_object[NameObject(key)] = root[key].clone(writer)
