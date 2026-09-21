from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfReader,PdfWriter
from pypdf.generic import RectangleObject,NameObject
from reportlab.pdfgen.canvas import Canvas
from gw_imposition.pdf_service import PdfPageInfo,inspect_pdf
from gw_imposition.models import Job
from gw_imposition.layout_engine import calculate
from gw_imposition.profiles import load_profile
from gw_imposition.pdf_export import export_to_stage,identity,points
from pdf_fixtures import image


class ArtworkImportTests(unittest.TestCase):
    def test_suggestions_and_manual_trim(self):
        page=PdfPageInfo(270,162,0)
        self.assertEqual(page.suggested_size()[:2],(88900,50800))
        other=PdfPageInfo(301,217,0)
        self.assertEqual(other.suggested_size()[:2],other.extent_um)
        page=PdfPageInfo(300,210,0,(4233,12700,88900,50800))
        self.assertEqual(page.suggested_size(),(88900,50800,'PDF TrimBox'))
        self.assertEqual(page.trim_for(88900,50800)[:2],(4233,12700))
        self.assertNotEqual(page.trim_for(80000,50000)[:2],(4233,12700))
        self.assertEqual(page.oriented(90).trim_um,(10583,4233,50800,88900))

    def test_crop_all_preserves_offset_trim_at_native_and_user_rotations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=root/'raw.pdf';source=root/'offset.pdf'
            cv=Canvas(str(raw),pagesize=(300,210))
            cv.setFillColorRGB(1,0,0);cv.rect(0,0,300,210,fill=1,stroke=0)
            cv.setFillColorRGB(0,1,0);cv.rect(12,30,252,144,fill=1,stroke=0);cv.save()
            for native in (0,90,180,270):
                writer=PdfWriter();p=writer.add_page(PdfReader(raw).pages[0]);p[NameObject('/TrimBox')]=RectangleObject((12,30,264,174));p.rotate(native);writer.write(source)
                original=inspect_pdf(source)[0]
                self.assertIsNotNone(original.trim_um)
                for orientation in (0,90):
                    info=original.oriented(orientation)
                    w,h,_=info.suggested_size();bx,by=info.derive_bleed(w,h)
                    job=Job(w,h,bx,5000,bleed_y_um=by,bleed_handling='crop');profile=load_profile();c=calculate(job,profile).recommended
                    self.assertIsNotNone(c)
                    self.assertEqual(c.placements,c.bleed_regions)
                    out=root/'cropped.pdf'
                    request=dict(source=str(source),signature=identity(source),page=0,destination=str(out),mode='artwork',job=asdict(job),profile=asdict(profile),candidate=asdict(c),source_dimensions=info.extent_um,source_trim=info.trim_for(w,h),source_orientation=orientation)
                    export_to_stage(request,out)
                    rendered=image(out);p=c.placements[0]
                    self.assertEqual(rendered.getpixel((round(points(p.x_um+p.width_um*.2)*2),round(points(p.y_um+p.height_um*.2)*2))),(0,255,0))
                    self.assertEqual(len(PdfReader(out).pages[0].images),0)

    def test_invalid_trimbox_is_not_a_size_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'invalid.pdf';writer=PdfWriter();p=writer.add_blank_page(270,162)
            p[NameObject('/TrimBox')]=RectangleObject((-20,0,500,144));writer.write(path)
            info=inspect_pdf(path)[0]
            self.assertIsNone(info.trim_um)
            self.assertIn('Invalid',info.trim_warning)
            self.assertEqual(info.suggested_size()[:2],(88900,50800))
