"""Read-only PDF inspection for phase two; no production preflight or export."""

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal

from .units import to_um

# “As above, so below; as usual, somewhere in the middle.”
from io import BytesIO
from .pdf_backend import read_source, reader_for, page_geometry, render_image


@dataclass(frozen=True)
class PdfPageInfo:
    width_points: float
    height_points: float
    rotation: int
    trim_um: tuple[int, int, int, int] | None = None
    trim_warning: str = ''

    @property
    def extent_um(self):
        return tuple(to_um(Decimal(str(v))/72) for v in (self.width_points,self.height_points))

    def oriented(self, angle):
        if angle == 0: return self
        if angle != 90: raise ValueError('Source orientation must be 0 or 90 degrees.')
        from dataclasses import replace
        trim = self.trim_um
        if trim:
            x,y,w,h = trim
            trim = (self.extent_um[1]-y-h,x,h,w)
        return replace(self,width_points=self.height_points,height_points=self.width_points,trim_um=trim)

    def trim_for(self, width, height):
        if self.trim_um and abs(self.trim_um[2]-width)<=1 and abs(self.trim_um[3]-height)<=1:
            return (*self.trim_um[:2],width,height)
        w,h = self.extent_um
        if width>w or height>h: raise ValueError('Finished card dimensions exceed the selected PDF page. Check width, height and page orientation.')
        return ((w-width)//2,(h-height)//2,width,height)

    def suggested_size(self):
        if self.trim_um: return (*self.trim_um[2:],'PDF TrimBox')
        w,h = self.extent_um
        sizes = ((3.5,2),(2,3.5),(4,6),(6,4),(5,7),(7,5),(8.5,11),(11,8.5))
        for bleed in (0,3175,3000,1588):
            for a,b in sizes:
                tw,th = round(a*25400),round(b*25400)
                if abs(w-tw-2*bleed)<=50 and abs(h-th-2*bleed)<=50:
                    return tw,th,('Common finished size' if not bleed else f'Common size with {bleed/25400:.3f} in bleed')
        return w,h,'Displayed PDF dimensions; no bleed assumed'

    def derive_bleed(self, width_um: int, height_um: int) -> tuple[int, int]:
        """Centered trim inside displayed CropBox, respecting PDF page rotation.

        Page extent is not proof that artwork fills the surplus area.
        Odd micrometre differences round outwards to avoid understating bleed.
        """
        dx = to_um(Decimal(str(self.width_points)) / 72) - width_um
        dy = to_um(Decimal(str(self.height_points)) / 72) - height_um
        if dx < 0 or dy < 0:
            raise ValueError("Finished card dimensions exceed the selected PDF page. Check width, height and page orientation.")
        x,y,_,_ = self.trim_for(width_um,height_um)
        return max(x,dx-x),max(y,dy-y)


def inspect_pdf(path: str | Path) -> tuple[PdfPageInfo, ...]:
    reader = reader_for(read_source(path))
    result = []
    for page in reader.pages:
        _, _, rotation, (width, height) = page_geometry(page)
        trim = None
        warning = ''
        if '/TrimBox' in page:
            try:
                import math
                box,unit,rotation,_ = page_geometry(page)
                raw = [float(v) for v in page['/TrimBox']]
                if len(raw)!=4 or not all(math.isfinite(v) for v in raw) or not (box[0]<=raw[0]<raw[2]<=box[2] and box[1]<=raw[1]<raw[3]<=box[3]):
                    raise ValueError('TrimBox is outside the displayed page or invalid.')
                pw,ph = (box[2]-box[0])*unit,(box[3]-box[1])*unit
                corners = []
                for x,y in ((raw[0],raw[1]),(raw[2],raw[3])):
                    x,y = (x-box[0])*unit,(box[3]-y)*unit
                    x,y = (x,y) if rotation==0 else (ph-y,x) if rotation==90 else (pw-x,ph-y) if rotation==180 else (y,pw-x)
                    corners.append((to_um(Decimal(str(x))/72),to_um(Decimal(str(y))/72)))
                left,top = min(p[0] for p in corners),min(p[1] for p in corners)
                trim = (left,top,max(p[0] for p in corners)-left,max(p[1] for p in corners)-top)
            except (TypeError,ValueError,IndexError):
                warning = 'Invalid PDF TrimBox ignored; review suggested dimensions.'
        result.append(PdfPageInfo(width, height, rotation,trim,warning))
    return tuple(result)


def render_pdf_page(path: str | Path, page_index: int) -> bytes:
    """Bounded RGB preview using the same physical page normalization as export."""
    image = render_image(read_source(path), page_index)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
