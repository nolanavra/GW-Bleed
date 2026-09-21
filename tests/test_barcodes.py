import unittest
from dataclasses import asdict, replace
from gw_imposition.barcodes import BarcodeSettings, build_barcode, encode_bars, has_barcode_reader, overlaps
from gw_imposition.registration import RegistrationSettings, build_registration
from gw_imposition.profiles import BUNDLED_PROFILES, load_profile, profile_from_data
from gw_imposition import Job, calculate

class BarcodeTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.candidate = calculate(Job(88900, 50800, 3175, 6350), self.profile).candidates[1]

    def test_capabilities_and_old_snapshots(self):
        for key, path in BUNDLED_PROFILES.items():
            p = load_profile(path)
            expected = key in ('pt_8336scc_multi', 'pt_9375scc_supercut')
            self.assertEqual(has_barcode_reader(p), expected)
            data = asdict(p)
            del data['capabilities']['barcode_reader']
            self.assertEqual(has_barcode_reader(profile_from_data(data)), expected)

    def test_geometry_and_rejection(self):
        settings = BarcodeSettings(True, '12305')
        marks = build_registration(self.candidate, self.profile, RegistrationSettings()).marks
        b = build_barcode(self.candidate, self.profile, settings, marks)
        first,last=b.bars[0],b.bars[-1]
        self.assertEqual(last.x_um+last.width_um-first.x_um,45000)
        self.assertEqual(first.height_um,6500)
        self.assertEqual(self.candidate.sheet_width_um-last.x_um-last.width_um,52000)
        self.assertTrue(4000<=first.y_um<=20000)
        self.assertGreater(first.x_um-b.bounds.x_um,0)
        self.assertFalse(any(overlaps(b.bounds, r) for r in self.candidate.bleed_regions))
        self.assertFalse(any(overlaps(b.bounds, m.rect) for m in marks))
        self.assertEqual(build_barcode(self.candidate, self.profile, replace(settings, automatic=False, y_um=first.y_um), marks), b)
        for invalid in (replace(settings, value=''), replace(settings, height_um=100000), replace(settings, automatic=False)):
            with self.assertRaises(ValueError):
                build_barcode(self.candidate, self.profile, invalid, marks)
        with self.assertRaises(ValueError):
            build_barcode(self.candidate, load_profile(BUNDLED_PROFILES['pt_335scc_b_multi']), settings)

    def test_formats_and_settings_round_trip(self):
        for value in ('00000','12305','99999'):
            s = BarcodeSettings(True, value)
            self.assertEqual(set(encode_bars(s)), {'0', '1'})
            registration = RegistrationSettings(barcode=s)
            self.assertEqual(RegistrationSettings(**asdict(registration)), registration)
        with self.assertRaises(ValueError):
            encode_bars(BarcodeSettings(True, 'lowercase', 'code39'))
        for value in ('123','123456','*12305*','１２３０５','12A05'):
            with self.assertRaises(ValueError):encode_bars(BarcodeSettings(True,value))
        with self.assertRaises(ValueError):encode_bars(BarcodeSettings(True,'12305','code128'))
        self.assertFalse(RegistrationSettings().barcode.enabled)

    def test_leading_edge_limits_and_fixed_geometry(self):
        from gw_imposition.models import Margins
        profile=replace(self.profile,press_margins=Margins(0,0,0,0))
        for y in (4000,20000):
            b=build_barcode(self.candidate,profile,BarcodeSettings(True,'00000',automatic=False,y_um=y))
            self.assertEqual(b.bars[0].y_um,y)
        for y in (3999,20001):
            with self.assertRaises(ValueError):build_barcode(self.candidate,profile,BarcodeSettings(True,'00000',automatic=False,y_um=y))
