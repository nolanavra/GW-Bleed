"""Vector PDF export to a staging file; publication is owned by the UI controller."""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pymupdf

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


def export_to_stage(request, staging):
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
    barcode = build_barcode(candidate, profile, registration.barcode, marks)
    data = source.read_bytes()
    digest = hashlib.sha256(data).digest()
    with pymupdf.open(stream=data, filetype="pdf") as src, pymupdf.open() as out:
        if src.needs_pass:
            raise ValueError("Password-protected PDFs cannot be exported.")
        index = request["page"]
        if type(index) is not int or not 0 <= index < len(src):
            raise ValueError("Selected source page is unavailable.")
        page = src[index]
        expected = (job.width_um + 2*job.bleed_um,
                    job.height_um + 2*job.vertical_bleed_um)
        actual = (to_um(Decimal(str(page.rect.width))/72),
                  to_um(Decimal(str(page.rect.height))/72))
        if any(abs(a-b) > 1 for a, b in zip(actual, expected)):
            raise ValueError("PDF dimensions no longer match the calculated bleed regions.")
        c = candidate
        sheet = out.new_page(width=points(c.sheet_width_um), height=points(c.sheet_height_um))
        stock_box = pymupdf.Rect(0, 0, points(c.sheet_width_um), points(c.sheet_height_um))
        sheet.set_mediabox(stock_box)
        for set_box in (sheet.set_cropbox, sheet.set_trimbox, sheet.set_bleedbox, sheet.set_artbox):
            set_box(stock_box)
        if mode != "lines":
            # Flatten annotations/widgets into PDF content, never into a bitmap.
            src.bake()
            page = src[index]
            rotation = page.rotation
            page.set_rotation(0)
            source_width, source_height = page.rect.width, page.rect.height
            angle = (rotation + c.rotation) % 360
            width, height = ((source_height, source_width) if angle in (90, 270)
                             else (source_width, source_height))
            for region in c.bleed_regions:
                # Place at original physical scale, centered within <=1 um rounding padding.
                x = points(region.x_um) + (points(region.width_um)-width)/2
                y = points(region.y_um) + (points(region.height_um)-height)/2
                target = pymupdf.Rect(x, y, x+width, y+height)
                if page.get_contents():
                    sheet.show_pdf_page(target, src, index, rotate=-angle, keep_proportion=True)
        if mode != "artwork":
            seen = set()
            for line in (*c.cuts, *c.slitters):
                coordinates = (line.x1_um, line.y1_um, line.x2_um, line.y2_um)
                if coordinates not in seen:
                    seen.add(coordinates)
                    sheet.draw_line((points(line.x1_um), points(line.y1_um)),
                                    (points(line.x2_um), points(line.y2_um)),
                                    color=(0, 0, 0), width=.25)
            for mark in c.finishing:
                sheet.draw_line((points(mark.x1_um), points(mark.y1_um)),
                                (points(mark.x2_um), points(mark.y2_um)), color=(0, 0, 0),
                                width=.25, dashes="[6 2 1 2] 0" if mark.kind == "crease" else "[3 2] 0")
        for mark in marks:
            r = mark.rect
            sheet.draw_rect(pymupdf.Rect(points(r.x_um), points(r.y_um),
                points(r.x_um+r.width_um), points(r.y_um+r.height_um)), color=None, fill=(0, 0, 0), width=0)
        if barcode:
            for r, fill in ((barcode.bounds, (1, 1, 1)), *((bar, (0, 0, 0)) for bar in barcode.bars)):
                sheet.draw_rect(pymupdf.Rect(points(r.x_um), points(r.y_um),
                    points(r.x_um+r.width_um), points(r.y_um+r.height_um)), color=None, fill=fill, width=0)
        # Clip the entire page content at the physical stock boundary, including strokes.
        # The source remains vector PDF content inside this page-space clipping path.
        sheet.clean_contents()
        contents = sheet.get_contents()
        if contents:
            clip = f"q\n0 0 {stock_box.width:.8f} {stock_box.height:.8f} re W n\n".encode("ascii")
            out.update_stream(contents[0], clip + out.xref_stream(contents[0]) + b"\nQ\n")
        out.save(staging, garbage=3, deflate=True)
    with pymupdf.open(staging) as check:
        if len(check) != 1 or abs(check[0].rect.width-points(c.sheet_width_um)) > .001 or abs(check[0].rect.height-points(c.sheet_height_um)) > .001:
            raise ValueError("Export verification failed: incorrect page dimensions.")
        for box in (check[0].mediabox, check[0].cropbox, check[0].trimbox, check[0].bleedbox, check[0].artbox):
            if any(abs(actual-expected) > .001 for actual, expected in zip(box, stock_box)):
                raise ValueError("Export verification failed: page boxes do not match selected stock.")
    if identity(source) != tuple(request["signature"]) or hashlib.sha256(source.read_bytes()).digest() != digest:
        raise ValueError("Source PDF changed during export. Output was not published.")
