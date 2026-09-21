"""Opt-in internal-alpha diagnostic using the real GUI and worker controllers."""
import json
from pathlib import Path
import tempfile
import time
import traceback


def run(source, report):
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication
    from .desktop_entry import worker_command
    from .gui import MainWindow
    from .pdf_service import inspect_pdf

    app = QApplication([])
    QStandardPaths.setTestModeEnabled(True)
    app.setApplicationName('GW Bleed workflow check')
    window = MainWindow()
    window.registration_panel.barcode_enabled.setChecked(False)  # This generic sample has no machine job payload.
    results = {'status': 'failed', 'checks': [], 'worker_command': worker_command('pdf', source, 0)}

    def wait(predicate, label, seconds=40):
        end = time.monotonic() + seconds
        while not predicate():
            app.processEvents()
            if time.monotonic() >= end:
                raise RuntimeError('Timed out: ' + label)
            time.sleep(.01)
        app.processEvents()

    try:
        window.show()
        window.load_pdf(source)
        wait(lambda: not window.pdf_busy, 'PDF preview')
        assert window.pdf_pages, window.messages.toPlainText()
        assert not window.preview.artwork.isNull(), 'Artwork missing'
        results['checks'].append('GUI PDF preview')
        if len(window.pdf_pages) > 1:
            window.page_choice.setCurrentIndex(1)
            wait(lambda: not window.pdf_busy, 'second page')
            assert window.pdf_pages and not window.preview.artwork.isNull()
            results['checks'].append('GUI page switching')
        window.width.setText('3.5')
        window.height.setText('2')
        window.calculate_button.click()
        wait(lambda: window.calculate_button.isEnabled(), 'layout calculation')
        assert window.result and window.result.candidates, window.messages.toPlainText()
        if len(window.result.candidates) > 1:
            window.table.selectRow(1)
        selected = window.result.candidates[window.table.currentRow()]
        assert window.preview.candidate == selected
        results['checks'].append('GUI calculation and selected alternative')
        with tempfile.TemporaryDirectory(prefix='GW workflow check ') as folder:
            for mode in ('artwork', 'lines', 'combined'):
                target = Path(folder) / (mode + '.pdf')
                assert window.start_pdf_export(target, mode)
                wait(lambda: window.exporter.process is None, 'export ' + mode, 130)
                assert target.is_file(), window.messages.toPlainText()
                pages = inspect_pdf(target)
                assert len(pages) == 1
                assert abs(pages[0].width_points - selected.sheet_width_um * 72 / 25400) < .001
                assert abs(pages[0].height_points - selected.sheet_height_um * 72 / 25400) < .001
                assert window.centralWidget().isEnabled()
                results['checks'].append('GUI export ' + mode)
            window.grab().save(str(Path(report).with_suffix('.png')))
            corrupt = Path(folder) / 'corrupt.pdf'
            corrupt.write_bytes(b'not a PDF')
            window.load_pdf(corrupt)
            wait(lambda: not window.pdf_busy, 'corrupt PDF')
            assert not window.pdf_pages and window.calculate_button.isEnabled()
            window.load_pdf(Path(folder) / 'missing.pdf')
            wait(lambda: not window.pdf_busy, 'missing PDF')
            assert not window.pdf_pages and window.calculate_button.isEnabled()
            results['checks'].append('GUI invalid-source recovery')
        results['status'] = 'passed'
    except Exception:
        results['error'] = traceback.format_exc()
        results['page_status'] = window.page_info.text()
        results['messages'] = window.messages.toPlainText()
        process = window.loader.process
        if process is not None:
            results['process'] = {'program': process.program(), 'arguments': process.arguments(),
                                  'cwd': process.workingDirectory(), 'error': process.errorString(),
                                  'state': str(process.state())}
    finally:
        window.close()
        app.processEvents()
        Path(report).write_text(json.dumps(results, indent=2), encoding='utf-8')
    return 0 if results['status'] == 'passed' else 1
