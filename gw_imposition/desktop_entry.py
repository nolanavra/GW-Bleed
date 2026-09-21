"""Explicit worker entry points for Python and standalone builds."""
import sys


def running_executable():
    """Use the actual Windows process image, independent of CPython's prefix.

    In our Nuitka standalone build sys.executable names an absent python.exe.
    GetModuleFileNameW also works after moving or renaming the application.
    """
    if sys.platform == 'win32':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        get_name = kernel.GetModuleFileNameW
        get_name.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        get_name.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_name(None, buffer, len(buffer))
        if not length or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value
    from pathlib import Path
    return str(Path(sys.argv[0]).resolve())


def worker_command(kind, *arguments):
    if kind not in ('pdf', 'export'): raise ValueError('Unknown worker type.')
    if getattr(sys, 'frozen', False) or '__compiled__' in globals():
        return running_executable(), ['--gw-worker',kind,*map(str,arguments)]
    return sys.executable, ['-m','gw_imposition.desktop_entry','--gw-worker',kind,*map(str,arguments)]


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--gw-check-workflow':
        from .workflow_check import run
        return run(sys.argv[2], sys.argv[3])
    if len(sys.argv)>1 and sys.argv[1]=='--gw-worker':
        if len(sys.argv)<3: return 2
        kind=sys.argv[2];sys.argv=[sys.argv[0],*sys.argv[3:]]
        if kind=='pdf':
            from .pdf_worker import main as run
        elif kind=='export':
            from .export_worker import main as run
        else: return 2
        run();return 0
    from .gui import main as run
    return run()

if __name__=='__main__':
    raise SystemExit(main())
