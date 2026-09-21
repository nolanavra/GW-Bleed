"""Run required tests with failure on skipped tests; suitable for release CI."""
import os
from pathlib import Path
import sys
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
if result.skipped:
    print('Required tests were skipped; release validation fails.', file=sys.stderr)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
