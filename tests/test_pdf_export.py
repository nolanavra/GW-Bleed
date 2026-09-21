"""PDF migration corpus: ReportLab fixtures, pypdf structure, PDFium raster, ZXing decoding."""
from dataclasses import asdict, replace
from pathlib import Path
from io import BytesIO
import tempfile
import unittest
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject, NameObject, NumberObject, DictionaryObject, FloatObject
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from pdf_fixtures import image, text, overlay_operations
from gw_imposition.pdf_export import export_to_stage, identity, points
from gw_imposition.pdf_backend import content_stream, normalized_page
from gw_imposition.pdf_service import inspect_pdf
from gw_imposition import Job, calculate, load_profile
from gw_imposition.units import to_um

class PdfExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source.pdf'
        buffer=BytesIO();canvas=Canvas(buffer,pagesize=(270,162));canvas.drawString(20,122,'FIRST PAGE');canvas.showPage()
        canvas.setPageSize((320,220))
        for x,y,color in ((25,29,(0,0,1)),(160,29,(1,1,0)),(25,110,(1,0,0)),(160,110,(0,1,0))):
            canvas.setFillColorRGB(*color);canvas.rect(x,y,135,81,stroke=0,fill=1)
        canvas.setFillColorRGB(0,0,0);canvas.drawString(45,150,'SECOND PAGE');canvas.showPage();canvas.save()
        writer=PdfWriter(clone_from=PdfReader(buffer));writer.pages[1].cropbox=RectangleObject((25,29,295,191));writer.pages[1].rotate(90);writer.write(self.source)
    def tearDown(self): self.temp.cleanup()
    def request(self, mode='artwork', stock='13x19', rotation=0, page=1):
        w,h=(to_um('2'),to_um('3.5')) if page==1 else (to_um('3.5'),to_um('2'))
        bx,by=inspect_pdf(self.source)[page].derive_bleed(w,h)
        job=Job(w,h,bx,max(to_um('.25'),2*max(bx,by)),bleed_y_um=by);profile=load_profile()
        c=next(c for c in calculate(job,profile).candidates if c.stock_id==stock and c.rotation==rotation)
        return dict(source=str(self.source),destination=str(self.root/'output.pdf'),signature=identity(self.source),mode=mode,page=page,job=asdict(job),profile=asdict(profile),candidate=asdict(c))
    def export(self,req):
        stage=self.root/'stage.pdf';export_to_stage(req,stage);return stage
    def test_modes_stocks_rotations_page_geometry_and_lines(self):
        for stock in ('12x18','13x19'):
            for rotation in (0,90):
                for mode in ('artwork','lines','combined'):
                    req=self.request(mode,stock,rotation);path=self.export(req);page=PdfReader(path).pages[0];c=req['candidate']
                    for box in (page.mediabox,page.cropbox,page.trimbox,page.bleedbox,page.artbox):
                        for a,b in zip(box,(0,0,points(c['sheet_width_um']),points(c['sheet_height_um']))): self.assertAlmostEqual(float(a),b,places=5)
                    self.assertEqual(text(path).count('SECOND PAGE'),0 if mode=='lines' else c['yield_per_sheet'])
                    self.assertNotIn('FIRST PAGE',text(path));self.assertEqual(len(page.images),0)
                    ops=overlay_operations(path);self.assertEqual(sum(op==b'S' for _,op in ops),0 if mode=='artwork' else len(c['cuts'])+len(c['slitters']))
                    for args,op in ops:
                        if op==b'w': self.assertEqual(float(args[0]),.25)
                        if op==b'G': self.assertEqual(list(args),[0])
    def test_render_matches_rotated_cropped_source_at_original_scale(self):
        for rotation in (0,90):
            req=self.request(rotation=rotation);path=self.export(req);r=req['candidate']['bleed_regions'][0];src=image(self.source,1);out=image(path)
            for fx,fy in ((.12,.12),(.88,.12),(.12,.88),(.88,.88)):
                ox,oy=(fx,fy) if rotation==0 else (1-fy,fx)
                self.assertEqual(out.getpixel((round(points(r['x_um']+ox*r['width_um'])*2),round(points(r['y_um']+oy*r['height_um'])*2))),src.getpixel((int(fx*src.width),int(fy*src.height))))
    def test_finishing_guides_match_engine_and_artwork_omits_them(self):
        from gw_imposition.finishing import FinishingOperation
        for kind in ('crease','cross_perf'):
            req=self.request(page=0);job=replace(Job(**req['job']),finishing=(FinishingOperation(kind,to_um('1')),FinishingOperation('strike_perf',to_um('1.5'),to_um('.25'),to_um('1.75')),FinishingOperation('rotary_perf',to_um('2.5'))));c=calculate(job,load_profile()).recommended
            req.update(job=asdict(job),candidate=asdict(c))
            for mode in ('artwork','lines','combined'):
                req['mode']=mode;ops=overlay_operations(self.export(req));expected=() if mode=='artwork' else (*c.cuts,*c.slitters,*c.finishing)
                moves=[args for args,op in ops if op==b'm'];ends=[args for args,op in ops if op==b'l'];self.assertEqual(len(moves),len(expected))
                for a,b,line in zip(moves,ends,expected):
                    actual=(*a,*b);target=(points(line.x1_um),points(c.sheet_height_um-line.y1_um),points(line.x2_um),points(c.sheet_height_um-line.y2_um))
                    for v,t in zip(actual,target): self.assertAlmostEqual(float(v),t,places=5)
    def test_registration_filled_rectangles_match_geometry_in_all_export_modes(self):
        from gw_imposition.registration import RegistrationSettings,build_registration
        for stock in ('12x18','13x19'):
            for rotation in (0,90):
                for mode in ('artwork','lines','combined'):
                    req=self.request(mode,stock,rotation,page=0);settings=RegistrationSettings();req['registration']=asdict(settings)
                    c=next(c for c in calculate(Job(**req['job']),load_profile()).candidates if asdict(c)==req['candidate']);marks=build_registration(c,load_profile(),settings).marks
                    rects=[args for args,op in overlay_operations(self.export(req)) if op==b're'][1:];self.assertEqual(len(rects),len(marks))
                    for args,mark in zip(rects,marks):
                        r=mark.rect
                        for a,b in zip(args,(points(r.x_um),points(c.sheet_height_um-r.y_um-r.height_um),points(r.width_um),points(r.height_um))): self.assertAlmostEqual(float(a),b,places=5)
    def test_l_mark_exports_both_arms_with_printing_margins(self):
        from gw_imposition.models import Margins
        from gw_imposition.registration import RegistrationSettings,build_registration
        req=self.request(page=0)
        profile=replace(load_profile(),press_margins=Margins(3175,3175,3175,3175),finisher_margins=Margins(60000,60000,60000,60000))
        c=calculate(Job(**req['job']),profile).recommended
        settings=RegistrationSettings(machine_mark_enabled=True)
        marks=build_registration(c,profile,settings).marks
        self.assertEqual(len([m for m in marks if m.axis.startswith('machine')]),2)
        req.update(profile=asdict(profile),candidate=asdict(c),registration=asdict(settings))
        for mode in ('artwork','lines','combined'):
            req['mode']=mode
            rects=[args for args,op in overlay_operations(self.export(req)) if op==b're'][1:]
            self.assertEqual(len(rects),len(marks))
            for args,mark in zip(rects,marks):
                r=mark.rect
                for actual,expected in zip(args,(points(r.x_um),points(c.sheet_height_um-r.y_um-r.height_um),points(r.width_um),points(r.height_um))):
                    self.assertAlmostEqual(float(actual),expected,places=5)
        blocked=replace(profile,press_margins=Margins(25000,25000,25000,25000))
        req.update(profile=asdict(blocked),candidate=asdict(calculate(Job(**req['job']),blocked).recommended))
        with self.assertRaisesRegex(ValueError,'L-shaped'):
            self.export(req)

    def test_stock_clip_prevents_edge_strokes_from_painting_outside_stock(self):
        path=self.export(self.request(mode='lines'));writer=PdfWriter(clone_from=path);p=writer.pages[0];w,h=float(p.mediabox.width),float(p.mediabox.height);stream=p.get_contents().get_data();end=stream.rfind(b'\nQ')
        self.assertGreater(end,0);p[NameObject('/Contents')]=writer._add_object(content_stream(stream[:end]+f'\n0 g -2 -2 {w+4} {h+4} re f\n'.encode()+stream[end:]));p.mediabox=RectangleObject((-2,-2,w+2,h+2));p.cropbox=p.mediabox;writer.write(path)
        im=image(path,scale=4);self.assertEqual(im.getpixel((im.width//2,im.height//2)),(0,0,0))
        for x in (0,3,im.width-4,im.width-1): self.assertTrue(all(im.getpixel((x,y))==(255,255,255) for y in range(im.height)))
        for y in (0,3,im.height-4,im.height-1): self.assertTrue(all(im.getpixel((x,y))==(255,255,255) for x in range(im.width)))
    def test_reject_source_overwrite_stale_source_and_tampered_geometry(self):
        req=self.request();req['destination']=str(self.source)
        with self.assertRaisesRegex(ValueError,'overwrite'): self.export(req)
        req=self.request();req['signature']=(req['signature'][0],0,0)
        with self.assertRaisesRegex(ValueError,'changed'): self.export(req)
        req=self.request();req['candidate']['placements'][0]['x_um']=-1
        with self.assertRaisesRegex(ValueError,'no longer matches'): self.export(req)
    def test_unwritable_and_changed_during_export(self):
        req=self.request()
        with self.assertRaises(OSError): export_to_stage(req,self.root/'absent'/'output.pdf')
        with patch('gw_imposition.pdf_export.identity',side_effect=[identity(self.source),('changed',0,0)]):
            with self.assertRaisesRegex(ValueError,'changed during'): self.export(req)
    def test_fonts_images_transparency_and_unequal_bleed(self):
        font=Path(__import__('reportlab').__file__).parent/'fonts'/'Vera.ttf';pdfmetrics.registerFont(TTFont('FixtureEmbedded',str(font)))
        c=Canvas(str(self.source),pagesize=(270,180));c.setFont('FixtureEmbedded',10);c.drawString(20,140,'EMBEDDED TEXT');c.saveState();c.setFillAlpha(.4);c.setFillColorRGB(1,0,0);c.rect(10,50,90,50,fill=1);c.restoreState()
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(Image.new('RGB',(12,12),(100,100,100))),110,50,20,20);c.showPage();c.save()
        req=self.request(page=0);path=self.export(req);page=PdfReader(path).pages[0];self.assertEqual(text(path).count('EMBEDDED TEXT'),req['candidate']['yield_per_sheet']);self.assertTrue(page.images)
        resources=page['/Resources']['/XObject']['/Artwork']['/Resources'];self.assertTrue(resources['/Font']);self.assertTrue(any(float(v.get_object().get('/ca',1))==.4 for v in resources['/ExtGState'].values()))
    def test_barcode_exports_decode_and_remain_vector(self):
        import zxingcpp
        from gw_imposition.registration import RegistrationSettings
        from gw_imposition.barcodes import BarcodeSettings
        for value in ('00000','12305','99999'):
            for mode in ('artwork','lines','combined'):
                req=self.request(mode=mode,stock='12x18',page=0);req['registration']=asdict(RegistrationSettings(barcode=BarcodeSettings(True,value)));path=self.export(req)
                self.assertEqual(len(PdfReader(path).pages[0].images),0);result=zxingcpp.read_barcode(image(path,scale=3),formats=zxingcpp.BarcodeFormat.Code39);self.assertIsNotNone(result);self.assertEqual(result.text,value)
    def test_all_source_rotations_and_userunit(self):
        base=self.source.read_bytes()
        for rotation in (0,90,180,270):
            writer=PdfWriter(clone_from=BytesIO(base));writer.pages[0].rotation=rotation;writer.pages[0][NameObject('/UserUnit')]=FloatObject(2);writer.write(self.source)
            info=inspect_pdf(self.source)[0];self.assertEqual((info.width_points,info.height_points),(324,540) if rotation in (90,270) else (540,324))
            normalized,w,h=normalized_page(self.source.read_bytes(),0);self.assertEqual((w,h),(info.width_points,info.height_points));self.assertEqual(normalized.rotation,0)
    def test_annotation_missing_appearance_is_explicit_error(self):
        from pypdf.annotations import Text
        writer=PdfWriter(clone_from=self.source);writer.add_annotation(0,Text(rect=(10,10,30,30),text='Must not vanish'));writer.write(self.source)
        with self.assertRaisesRegex(ValueError,'no supported appearance'): self.export(self.request(page=0))
    def test_form_appearance_is_flattened_as_vectors(self):
        c=Canvas(str(self.source),pagesize=(270,162));c.acroForm.textfield(name='job',value='FORM VALUE',x=20,y=80,width=180,height=30);c.showPage();c.save()
        path=self.export(self.request(page=0));self.assertIn('FORM VALUE',text(path));page=PdfReader(path).pages[0];self.assertFalse(page.get('/Annots'));self.assertEqual(len(page.images),0)
    def test_spot_cmyk_overprint_and_output_intents_are_retained(self):
        from reportlab.lib.colors import CMYKColorSep
        from pypdf.generic import ArrayObject, TextStringObject
        canvas=Canvas(str(self.source),pagesize=(270,162))
        canvas.setFillOverprint(True);canvas.setStrokeOverprint(True)
        canvas.setFillColor(CMYKColorSep(0,1,0,0,spotName='FixtureMagenta'))
        canvas.rect(30,30,120,80,fill=1,stroke=0);canvas.showPage();canvas.save()
        writer=PdfWriter(clone_from=self.source)
        intent=DictionaryObject({NameObject('/Type'):NameObject('/OutputIntent'),NameObject('/S'):NameObject('/GTS_PDFX'),NameObject('/OutputConditionIdentifier'):TextStringObject('Synthetic preservation test, not PDF/X certification')})
        writer._root_object[NameObject('/OutputIntents')]=ArrayObject([writer._add_object(intent)]);writer.write(self.source)
        path=self.export(self.request(page=0));reader=PdfReader(path)
        self.assertEqual(reader.trailer['/Root']['/OutputIntents'][0].get_object()['/OutputConditionIdentifier'],intent['/OutputConditionIdentifier'])
        resources=reader.pages[0]['/Resources']['/XObject']['/Artwork']['/Resources']
        self.assertTrue(any(value.get_object()[0]=='/Separation' for value in resources['/ColorSpace'].values()))
        self.assertTrue(any(state.get_object().get('/op') for state in resources['/ExtGState'].values()))

    def test_optional_content_default_visibility_survives_export(self):
        from pypdf.generic import ArrayObject, TextStringObject
        writer=PdfWriter(clone_from=self.source);page=writer.pages[0]
        group=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/OCG'),NameObject('/Name'):TextStringObject('Hidden artwork')}))
        writer._root_object[NameObject('/OCProperties')]=DictionaryObject({NameObject('/OCGs'):ArrayObject([group]),NameObject('/D'):DictionaryObject({NameObject('/OFF'):ArrayObject([group]),NameObject('/BaseState'):NameObject('/ON')})})
        page['/Resources'][NameObject('/Properties')]=DictionaryObject({NameObject('/Hidden'):group})
        page[NameObject('/Contents')]=writer._add_object(content_stream(b'/OC /Hidden BDC 1 0 0 rg 0 0 270 162 re f EMC'))
        writer.write(self.source);req=self.request(page=0);path=self.export(req);reader=PdfReader(path)
        off=reader.trailer['/Root']['/OCProperties']['/D']['/OFF'][0]
        prop=reader.pages[0]['/Resources']['/XObject']['/Artwork']['/Resources']['/Properties'].raw_get('/Hidden')
        self.assertEqual(off.idnum,prop.idnum)
        r=req['candidate']['bleed_regions'][0];im=image(path)
        self.assertEqual(im.getpixel((round(points(r['x_um']+r['width_um']/2)*2),round(points(r['y_um']+r['height_um']/2)*2))),(255,255,255))

    def test_all_rotations_export_matches_source(self):
        base=self.source.read_bytes()
        for angle in (0,90,180,270):
            writer=PdfWriter(clone_from=BytesIO(base));writer.pages[1].rotation=angle;writer.write(self.source)
            info=inspect_pdf(self.source)[1];w,h=(50800,88900) if angle in (90,270) else (88900,50800)
            bx,by=info.derive_bleed(w,h);job=Job(w,h,bx,6350,bleed_y_um=by)
            for rotation in (0,90):
                c=next(c for c in calculate(job,load_profile()).candidates if c.rotation==rotation)
                req=dict(source=str(self.source),destination=str(self.root/'out.pdf'),signature=identity(self.source),mode='artwork',page=1,job=asdict(job),profile=asdict(load_profile()),candidate=asdict(c))
                path=self.export(req);src=image(self.source,1);out=image(path);r=c.bleed_regions[0]
                for fx,fy in ((.12,.12),(.88,.12),(.12,.88),(.88,.88)):
                    ox,oy=(fx,fy) if rotation==0 else (1-fy,fx)
                    self.assertEqual(out.getpixel((round(points(r.x_um+ox*r.width_um)*2),round(points(r.y_um+oy*r.height_um)*2))),src.getpixel((int(fx*src.width),int(fy*src.height))),(angle,rotation))
