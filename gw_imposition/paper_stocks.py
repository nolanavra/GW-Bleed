"""User paper-stock definitions, independent of machine capability profiles."""
from dataclasses import dataclass, field
from .models import Stock, Margins
from .machine_guide import MachineSetup
from decimal import Decimal, ROUND_HALF_UP


def crease_depth_is_placeholder(thickness_inches, capabilities):
    return not thickness_inches or capabilities is None or capabilities.min_paper_thickness_um is None


def automatic_crease_depth(thickness_inches, capabilities):
    """Map physical caliper to 1–5, or use the owner's placeholder level 2."""
    if crease_depth_is_placeholder(thickness_inches, capabilities):
        return 2
    MachineSetup(thickness_inches)
    thickness = Decimal(thickness_inches)*25400
    low, high = capabilities.min_paper_thickness_um, capabilities.max_paper_thickness_um
    if not low <= thickness <= high:
        raise ValueError('Selected stock thickness is outside this machine’s thickness range.')
    return int((1+4*(thickness-low)/(high-low)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class PaperStock:
    name: str
    width_um: int
    height_um: int
    thickness_inches: str = ''
    printing_margins: Margins = field(default_factory=lambda: Margins(3175,3175,3175,3175))
    gsm: int | None = None

    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.strip() or len(self.name)>120:
            raise ValueError('Provide a paper profile name of at most 120 characters.')
        Stock(self.name,self.width_um,self.height_um)
        if max(self.width_um,self.height_um)>2000000:
            raise ValueError('Paper dimensions exceed the supported input range.')
        MachineSetup(self.thickness_inches)
        if self.gsm is not None and (type(self.gsm) is not int or not 1 <= self.gsm <= 2000):
            raise ValueError('Paper weight must be a whole gsm value from 1 to 2000.')
        if isinstance(self.printing_margins, dict):
            object.__setattr__(self, 'printing_margins', Margins(**self.printing_margins))
        if not isinstance(self.printing_margins, Margins):
            raise ValueError('Invalid printing margins.')
        m = self.printing_margins
        if m.left_um+m.right_um >= min(self.width_um,self.height_um) or m.lead_um+m.trail_um >= max(self.width_um,self.height_um):
            raise ValueError('Printing margins must leave a printable area on the sheet.')

    def stock(self):
        return Stock(self.name, min(self.width_um,self.height_um),max(self.width_um,self.height_um))


def standard_paper_stocks():
    """Common nominal weights; actual caliper must be measured, not inferred."""
    return [PaperStock(f'{label} — {gsm} gsm', width, height, gsm=gsm)
            for label,width,height in (('12 × 18 in',304800,457200),('13 × 19 in',330200,482600))
            for gsm in (200,250,300)]


def stock_fits_machine(paper, profile):
    c = profile.capabilities
    s = paper.stock()
    return c is None or (c.min_sheet_width_um <= s.width_um <= c.max_sheet_width_um and
                         c.min_sheet_height_um <= s.height_um <= c.max_sheet_height_um)
