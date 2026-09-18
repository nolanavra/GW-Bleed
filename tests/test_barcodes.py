import unittest
from dataclasses import asdict, replace
from gw_imposition.barcodes import BarcodeSettings, build_barcode, encode_bars, has_barcode_reader, overlaps
from gw_imposition.registration import RegistrationSettings, build_registration
from gw_imposition.profiles import BUNDLED_PROFILES, load_profile, profile_from_data
from gw_imposition import Job, calculate

class BarcodeTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.candidate = calculate(Job(88900, 50800, 3175, 6350), self.profile).recommended

    def test_capabilities_and_old_snapshots(self):
        for key, path in BUNDLED_PROFILES.items():
            p = load_profile(path)
            expected = key in ('pt_8336scc_multi', 'pt_9375scc_supercut')
            self.assertEqual(has_barcode_reader(p), expected)
            data = asdict(p)
            del data['capabilities']['barcode_reader']
            self.assertEqual(has_barcode_reader(profile_from_data(data)), expected)

    def test_geometry_and_rejection(self):
        settings = BarcodeSettings(True, '000123')
        marks = build_registration(self.candidate, self.profile, RegistrationSettings()).marks
        b = build_barcode(self.candidate, self.profile, settings, marks)
        self.assertEqual(b.bars[0].x_um-b.bounds.x_um, 2540)
        self.assertFalse(any(overlaps(b.bounds, r) for r in self.candidate.bleed_regions))
        self.assertFalse(any(overlaps(b.bounds, m.rect) for m in marks))
        self.assertEqual(build_barcode(self.candidate, self.profile, replace(settings, automatic=False, x_um=b.bounds.x_um, y_um=b.bounds.y_um), marks), b)
        for invalid in (replace(settings, value=''), replace(settings, height_um=100000), replace(settings, automatic=False)):
            with self.assertRaises(ValueError):
                build_barcode(self.candidate, self.profile, invalid, marks)
        with self.assertRaises(ValueError):
            build_barcode(self.candidate, load_profile(BUNDLED_PROFILES['pt_335scc_b_multi']), settings)

    def test_formats_and_settings_round_trip(self):
        for symbology in ('code128', 'code39'):
            s = BarcodeSettings(True, '000123', symbology)
            self.assertEqual(set(encode_bars(s)), {'0', '1'})
            registration = RegistrationSettings(barcode=s)
            self.assertEqual(RegistrationSettings(**asdict(registration)), registration)
        with self.assertRaises(ValueError):
            encode_bars(BarcodeSettings(True, 'lowercase', 'code39'))
        self.assertFalse(RegistrationSettings().barcode.enabled)
