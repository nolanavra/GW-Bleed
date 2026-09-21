"""Vector PDF export to a staging file; publication is owned by the UI controller."""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from .pdf_backend import read_source, normalized_page, reader_for, content_stream, copy_document_rendering_metadata
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, RectangleObject

from .layout_engine import calculate
from .models import Job
from .profiles import profile_from_data
from .units import to_um
from .registration import RegistrationSettings, build_registration
from .barcodes import build_barcode

MODES = {"artwork": "Artwork only", "lines": "Finishing lines only",
         "combined": "Artwork with finishing lines"}


def points(um):
    return um * 72 / 25400


def identity(path):
    path = Path(path)
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def _export_single(request, staging):
    source, destination = Path(request["source"]), Path(request["destination"])
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise ValueError("The output must not overwrite the source PDF.")
    if tuple(request["signature"]) != identity(source):
        raise ValueError("Source PDF changed. Reload and recalculate before exporting.")
    mode = request["mode"]
    if mode not in MODES:
        raise ValueError("Unknown PDF export type.")
    job = Job(**request["job"])
    profile = profile_from_data(request["profile"])
    registration = RegistrationSettings(**request.get("registration", {"enabled": False}))
    expected_candidate = json.loads(json.dumps(request["candidate"]))
    candidate = next((c for c in calculate(job, profile).candidates
                      if json.loads(json.dumps(asdict(c))) == expected_candidate), None)
    if candidate is None:
        raise ValueError("Selected layout no longer matches the job and machine profile.")
    marks = build_registration(candidate, profile, registration).marks
    if registration.enabled and registration.machine_mark_enabled and not any(mark.axis == 'machine' for mark in marks):
        raise ValueError('The enabled L-shaped registration mark cannot fit in the printable top-right region. Adjust paper-stock printing margins or select a layout with more clear space before exporting.')
    barcode = build_barcode(candidate, profile, registration.barcode, marks)
    data = read_source(source)
    digest = hashlib.sha256(data).digest()
    page, source_width, source_height = normalized_page(data, request['page'])
    source_angle = request.get('source_orientation',0)
    if type(source_angle) is not int or source_angle not in (0,90):
        raise ValueError('Invalid source orientation.')
    if source_angle:
        page.rotate(90)
        page.transfer_rotation_to_content()
        source_width,source_height = source_height,source_width
    expected = request.get("source_dimensions", (job.width_um + 2*job.bleed_um, job.height_um + 2*job.vertical_bleed_um))
    envelope = (job.width_um + 2*job.bleed_um, job.height_um + 2*job.vertical_bleed_um)
    if len(expected) != 2 or any(type(v) is not int for v in expected) or any(v < trim or v > limit+1 for v,trim,limit in zip(expected,(job.width_um,job.height_um),envelope)):
        raise ValueError("Source artwork exceeds calculated bleed bounds.")
    actual = tuple(to_um(Decimal(str(v))/72) for v in (source_width, source_height))
    if any(abs(a-b) > 1 for a, b in zip(actual, expected)):
        raise ValueError('PDF dimensions no longer match the calculated bleed regions.')
    trim = request.get('source_trim',((actual[0]-job.width_um)//2,(actual[1]-job.height_um)//2,job.width_um,job.height_um))
    if len(trim)!=4 or any(type(v) is not int for v in trim) or tuple(trim[2:])!=(job.width_um,job.height_um) or min(trim)<0 or trim[0]+trim[2]>actual[0]+1 or trim[1]+trim[3]>actual[1]+1:
        raise ValueError('Invalid source trim boundary.')
    from .artwork import bleed_clips, back_candidate
    c = back_candidate(candidate, request.get("mirror", False))
    margin = profile.press_margins
    if any(r.x_um < margin.left_um or r.y_um < margin.lead_um or
           r.x_um+r.width_um > c.sheet_width_um-margin.right_um or
           r.y_um+r.height_um > c.sheet_height_um-margin.trail_um for r in c.bleed_regions):
        raise ValueError('Artwork on this side exceeds the stock printing margins. Review back alignment and layout.')
    # Rebuild fixed reader marks for the displayed side; artwork itself is not mirrored.
    marks = build_registration(c, profile, registration).marks
    if registration.enabled and registration.machine_mark_enabled and not any(mark.axis == 'machine' for mark in marks):
        raise ValueError('The enabled machine registration mark cannot fit on this side of the sheet.')
    barcode = build_barcode(c, profile, registration.barcode, marks)
    writer = PdfWriter()
    copy_document_rendering_metadata(page.indirect_reference.pdf, writer)
    width, height = points(c.sheet_width_um), points(c.sheet_height_um)
    sheet = writer.add_blank_page(width, height)
    for key in ('/MediaBox', '/CropBox', '/TrimBox', '/BleedBox', '/ArtBox'):
        sheet[NameObject(key)] = RectangleObject((0, 0, width, height))
    commands = [f'q 0 0 {width:.10f} {height:.10f} re W n']
    if mode != 'lines':
        # One reusable vector Form XObject preserves resources and transparency group.
        form = content_stream(page.get_contents().get_data() if page.get_contents() is not None else b'')
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): RectangleObject((0, 0, source_width, source_height)),
                     NameObject('/Resources'): page.get('/Resources', DictionaryObject()).clone(writer)})
        if '/Group' in page:
            form[NameObject('/Group')] = page['/Group'].clone(writer)
        sheet[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Artwork'): writer._add_object(form)})})
        for placement,region,clip in zip(c.placements,c.bleed_regions,bleed_clips(c,job.bleed_handling)):
            rw, rh = (source_height, source_width) if c.rotation == 90 else (source_width, source_height)
            ox,oy = (source_height-points(trim[1]+trim[3]),points(trim[0])) if c.rotation == 90 else (points(trim[0]),points(trim[1]))
            x = points(placement.x_um)-ox
            y = height-points(placement.y_um)+oy-rh
            matrix = (0, -1, 1, 0, x, y+source_width) if c.rotation == 90 else (1, 0, 0, 1, x, y)
            clipping = f'{points(clip.x_um):.10f} {height-points(clip.y_um+clip.height_um):.10f} {points(clip.width_um):.10f} {points(clip.height_um):.10f} re W n ' if job.bleed_handling in ('trim','crop') else ''
            commands.append('q ' + clipping + ' '.join(f'{v:.10f}' for v in matrix) + ' cm /Artwork Do Q')
    if mode != 'artwork':
        seen = set()
        for line in (*c.cuts, *c.slitters, *c.finishing):
            coords = (line.x1_um, line.y1_um, line.x2_um, line.y2_um)
            kind = getattr(line, 'kind', '')
            if (coords, kind) in seen:
                continue
            seen.add((coords, kind))
            dash = '[6 2 1 2]' if kind == 'crease' else '[3 2]' if kind else '[]'
            commands.append(f'q 0 G 0.25 w {dash} 0 d {points(line.x1_um):.10f} {height-points(line.y1_um):.10f} m {points(line.x2_um):.10f} {height-points(line.y2_um):.10f} l S Q')
    rectangles = [(mark.rect, 0) for mark in marks]
    if barcode:
        rectangles += [(barcode.bounds, 1)] + [(bar, 0) for bar in barcode.bars]
    for rect, gray in rectangles:
        commands.append(f'q {gray} g {points(rect.x_um):.10f} {height-points(rect.y_um+rect.height_um):.10f} {points(rect.width_um):.10f} {points(rect.height_um):.10f} re f Q')
    commands.append('Q')
    sheet[NameObject('/Contents')] = writer._add_object(content_stream(('\n'.join(commands)+'\n').encode('ascii')))
    writer.add_metadata({'/Producer': 'GW Bleed development / pypdf', '/Creator': 'GW Bleed'})
    from io import BytesIO
    buffer = BytesIO()
    writer.write(buffer)
    result = buffer.getvalue()
    if staging is not None:
        Path(staging).write_bytes(result)
        verify_export(staging, c.sheet_width_um, c.sheet_height_um)
    if identity(source) != tuple(request["signature"]) or hashlib.sha256(read_source(source)).digest() != digest:
        raise ValueError("Source PDF changed during export. Output was not published.")
    return result


def verify_export(path, width_um, height_um, page_count=1):
    reader = reader_for(read_source(path))
    expected = (0, 0, points(width_um), points(height_um))
    if len(reader.pages) != page_count:
        raise ValueError('Export verification failed: incorrect page count.')
    for page in reader.pages:
        for box in (page.mediabox, page.cropbox, page.trimbox, page.bleedbox, page.artbox):
            if any(abs(float(a)-b) > .001 for a, b in zip(box, expected)):
                raise ValueError('Export verification failed: page boxes do not match selected stock.')
        if b're W n' not in page.get_contents().get_data():
            raise ValueError('Export verification failed: missing physical sheet clip.')


def export_to_stage(request, staging):
    back = request.get('back')
    if back is None:
        return _export_single(request, staging)
    if not isinstance(back, dict):
        raise ValueError('Invalid back artwork request.')
    second = dict(request, **{k: back[k] for k in ('source','signature','page','source_dimensions','mirror')})
    for key in ('source_trim','source_orientation'):
        second.pop(key,None)
        if key in back: second[key] = back[key]
    second.pop('back', None)
    sources = (request, second)
    digests = [hashlib.sha256(read_source(r['source'])).digest() for r in sources]
    writer = PdfWriter()
    readers = []
    for r in sources:
        reader = reader_for(_export_single(r, None))
        readers.append(reader)
        if not writer.pages:
            copy_document_rendering_metadata(reader, writer)
        writer.add_page(reader.pages[0])
    # Each side has its own cloned layer objects. Preserve their default visibility
    # in one document-level configuration instead of retaining only front layers.
    from pypdf.generic import ArrayObject
    groups, off = ArrayObject(), ArrayObject()
    for reader in readers:
        properties = reader.trailer['/Root'].get('/OCProperties')
        if properties:
            properties = properties.get_object()
            default = properties.get('/D', DictionaryObject()).get_object()
            if default.get('/AS') or default.get('/BaseState','/ON') not in ('/ON','/OFF'):
                raise ValueError('Duplex export cannot safely combine these optional-content configurations.')
            for group in properties.get('/OCGs',[]):
                cloned = group.clone(writer)
                groups.append(cloned)
                visible = default.get('/BaseState','/ON') != '/OFF'
                if group in default.get('/ON',[]): visible = True
                if group in default.get('/OFF',[]): visible = False
                if not visible: off.append(cloned)
    if groups:
        writer._root_object[NameObject('/OCProperties')] = DictionaryObject({NameObject('/OCGs'):groups,
            NameObject('/D'):DictionaryObject({NameObject('/BaseState'):NameObject('/ON'),NameObject('/OFF'):off,NameObject('/Order'):groups})})
    writer.add_metadata({'/Producer':'GW Bleed development / pypdf','/Creator':'GW Bleed'})
    writer.write(staging)
    c = request['candidate']
    verify_export(staging,c['sheet_width_um'],c['sheet_height_um'],2)
    for r,digest in zip(sources,digests):
        if identity(r['source']) != tuple(r['signature']) or hashlib.sha256(read_source(r['source'])).digest() != digest:
            raise ValueError('Front or back source changed during export. Output was not published.')
