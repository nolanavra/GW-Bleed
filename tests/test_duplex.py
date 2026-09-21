from dataclasses import asdict,replace
from pathlib import Path
import tempfile
import unittest
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
from gw_imposition.models import Job
from gw_imposition.profiles import load_profile
from gw_imposition.layout_engine import calculate
from gw_imposition.artwork import bleed_clips,back_candidate
from gw_imposition.pdf_export import export_to_stage,identity


class DuplexTests(unittest.TestCase):
    def test_trim_and_overlap_have_distinct_rendered_gutters(self):
        from pdf_fixtures import image
        from gw_imposition.pdf_export import points
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'edges.pdf'
            cv=Canvas(str(source),pagesize=(270,162))
            cv.setFillColorRGB(1,0,0);cv.rect(0,0,135,162,fill=1,stroke=0)
            cv.setFillColorRGB(0,0,1);cv.rect(135,0,135,162,fill=1,stroke=0);cv.save()
            profile=load_profile()
            colors=[]
            for mode in ('trim','overlap'):
                job=Job(88900,50800,3175,5000,bleed_handling=mode);c=calculate(job,profile).recommended
                out=root/(mode+'.pdf')
                request=dict(source=str(source),signature=identity(source),page=0,destination=str(out),mode='artwork',job=asdict(job),profile=asdict(profile),candidate=asdict(c))
                export_to_stage(request,out)
                p=c.placements[0]
                colors.append(image(out).getpixel((round(points(p.x_um+p.width_um+2200)*2),round(points(p.y_um+20000)*2))))
            self.assertEqual(colors,[(0,0,255),(255,0,0)])

    def test_overlap_and_midpoint_clips(self):
        profile=load_profile()
        job=Job(88900,50800,3175,5000,bleed_handling='trim')
        c=calculate(job,profile).recommended
        clips=bleed_clips(c,'trim')
        self.assertEqual(clips[0].x_um+clips[0].width_um,clips[1].x_um)
        self.assertEqual(clips[0].x_um+clips[0].width_um,(c.placements[0].x_um+88900+c.placements[1].x_um)//2)
        self.assertEqual(bleed_clips(c,'overlap'),c.bleed_regions)
        self.assertEqual(c.placements,calculate(replace(job,bleed_handling='overlap'),profile).recommended.placements)
        with self.assertRaisesRegex(ValueError,'Gutter'):
            calculate(replace(job,bleed_handling='keep'),profile)
        mirrored=back_candidate(c,True)
        self.assertEqual(mirrored.placements[0].x_um,c.sheet_width_um-c.placements[0].x_um-88900)
        self.assertEqual(back_candidate(mirrored,True),c)

    def test_two_pages_and_two_files_export_vectors_and_protect_both_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);front=root/'front.pdf';back=root/'back.pdf';out=root/'output.pdf'
            cv=Canvas(str(front),pagesize=(270,162));cv.drawString(30,70,'FRONT');cv.showPage();cv.drawString(30,70,'BACK');cv.save()
            cv=Canvas(str(back),pagesize=(270,162));cv.drawString(30,70,'SEPARATE');cv.save()
            job=Job(88900,50800,3175,5000,bleed_handling='trim');profile=load_profile();c=calculate(job,profile).recommended
            request=dict(source=str(front),signature=identity(front),page=0,destination=str(out),mode='artwork',job=asdict(job),profile=asdict(profile),candidate=asdict(c))
            for source,page,label in ((front,1,'BACK'),(back,0,'SEPARATE')):
                for mirror in (False,True):
                    request['back']=dict(source=str(source),signature=identity(source),page=page,source_dimensions=[95250,57150],mirror=mirror)
                    export_to_stage(request,out)
                    reader=PdfReader(out)
                    self.assertEqual(len(reader.pages),2)
                    self.assertEqual(reader.pages[0].extract_text().count('FRONT'),c.yield_per_sheet)
                    self.assertEqual(reader.pages[1].extract_text().count(label),c.yield_per_sheet)
                    self.assertEqual(len(reader.pages[1].images),0)
                    self.assertEqual(reader.pages[0].mediabox,reader.pages[1].mediabox)
                    self.assertGreater(reader.pages[1].get_contents().get_data().count(b're W n'),1)
            request['destination']=str(back)
            with self.assertRaisesRegex(ValueError,'overwrite'):
                export_to_stage(request,out)
            request['destination']=str(out)
            back.write_bytes(b'changed')
            with self.assertRaises(Exception):export_to_stage(request,out)

