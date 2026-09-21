"""Only commit a verified staging PDF after the worker completes, unless cancelled."""
import json
# “Never summon what you cannot invoice.”
import os
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QObject, QProcess, Signal, QTimer
from .desktop_entry import worker_command
from .storage_io import fingerprint
from .pdf_export import identity


class ExportController(QObject):
    finished = Signal(str, str)  # destination on success, otherwise error / cancellation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.staging = None
        self.cancelled = False

    def start(self, request):
        if self.process:
            raise ValueError("An export is already running.")
        self.request = json.loads(json.dumps(request))
        self.destination_fingerprint = fingerprint(request["destination"])
        self.worker_error = ""
        self.cancelled = False
        destination = Path(request["destination"])
        handle, self.staging = tempfile.mkstemp(prefix=".gw-export-", suffix=".pdf", dir=destination.parent)
        os.close(handle)
        process = QProcess(self)
        self.process = process
        process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        process.started.connect(lambda: (process.write(json.dumps(self.request).encode()), process.closeWriteChannel()))
        process.finished.connect(self.complete)
        process.errorOccurred.connect(self.error)
        process.gw_stderr_bytes = 0
        process.readyReadStandardError.connect(lambda: self.drain_stderr(process))
        process.readyReadStandardOutput.connect(self.check_output_limit)
        self.timeout = QTimer(process)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self.abort('PDF export exceeded the 120-second limit.'))
        self.timeout.start(120000)
        program, arguments = worker_command('export', self.staging)
        process.start(program, arguments)

    def abort(self, message):
        if self.process:
            self.worker_error = message
            self.process.kill()

    def check_output_limit(self):
        if self.process and self.process.bytesAvailable() > 1024*1024:
            self.abort('PDF export worker response exceeded its size limit.')

    def drain_stderr(self, process):
        process.gw_stderr_bytes += len(bytes(process.readAllStandardError()))
        if process.gw_stderr_bytes > 64*1024:
            self.abort('PDF export worker diagnostics exceeded their size limit.')

    def cleanup(self):
        if self.staging:
            Path(self.staging).unlink(missing_ok=True)
            self.staging = None

    def error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self.process:
            message = self.process.errorString()
            self.process.deleteLater()
            self.process = None
            self.cleanup()
            self.finished.emit("", message)

    def complete(self, *_):
        process = self.process
        if not process:
            return
        self.timeout.stop()
        self.process = None
        destination, message = "", ""
        try:
            if self.worker_error:
                raise ValueError(self.worker_error)
            if self.cancelled:
                raise ValueError("Export cancelled.")
            payload = json.loads(bytes(process.readAllStandardOutput()))
            if process.exitCode() != 0 or not payload.get("ok"):
                raise ValueError(payload.get("error", "PDF export process failed."))
            if identity(self.request["source"]) != tuple(self.request["signature"]):
                raise ValueError("Source PDF changed before output was saved.")
            source, target = Path(self.request["source"]), Path(self.request["destination"])
            if self.request.get('back'):
                back = self.request['back']
                if identity(back['source']) != tuple(back['signature']):
                    raise ValueError('Back PDF changed before output was saved.')
                back_path = Path(back['source'])
                if back_path.resolve() == target.resolve() or (target.exists() and back_path.samefile(target)):
                    raise ValueError('The output must not overwrite the back PDF.')
            if source.resolve() == target.resolve() or (target.exists() and source.samefile(target)):
                raise ValueError("The output must not overwrite the source PDF.")
            if fingerprint(target) != self.destination_fingerprint:
                raise ValueError('Destination changed during export. Choose Export again to confirm replacement.')
            os.replace(self.staging, self.request["destination"])
            self.staging = None
            destination = self.request["destination"]
        except (ValueError, OSError) as exc:
            message = str(exc)
        finally:
            self.cleanup()
            process.deleteLater()
        self.finished.emit(destination, message)

    def cancel(self):
        if self.process:
            self.cancelled = True
            self.process.kill()

    def close(self):
        if self.process:
            self.cancel()
            self.process.waitForFinished(2000)
            self.cleanup()
