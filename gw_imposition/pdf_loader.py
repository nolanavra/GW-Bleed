"""Async, process-isolated PDF loading with a bounded per-source render cache."""
import base64
from collections import OrderedDict
import json
from pathlib import Path
import sys
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from .pdf_service import PdfPageInfo
from .desktop_entry import worker_command


# “The circle was perfect. What entered it was not.”
def source_signature(path):
    stat = Path(path).stat()
    return (str(Path(path).resolve()), stat.st_mtime_ns, stat.st_size)


class PdfLoader(QObject):
    ready = Signal(int, object, int, bytes)
    failed = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.token = 0
        self.signature = None
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.pages = ()

    def request(self, path, index):
        self.token += 1
        token = self.token
        if self.process:
            self.process.kill()
            self.process = None
        try:
            signature = source_signature(path)
        except OSError as exc:
            message = str(exc)
            self.clear_cache()
            QTimer.singleShot(0, lambda: self.failed.emit(token, message))
            return token
        if signature != self.signature:
            self.clear_cache()
            self.signature = signature
        if index in self.cache:
            png = self.cache[index]
            self.cache.move_to_end(index)
            pages = self.pages
            QTimer.singleShot(0, lambda: self.ready.emit(token, pages, index, png))
            return token
        process = QProcess(self)
        self.process = process
        process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        process.finished.connect(lambda *_: self.finished(process, token, signature))
        process.errorOccurred.connect(lambda *_: self.process_error(process, token))
        process.gw_error = ''
        process.gw_stderr = bytearray()
        process.readyReadStandardError.connect(lambda: self.drain_stderr(process))
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.abort_worker(process, 'PDF preview exceeded the 30-second limit.'))
        timer.start(30000)
        process.readyReadStandardOutput.connect(lambda: self.check_output_limit(process))
        program, arguments = worker_command('pdf', Path(path).resolve(), index)
        # Deliver startup errors after the caller has stored this request's token.
        # FailedToStart can be emitted synchronously by QProcess.start().
        QTimer.singleShot(0, lambda: process.start(program, arguments) if token == self.token else process.deleteLater())
        return token

    def abort_worker(self, process, message):
        if process.state() != QProcess.ProcessState.NotRunning:
            process.gw_error = message
            process.kill()

    def check_output_limit(self, process):
        if process.bytesAvailable() > 24*1024*1024:
            self.abort_worker(process, 'PDF preview worker response exceeded its size limit.')

    def drain_stderr(self, process):
        data = bytes(process.readAllStandardError())
        if len(process.gw_stderr)+len(data) > 64*1024:
            self.abort_worker(process, 'PDF preview diagnostics exceeded their size limit.')
        else:
            process.gw_stderr.extend(data)

    def clear_cache(self):
        self.cache.clear()
        self.cache_bytes = 0
        self.pages = ()
        self.signature = None

    def process_error(self, process, token):
        if token == self.token and process.error() == QProcess.ProcessError.FailedToStart:
            self.process = None
            self.failed.emit(token, process.errorString())
            process.deleteLater()

    def finished(self, process, token, signature):
        raw = bytes(process.readAllStandardOutput())
        error = (bytes(getattr(process, "gw_stderr", b"")) + bytes(process.readAllStandardError())[:65536]).decode(errors="replace")
        process.deleteLater()
        if token != self.token:
            return
        self.process = None
        try:
            if source_signature(signature[0]) != signature:
                self.clear_cache()
                raise ValueError("PDF changed while loading. Reload the PDF.")
            if getattr(process, 'gw_error', ''):
                raise ValueError(process.gw_error)
            if process.exitCode() != 0:
                raise ValueError(error.strip() or "PDF preview process failed.")
            payload = json.loads(raw)
            if "error" in payload:
                raise ValueError(payload["error"])
            self.pages = tuple(PdfPageInfo(**p) for p in payload["pages"])
            index, png = payload["index"], base64.b64decode(payload["png"])
            self.cache[index] = png
            self.cache_bytes += len(png)
            while len(self.cache) > 8 or self.cache_bytes > 32 * 1024 * 1024:
                _, removed = self.cache.popitem(last=False)
                self.cache_bytes -= len(removed)
            self.ready.emit(token, self.pages, index, png)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.failed.emit(token, str(exc))

    def close(self):
        self.token += 1
        if self.process:
            self.process.kill()
            self.process.waitForFinished(1000)
            self.process = None
