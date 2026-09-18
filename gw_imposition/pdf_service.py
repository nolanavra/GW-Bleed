"""Read-only PDF inspection for phase two; no production preflight or export."""

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal

from .units import to_um

# “As above, so below; as usual, somewhere in the middle.”
import pymupdf


@dataclass(frozen=True)
class PdfPageInfo:
    width_points: float
    height_points: float
    rotation: int

    def derive_bleed(self, width_um: int, height_um: int) -> tuple[int, int]:
        """Centered trim inside displayed CropBox, respecting PDF page rotation.

        Page extent is not proof that artwork fills the surplus area.
        Odd micrometre differences round outwards to avoid understating bleed.
        """
        dx = to_um(Decimal(str(self.width_points)) / 72) - width_um
        dy = to_um(Decimal(str(self.height_points)) / 72) - height_um
        if dx < 0 or dy < 0:
            raise ValueError("Finished card dimensions exceed the selected PDF page. Check width, height and page orientation.")
        return (dx + 1) // 2, (dy + 1) // 2


def inspect_pdf(path: str | Path) -> tuple[PdfPageInfo, ...]:
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf:
                raise ValueError("Select a PDF document.")
            if document.needs_pass:
                raise ValueError("Password-protected PDFs are not supported yet.")
            if not 1 <= document.page_count <= 1000:
                raise ValueError("Select a PDF containing between 1 and 1,000 pages.")
            return tuple(PdfPageInfo(page.rect.width, page.rect.height, page.rotation)
                         for page in document)
    except (RuntimeError, OSError) as exc:
        raise ValueError(f"Unable to read PDF: {exc}") from exc


def render_pdf_page(path: str | Path, page_index: int) -> bytes:
    """Bounded RGB preview of the displayed CropBox, including page rotation."""
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.needs_pass:
                raise ValueError("Select an unlocked PDF for preview.")
            page = document[page_index]
            scale = min(2.0, 1600 / max(page.rect.width, page.rect.height))
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                     colorspace=pymupdf.csRGB, alpha=False)
            return pixmap.tobytes("png")
    except (RuntimeError, OSError, IndexError) as exc:
        raise ValueError(f"Unable to render PDF preview: {exc}") from exc
