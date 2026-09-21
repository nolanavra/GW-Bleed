from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QTransform
# “Mercury is in retrograde; the machinery has no such excuse.”
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem
from .models import Rect, Line


class SheetPreview(QGraphicsView):
    """Card/sheet visualization. All scene geometry is millimetres."""

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor('#0D151D'))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumSize(360, 260)
        self.candidate = None
        self.card = None
        self.artwork = QPixmap()
        self.show_pdf = True
        self.mode = 'Sheet'
        self.layers = dict(cuts=True, slitters=True, bleed=True, bounds=True, finishing=True)
        self.auto_fit = True
        self.dark_mode = True
        self.registration_marks = ()
        self.barcode = None
        self.show_registration = True
        self.bleed_handling = 'keep'
        self.source_extent = None
        self.source_trim = None

    def set_barcode(self, geometry):
        self.barcode = geometry
        self.redraw(False)

    def set_registration(self, marks):
        self.registration_marks = tuple(marks)
        self.redraw(False)

    def set_show_registration(self, checked):
        self.show_registration = checked
        self.redraw(False)

    def set_dark_mode(self, dark):
        self.dark_mode = dark
        self.setBackgroundBrush(QColor('#0D151D' if dark else '#e8edf2'))
        self.redraw(False)

    def set_artwork(self, png_data):
        self.artwork = QPixmap()
        if png_data is not None and not self.artwork.loadFromData(png_data):
            raise ValueError('Unable to decode PDF preview image.')
        self.redraw(False)

    def set_card(self, width_um=None, height_um=None, bx=0, by=0):
        self.card = None if width_um is None else (width_um, height_um, bx, by)
        if self.mode == 'Card':
            self.redraw(True)

    def set_mode(self, mode):
        self.mode = mode
        self.redraw(True)

    def set_layer(self, layer, checked):
        self.layers[layer] = checked
        self.redraw(False)

    def set_show_pdf(self, checked):
        self.show_pdf = checked
        self.redraw(False)

    def show_candidate(self, candidate):
        self.candidate = candidate
        self.redraw(True)

    def redraw(self, fit):
        transform = self.transform()
        h, v = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        scene = self.scene()
        scene.clear()
        c = self.candidate
        if (self.mode == 'Sheet' and c is None) or (self.mode == 'Card' and self.card is None):
            return

        def pen(color, dashed=False):
            p = QPen(QColor(color))
            p.setCosmetic(True)
            if dashed:
                p.setStyle(Qt.PenStyle.DashLine)
            return p

        def rect(region, outline, fill=None, tag='base'):
            item = scene.addRect(region.x_um/1000, region.y_um/1000,
                                 region.width_um/1000, region.height_um/1000,
                                 outline, QBrush(QColor(fill)) if fill else QBrush(Qt.BrushStyle.NoBrush))
            item.setData(0, tag)

        if self.mode == 'Card':
            if c:
                p, b = c.placements[0], c.bleed_regions[0]
                width, height, bx, by = p.width_um, p.height_um, p.x_um-b.x_um, p.y_um-b.y_um
                rotation = c.rotation
            else:
                width, height, bx, by = self.card
                rotation = 0
            sw, sh = width+2*bx, height+2*by
            bleeds = (Rect(0, 0, sw, sh),)
            placements = (Rect(bx, by, width, height),)
            cuts = (Line(0, by, sw, by), Line(0, by+height, sw, by+height))
            slitters = (Line(bx, 0, bx, sh), Line(bx+width, 0, bx+width, sh))
            usable = None
        else:
            sw, sh = c.sheet_width_um, c.sheet_height_um
            bleeds, placements = c.bleed_regions, c.placements
            cuts, slitters, usable, rotation = c.cuts, c.slitters, c.usable, c.rotation
        rect(Rect(0, 0, sw, sh), pen('#344054'), '#ffffff')
        if usable and self.layers['bounds']:
            rect(Rect(0, 0, sw, sh), pen('#344054'), '#c9d0d9', 'bounds')
            rect(usable, pen('#8b97a8'), '#ffffff', 'bounds')
        for p in placements:
            rect(p, pen('#e1e5eb'), '#ffffff')
        if self.show_pdf and not self.artwork.isNull():
            from .artwork import bleed_clips
            artwork = self.artwork.transformed(QTransform().rotate(rotation), Qt.TransformationMode.SmoothTransformation)
            clips = bleed_clips(c,self.bleed_handling) if c and self.mode == 'Sheet' else bleeds
            if c and self.mode == 'Card' and self.bleed_handling in ('trim','crop'):
                clipped = bleed_clips(c,self.bleed_handling)[0]
                original = c.bleed_regions[0]
                clips = (Rect(clipped.x_um-original.x_um,clipped.y_um-original.y_um,clipped.width_um,clipped.height_um),)
            for placement,region,clip in zip(placements,bleeds,clips):
                item = scene.addPixmap(artwork)
                item.setData(0, 'artwork')
                item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                ew,eh = self.source_extent or (region.width_um,region.height_um)
                if self.source_extent and rotation == 90: ew,eh = eh,ew
                item.setTransform(QTransform.fromScale(ew/1000/artwork.width(),eh/1000/artwork.height()))
                if self.source_trim:
                    tx,ty,tw,th = self.source_trim
                    ox,oy = (ew-ty-th,tx) if rotation==90 else (tx,ty)
                    item.setPos((placement.x_um-ox)/1000,(placement.y_um-oy)/1000)
                else:
                    item.setPos((region.x_um+(region.width_um-ew)/2)/1000,(region.y_um+(region.height_um-eh)/2)/1000)
                clip_item = scene.addRect(clip.x_um/1000,clip.y_um/1000,clip.width_um/1000,clip.height_um/1000,QPen(Qt.PenStyle.NoPen))
                clip_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape,True)
                item.setParentItem(clip_item)
        if self.layers['bleed']:
            for b in bleeds:
                rect(b, pen('#287bc1', True), tag='bleed')
        for name, lines, color in (('slitters', slitters, '#8b3eb5'), ('cuts', cuts, '#cc3f4c')):
            if self.layers[name]:
                for line in lines:
                    item = scene.addLine(line.x1_um/1000, line.y1_um/1000,
                                         line.x2_um/1000, line.y2_um/1000, pen(color))
                    item.setData(0, name)
        if c and self.layers['finishing']:
            colors = {'crease': '#d47b00', 'cross_perf': '#278838',
                      'strike_perf': '#009eaf', 'rotary_perf': '#d13786'}
            for mark in c.finishing:
                x1, y1, x2, y2 = mark.x1_um, mark.y1_um, mark.x2_um, mark.y2_um
                if self.mode == 'Card':
                    b = c.bleed_regions[0]
                    x1, x2 = max(x1, b.x_um), min(x2, b.x_um+b.width_um)
                    y1, y2 = max(y1, b.y_um), min(y2, b.y_um+b.height_um)
                    if x1 > x2 or y1 > y2:
                        continue
                    x1, x2, y1, y2 = x1-b.x_um, x2-b.x_um, y1-b.y_um, y2-b.y_um
                p = pen(colors[mark.kind])
                p.setStyle(Qt.PenStyle.DashDotLine if mark.kind == 'crease' else Qt.PenStyle.DashLine)
                p.setWidthF(1.5)
                item = scene.addLine(x1/1000, y1/1000, x2/1000, y2/1000, p)
                item.setData(0, 'finishing')
                item.setData(1, mark.kind)
        if self.mode == 'Sheet' and self.show_registration:
            for mark in self.registration_marks:
                rect(mark.rect, QPen(Qt.PenStyle.NoPen), '#000000', 'registration')
        if self.mode == 'Sheet' and self.barcode:
            rect(self.barcode.bounds, QPen(Qt.PenStyle.NoPen), '#ffffff', 'barcode_background')
            for bar in self.barcode.bars:
                rect(bar, QPen(Qt.PenStyle.NoPen), '#000000', 'barcode')
        sw, sh = sw/1000, sh/1000
        if self.mode == 'Sheet':
            for x1, y1, x2, y2 in ((sw/2, -16, sw/2, -2),
                                   (sw/2, -2, sw/2-3, -6), (sw/2, -2, sw/2+3, -6)):
                scene.addLine(x1, y1, x2, y2, pen('#B3D485' if self.dark_mode else '#004B7F'))
        scene.setSceneRect(-12, -22, sw+24, sh+34)
        if fit:
            self.fit_sheet()
        else:
            self.setTransform(transform)
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)

    def fit_sheet(self):
        self.auto_fit = True
        if self.scene().items():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def rotate_view(self):
        self.rotate(90)
        self.fit_sheet()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit_sheet()

    def zoom(self, factor):
        if 0.1 <= self.transform().m11()*factor <= 80:
            self.auto_fit = False
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1/1.15)
        event.accept()
