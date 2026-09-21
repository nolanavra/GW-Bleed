import configparser
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gw_imposition.models import Job
from gw_imposition.finishing import FinishingOperation
from gw_imposition.profiles import load_profile
from gw_imposition.layout_engine import calculate
from gw_imposition.machine_guide import MachineSetup
from gw_imposition.trimposer_export import trimposer_ini,save_trimposer_ini


class TrimposerExportTests(unittest.TestCase):
    def setUp(self):
        self.profile=load_profile()
        self.profile=replace(self.profile,capabilities=replace(self.profile.capabilities,min_paper_thickness_um=127,max_paper_thickness_um=381))
        self.job=Job(88900,50800,3175,6350)
        self.setup=MachineSetup('.008',2,'Sample')

    def encode(self,job=None,candidate=None,**options):
        job=job or self.job
        candidate=candidate or calculate(job,self.profile).candidates[0]
        return trimposer_ini(job,self.profile,candidate,self.setup,job_number=123,speed_grade=4,crease_level=2,**options)

    def parse(self,data):
        p=configparser.ConfigParser(interpolation=None);p.read_string(data.decode('ascii'))
        return p['MANULE_JOB_PARA']

    def test_alternatives_and_mm_units(self):
        for c in calculate(self.job,self.profile).candidates:
            data=self.encode(candidate=c,registration_position=(6350,12700))
            p=self.parse(data)
            self.assertTrue(data.startswith(b'[MANULE_JOB_PARA]\r\n'))
            self.assertEqual(float(p['m_Paper_Width']),c.sheet_width_um/1000)
            self.assertEqual(float(p['m_Paper_Thickness']),.2032)
            self.assertEqual(float(p['m_Locator_Offset_Hor']),12.7)
            self.assertEqual(float(p['m_Locator_Offset_Ver']),6.35)
            self.assertEqual(int(p['m_CutNum']),len(c.cut_y_um))
            positions=sorted(c.sheet_width_um-x for x in c.slitter_x_um)
            self.assertEqual(float(p['m_p_SlitPos_Arry[0]']),positions[0]/1000)
            self.assertEqual(float(p['m_p_SlitPos_Arry[5]']),positions[-1]/1000)

    def test_strike_endpoint_blocks(self):
        job=replace(self.job,finishing=(FinishingOperation('strike_perf',20000,0,25400),FinishingOperation('crease',25400)))
        c=calculate(job,self.profile).candidates[0]
        p=self.parse(self.encode(job,c))
        self.assertEqual(p['m_Is_Perforator_Ver_Part_Enable'],'1')
        self.assertEqual(p['m_Is_Crease_Enable'],'1')
        self.assertIn('m_p_PerforatorVerPartPos_Arry[50]',p)
        self.assertEqual(int(p['m_p_PerforatorVerPartNum[0]']),c.rows)

    def test_reject_unknown_operations_stale_geometry_and_names(self):
        job=replace(self.job,finishing=(FinishingOperation('cross_perf',25400),))
        with self.assertRaisesRegex(ValueError,'not established'):
            self.encode(job)
        c=calculate(self.job,self.profile).candidates[0]
        with self.assertRaisesRegex(ValueError,'no longer valid'):
            self.encode(candidate=replace(c,cut_y_um=(1,)))
        self.setup=MachineSetup('.008',2,'bad\nname')
        with self.assertRaisesRegex(ValueError,'ASCII'):
            self.encode()

    def test_atomic_output_and_no_binary(self):
        data=self.encode()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'MachineParameterFile_123.ini'
            save_trimposer_ini(path,data)
            self.assertEqual(path.read_bytes(),data)
            with patch('gw_imposition.trimposer_export.os.replace',side_effect=OSError('locked')):
                with self.assertRaises(OSError):save_trimposer_ini(path,data+b'\r\n')
            self.assertEqual(path.read_bytes(),data)
            self.assertEqual(list(Path(folder).iterdir()),[path])
            with self.assertRaisesRegex(ValueError,'future feature'):
                save_trimposer_ini(Path(folder)/'Export.bin',data)

    def test_speed_fixed_and_depth_derived(self):
        c=calculate(self.job,self.profile).recommended
        s=replace(self.setup,thickness_inches='.015')
        p=self.parse(trimposer_ini(self.job,self.profile,c,s,job_number=9))
        self.assertEqual(p['m_ProcessSpeed_Grade'],'4')
        self.assertEqual(p['m_Crease_Level'],'5')
        with self.assertRaises(ValueError):
            trimposer_ini(self.job,self.profile,c,s,job_number=9,speed_grade=3)
        fallback=self.parse(trimposer_ini(self.job,replace(self.profile,capabilities=load_profile().capabilities),c,s,job_number=9))
        self.assertEqual(fallback['m_Crease_Level'],'2')
