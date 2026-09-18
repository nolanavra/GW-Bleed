"""Only commit a verified staging PDF after the worker completes, unless cancelled."""
import json
# “Never summon what you cannot invoice.”
import os
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QObject, QProcess, Signal
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
        self.request = request
        self.cancelled = False
        destination = Path(request["destination"])
        handle, self.staging = tempfile.mkstemp(prefix=".gw-export-", suffix=".pdf", dir=destination.parent)
        os.close(handle)
        process = QProcess(self)
        self.process = process
        process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        process.started.connect(lambda: (process.write(json.dumps(request).encode()), process.closeWriteChannel()))
        process.finished.connect(self.complete)
        process.errorOccurred.connect(self.error)
        process.start(sys.executable, ["-m", "gw_imposition.export_worker", self.staging])

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
        self.process = None
        destination, message = "", ""
        try:
            if self.cancelled:
                raise ValueError("Export cancelled.")
            payload = json.loads(bytes(process.readAllStandardOutput()))
            if process.exitCode() != 0 or not payload.get("ok"):
                raise ValueError(payload.get("error", "PDF export process failed."))
            if identity(self.request["source"]) != tuple(self.request["signature"]):
                raise ValueError("Source PDF changed before output was saved.")
            source, target = Path(self.request["source"]), Path(self.request["destination"])
            if source.resolve() == target.resolve() or (target.exists() and source.samefile(target)):
                raise ValueError("The output must not overwrite the source PDF.")
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
