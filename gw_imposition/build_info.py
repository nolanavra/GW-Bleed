"""Build identity works in a checkout and a standalone distribution."""
import json
from pathlib import Path


def build_information():
    path = Path(__file__).parent / 'resources' / 'build-info.json'
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8'))
    return {'version': '0.5.0a2', 'channel': 'Internal alpha — unverified machine profiles',
            'source_snapshot': 'Development checkout (not a packaged build)', 'signed': False}


def about_text():
    info = build_information()
    return '\n'.join(['GW Bleed ' + info['version'], info['channel'],
                      'Source snapshot: ' + info['source_snapshot'],
                      'Unsigned internal build. Not qualified for production.',
                      'Manual mappings and machine calibration remain unverified.',
                      'Copyright Graphic Whizard inc. | Application code: Apache-2.0',
                      'Bundled libraries and manuals retain their own notices.'])
