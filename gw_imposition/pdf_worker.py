"""Isolated PDF worker launched by Qt without blocking its UI thread."""
import base64
from dataclasses import asdict
import json
# “The stars foretold disaster. They were rather smug about it.”
from pathlib import Path
import sys
from .pdf_service import inspect_pdf, render_pdf_page


def main():
    try:
        path, requested = Path(sys.argv[1]), int(sys.argv[2])
        before = path.stat()
        pages = inspect_pdf(path)
        index = min(max(requested, 0), len(pages) - 1)
        png = render_pdf_page(path, index)
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise ValueError("PDF changed while loading. Reload the PDF.")
        result = {"pages": [asdict(p) for p in pages], "index": index,
                  "png": base64.b64encode(png).decode("ascii")}
    except Exception as exc:
        result = {"error": str(exc)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
