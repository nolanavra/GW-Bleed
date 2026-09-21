"""Read-only machine screen reference with session-only operator acknowledgements."""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QFont, QIcon, QPixmap
from decimal import Decimal
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QFormLayout, QListWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QStackedWidget, QToolButton,
    QStyledItemDelegate, QStyle)
from .machine_guide import MachineSetup, machine_inches
from .machine_icons import machine_icon
from .machine_manuals import contextual_tooltip, machine_context


class MachineHeader(QHeaderView):
    def __init__(self, parent):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsClickable(True)
        self.setMinimumHeight(78)

    def paintSection(self, painter, rect, section):
        if not rect.isValid():
            return
        painter.save()
        painter.fillRect(rect, QColor('#bdd9ee'))
        painter.setPen(QColor('#6087a7'))
        painter.drawRect(rect.adjusted(0,0,-1,-1))
        icon = self.model().headerData(section, self.orientation(), Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon):
            icon.paint(painter, int(rect.center().x()-24), rect.top()+3, 48, 48)
        painter.setFont(QFont('Segoe UI',10))
        painter.setPen(QColor('#101722'))
        label = str(self.model().headerData(section,self.orientation()) or '')
        painter.drawText(rect.adjusted(2,52,-2,-2), Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class MachineEntryDelegate(QStyledItemDelegate):
    """Inset numerical fields resemble the white touchscreen entry boxes."""
    entry_mode = False

    def paint(self, painter, option, index):
        if not self.entry_mode:
            return super().paint(painter, option, index)
        painter.save()
        box = option.rect.adjusted(14, 7, -14, -7)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor('#d7eafa'))
        painter.fillRect(box, QColor('#72b4ff' if selected else '#f8fbff'))
        painter.setPen(QPen(QColor('#2376c9' if selected else '#5a7898'), 2))
        painter.drawRect(box)
        painter.setFont(QFont('Segoe UI', 20))
        painter.setPen(QColor('#101722'))
        text = str(index.data() or '')
        metrics = painter.fontMetrics()
        text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1,box.width()-20))
        painter.drawText(box.adjusted(10,0,-10,0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()


class Diagram(QWidget):
    def __init__(self, candidate):
        super().__init__()
        self.candidate = candidate
        self.setMinimumSize(400, 300)
        self.setToolTip('Machine orientation: feed length horizontal; right paper edge at the top. Cuts blue, slitters red, creases green, perfs gold.')

    def paintEvent(self, event):
        p = QPainter(self)
        c = self.candidate
        scale = min((self.width()-80)/c.sheet_height_um, (self.height()-80)/c.sheet_width_um)
        left = (self.width()-c.sheet_height_um*scale)/2
        top = (self.height()-c.sheet_width_um*scale)/2
        def point(x, y):
            return QPointF(left+y*scale, top+(c.sheet_width_um-x)*scale)
        p.setBrush(QColor('#ddc797'))
        p.setPen(QColor('black'))
        p.drawRect(QRectF(left, top, c.sheet_height_um*scale, c.sheet_width_um*scale))
        p.drawText(int(left), int(top-12), f'Length {machine_inches(c.sheet_height_um)} in → | Width {machine_inches(c.sheet_width_um)} in')
        p.setBrush(Qt.BrushStyle.NoBrush)
        for color, lines in [('#165ac4', c.cuts), ('#d12626', c.slitters), ('#148331', [m for m in c.finishing if m.kind == 'crease']), ('#b07800', [m for m in c.finishing if m.kind != 'crease'])]:
            p.setPen(QPen(QColor(color), 2))
            for line in lines:
                p.drawLine(point(line.x1_um, line.y1_um), point(line.x2_um, line.y2_um))
        p.setPen(QColor('black'))
        p.drawText(40, self.height()-12, 'Leading edge: left | Cuts blue · Slits red · Crease green · Perf gold')


class GuidanceOverlay(QWidget):
    """Mouse-transparent annotations recomputed from widget geometry at each paint."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event):
        o = self.owner
        if not o.target or not o.target.isVisible() or not o.valid:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#a83bba'), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(o.target.rect())
        rect.moveTopLeft(QPointF(o.target.mapTo(o, rect.topLeft().toPoint())))
        p.drawEllipse(rect.adjusted(-4, -4, 4, 4))
        start = QPointF(o.instruction.mapTo(o, o.instruction.rect().topLeft()))
        end = rect.center()
        if o.pages.currentIndex() == 0 and o.table.currentItem():
            cell = o.table.visualItemRect(o.table.currentItem())
            if o.table.viewport().rect().intersects(cell):
                cell = cell.intersected(o.table.viewport().rect())
                cell_rect = QRectF(cell)
                cell_rect.moveTopLeft(QPointF(o.table.viewport().mapTo(o, cell.topLeft())))
                p.drawRect(cell_rect.adjusted(1, 1, -1, -1))
                end = cell_rect.center()
        p.drawLine(start, end)
        delta = start-end
        length = max(1, (delta.x()**2+delta.y()**2)**.5)
        unit = delta/length
        normal = QPointF(-unit.y(), unit.x())
        p.setBrush(QColor('#a83bba'))
        p.drawPolygon(QPolygonF([end, end+unit*16+normal*6, end+unit*16-normal*6]))


class MachineGuideDialog(QDialog):
    settings_changed = Signal(object)

    def __init__(self, data, setup, parent=None, *, registration_position=None, show_setup_inputs=True):
        super().__init__(parent)
        self.data, self.valid, self.target = data, True, None
        self.registration_position = registration_position
        self.automatic_setup = not show_setup_inputs
        self.setFont(QFont('Segoe UI', 10))
        self.completed = set()
        self.setWindowTitle('GW Bleed — Machine setup guide (unverified)')
        self.resize(1380, 960)
        root = QVBoxLayout(self)
        c = data.candidate
        title = QLabel(f'{data.machine_name} | {c.stock_id} | {c.columns} × {c.rows} | {c.yield_per_sheet} pieces | Rotation {c.rotation}°')
        title.setWordWrap(True)
        root.addWidget(title)
        self.status = QLabel('Operator reference only. Confirmations do not verify or control the machine.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.manual_context = QLabel(machine_context(data.machine_id))
        self.manual_context.setWordWrap(True)
        self.manual_context.setMaximumHeight(85)
        self.manual_context.setToolTip(machine_context(data.machine_id))
        root.addWidget(self.manual_context)
        self.setup_inputs = QWidget()
        form = QFormLayout(self.setup_inputs)
        self.thickness = QLineEdit(setup.thickness_inches)
        self.thickness.setPlaceholderText('Required — inches')
        self.thickness.setToolTip('Measured stock thickness in inches; supplied by the operator, never derived from PDF artwork.')
        self.depth = QComboBox()
        self.depth.addItem('Select crease depth', None)
        for i in range(11):
            self.depth.addItem(str(i), i)
        self.depth.setCurrentIndex(0 if setup.crease_depth is None else setup.crease_depth+1)
        self.depth.setToolTip(contextual_tooltip(data.machine_id, 'GW Bleed uses its configured 1–5 stock-thickness mapping where physical limits are known, otherwise placeholder 2. This is an application convention, not a manual-certified crease calibration. Legacy 0–10 values remain readable.', 'crease'))
        self.job_name = QLineEdit(setup.job_name)
        self.job_name.setMaxLength(200)
        self.job_name.setToolTip('Optional label to use when saving the program on the real machine.')
        form.addRow('Stock thickness (in)', self.thickness)
        form.addRow('Crease depth (0–10)', self.depth)
        form.addRow('Job name', self.job_name)
        root.addWidget(self.setup_inputs)
        self.setup_inputs.setVisible(show_setup_inputs)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.steps = QListWidget()
        self.steps.setStyleSheet('QListWidget {background:#dde5ee; color:#182534; border:1px solid #8294a8;} QListWidget::item:selected {background:#287dbc; color:white;} QListWidget::item:focus {border:1px solid #7431a6;}')
        self.steps.addItems(data.steps)
        self.steps.setMaximumWidth(170)
        self.steps.setAccessibleName('Machine setup steps')
        body.addWidget(self.steps)
        self.screen = QWidget()
        self.screen.setObjectName('machineScreen')
        self.screen.setStyleSheet('''
            QWidget#machineScreen {background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #e6f3ff,stop:1 #a7c9ed); border: 4px solid #1266d6;}
            QWidget {color:#101722; background:transparent;}
            QLabel#machineTitle {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1268ee,stop:1 #00a6f4); color:white; font:26px 'Segoe UI'; padding:5px 12px;}
            QToolButton {border:0; padding:2px 8px; font:bold 15px 'Segoe UI'; background:transparent;}
            QToolButton:hover {background:#d2eaff;}
            QToolButton:focus {border:2px solid #923bb8;}
            QPushButton {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f7fbff,stop:1 #b8cde4); color:#101722; padding:7px; border:2px outset #7693b3; font:20px 'Segoe UI';}
            QPushButton:focus {border:2px solid #923bb8;}
            QTableWidget {alternate-background-color:#08c7e4; background:#e5f3ff; color:#111; gridline-color:#235878; font:23px 'Segoe UI'; border:1px solid #5284b0;}
            QTableWidget::item:selected {background:#6db0ff; color:black;}
            QHeaderView::section {background:#c2dff5; color:#0a182b; border:1px solid #4d80b1; padding:4px; font:15px 'Segoe UI';}
            QScrollBar:vertical {background:#c2dbed; width:20px;}
            QScrollBar::handle:vertical {background:#176ae4; min-height:35px;}
        ''')
        body.addWidget(self.screen, 1)
        screen_layout = QVBoxLayout(self.screen)
        screen_layout.setContentsMargins(6, 6, 6, 6)
        self.screen_title = QLabel('Set page data')
        self.screen_title.setObjectName('machineTitle')
        screen_layout.addWidget(self.screen_title)
        screen_body = QHBoxLayout()
        screen_layout.addLayout(screen_body, 1)
        self.left_rail, self.right_rail = QWidget(), QWidget()
        for rail in (self.left_rail, self.right_rail):
            rail.setFixedWidth(116)
            rail.setStyleSheet('background:#b8bec8; border:0;')
        left_buttons = QVBoxLayout(self.left_rail)
        right_buttons = QVBoxLayout(self.right_rail)
        for rail_layout in (left_buttons, right_buttons):
            rail_layout.setContentsMargins(4,4,4,4)
            rail_layout.setSpacing(2)
        screen_body.addWidget(self.left_rail)
        center = QVBoxLayout()
        screen_body.addLayout(center, 1)
        screen_body.addWidget(self.right_rail)
        self.category_bar = QWidget()
        nav = QHBoxLayout(self.category_bar)
        center.addWidget(self.category_bar)
        self.home = self.icon_button(left_buttons, 'Home', 'Home', self.show_main, 'Show the parameter overview in this guide.')
        self.return_button = self.icon_button(left_buttons, 'Return', 'Return', self.show_main, 'Return to the guide parameter overview.')
        self.categories = {}
        for label, icon in [('Sheet', 'Sheet'), ('Cuts', 'Slitters'), ('Slitters', 'Cuts'), ('Crease', 'Crease')]:
            self.categories[label] = self.icon_button(nav, label, icon, lambda checked=False, name=label: self.category(name), f'Open {label.lower()} entry reference. Values are read-only; enter them on the actual machine.')
        self.icon_button(nav, 'Fold', 'Fold', lambda: self.instruction.setText('The folded-sheet control appears in the supplied reference. Its programming behavior is unverified; no setting is changed here.'), 'Reference icon only. The folded-sheet control behavior is unverified.')
        nav.addStretch()
        self.pages = QStackedWidget()
        entry_layout = QHBoxLayout()
        center.addLayout(entry_layout, 1)
        entry_layout.addWidget(self.pages, 1)
        self.table = QTableWidget()
        self.table.setHorizontalHeader(MachineHeader(self.table))
        self.entry_delegate = MachineEntryDelegate(self.table)
        self.table.setItemDelegate(self.entry_delegate)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setIconSize(QSize(48,48))
        self.table.setAccessibleName('Read-only machine values')
        self.pages.addWidget(self.table)
        self.diagram = Diagram(c)
        self.pages.addWidget(self.diagram)
        self.keypad = QWidget()
        self.keypad.setFixedWidth(280)
        grid = QGridLayout(self.keypad)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.setSpacing(8)
        self.unit_display = QLabel('inch')
        self.unit_display.setStyleSheet('background:#b1c9e3; border:4px solid #1472e1; padding:12px; font:25px "Segoe UI";')
        grid.addWidget(self.unit_display, 0, 0, 1, 4)
        for i, label in enumerate(('1','2','3','−','4','5','6','+','7','8','9','Esc','.','0','C','Ent')):
            b = QPushButton(label)
            b.setMinimumSize(54, 56)
            b.setToolTip('Visual keypad reference only. Enter the highlighted value on the real machine.')
            grid.addWidget(b, 1+i//4, i%4)
            b.clicked.connect(lambda: self.instruction.setText('Use the real machine keypad. Calculated guide values cannot be edited here.'))
        entry_layout.addWidget(self.keypad)
        self.back_button = self.button(left_buttons, 'Back', self.show_main, 'Return from strike-perf table to main parameters in this reference.')
        self.strike_next = self.button(right_buttons, 'Next', self.show_strikes, 'Open the four-column strike-perf chart.')
        self.strike_next.setEnabled(True)
        self.save_machine = self.icon_button(left_buttons, 'Save As', 'Save As', lambda: self.reference_control('Save As'), 'Reference only; this does not save or send a machine program.')
        self.layout_buttons = {}
        for name in ('Low speed', 'Number of sheets', 'Unused', 'Barcode', 'Reg mark', 'Feeder table lower', 'Perf check', 'Test'):
            rail_layout = left_buttons if name in ('Low speed','Number of sheets','Unused') else right_buttons
            label = {'Number of sheets':'Sheets 0/0', 'Unused':'Unused 0/1', 'Feeder table lower':'Feeder\ntable lower'}.get(name,name)
            self.layout_buttons[name] = self.icon_button(rail_layout, label, name, lambda checked=False,n=name:self.reference_control(n), f'{name}: reference only; machine behavior is unverified.')
        left_buttons.addStretch()
        right_buttons.addStretch()
        self.run_button = self.icon_button(right_buttons, 'Run', 'Run', lambda: self.reference_control('Run'), 'Unverified control. This button does not run equipment.')
        self.instruction = QLabel()
        self.instruction.setWordWrap(True)
        self.instruction.setMinimumHeight(65)
        root.addWidget(self.instruction)
        self.warnings = QLabel('\n'.join((*data.conflicts, *data.warnings)))
        self.warnings.setWordWrap(True)
        root.addWidget(self.warnings)
        footer = QHBoxLayout()
        root.addLayout(footer)
        self.button(footer, '← Previous step', lambda: self.move_step(-1), 'Previous application walkthrough step; not a firmware page.')
        self.confirm = self.button(footer, 'Entered on machine', self.acknowledge, 'Record your acknowledgement only; GW Bleed cannot verify the machine.')
        self.button(footer, 'Next step →', lambda: self.move_step(1), 'Next application walkthrough step; not a firmware page.')
        self.overlay = GuidanceOverlay(self)
        self.table.currentCellChanged.connect(self.field_selected)
        self.table.verticalScrollBar().valueChanged.connect(self.overlay.update)
        self.table.horizontalScrollBar().valueChanged.connect(self.overlay.update)
        self.table.horizontalHeader().sectionClicked.connect(self.strike_entry)
        self.steps.currentRowChanged.connect(self.show_step)
        for widget, signal in [(self.thickness, 'textChanged'), (self.job_name, 'textChanged'), (self.depth, 'currentIndexChanged')]:
            getattr(widget, signal).connect(self.settings_edited)
        self.steps.setCurrentRow(0)
        self.settings_edited()
        self.show_main()
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

    def button(self, layout, text, callback, tooltip):
        b = QPushButton(text)
        b.setToolTip(tooltip)
        b.setAccessibleName(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def icon_button(self, layout, text, icon, callback, tooltip):
        button = QToolButton()
        button.setText(text)
        button.setIcon(machine_icon(icon))
        button.setIconSize(QSize(44, 44))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setToolTip(contextual_tooltip(self.data.machine_id, tooltip, icon.lower()))
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def reference_control(self, name):
        if name == 'Low speed':
            button = self.layout_buttons[name]
            label = 'High speed' if button.text() == 'Low speed' else 'Low speed'
            button.setText(label)
            button.setIcon(machine_icon(label))
            self.instruction.setText(f'{label} reference displayed. This changes only the illustration; machine speed is not set or verified.')
        else:
            self.instruction.setText(f'{name} is a reference control from the supplied machine screen. Its operation is unverified; nothing is sent to equipment.' + (' Sheet counters are placeholders, not live counts.' if name in ('Number of sheets','Unused') else ''))

    def screen_controls(self, layout_screen=False, strikes=False):
        self.current_screen = 'layout' if layout_screen else ('strikes' if strikes else 'parameters')
        self.category_bar.setVisible(not layout_screen and not strikes)
        for button in self.layout_buttons.values():
            button.setVisible(layout_screen)
        for button in (self.save_machine,self.back_button,self.strike_next):
            button.setVisible(not layout_screen)

    def settings_edited(self, *_):
        self.completed.clear()
        self.refresh_steps()
        try:
            setup = MachineSetup(self.thickness.text().strip(), self.depth.currentData(), self.job_name.text())
            self.settings_changed.emit(setup)
            ready = setup.complete
            if setup.thickness_inches and machine_inches(Decimal(setup.thickness_inches)*25400) == '0.000':
                raise ValueError('Stock thickness rounds to 0.000 in; resolve machine precision before continuing.')
            self.status.setText('Operator reference only — workflow unverified.')
        except ValueError as exc:
            ready = False
            self.status.setText(str(exc))
        self.confirm.setEnabled(self.valid and ready and not self.data.conflicts)
        if self.steps.currentRow() == 0:
            self.show_main() if getattr(self,'viewing_main',False) else self.show_step(0)

    def invalidate(self, reason='Layout or inputs changed. Close this guide and regenerate it from the current layout.'):
        self.valid = False
        self.completed.clear()
        self.refresh_steps()
        self.status.setText(reason)
        self.confirm.setEnabled(False)
        self.screen.setEnabled(False)
        self.steps.setEnabled(False)
        for w in (self.thickness, self.depth, self.job_name):
            w.setEnabled(False)
        self.overlay.update()

    def refresh_steps(self):
        for i, label in enumerate(self.data.steps):
            self.steps.item(i).setText(('✓ ' if i in self.completed else '')+label)

    def acknowledge(self):
        if self.valid and self.confirm.isEnabled():
            self.completed.add(self.steps.currentRow())
            self.refresh_steps()
            self.status.setText(f'{len(self.completed)}/{len(self.data.steps)} steps acknowledged by operator; machine not verified.')

    def move_step(self, delta):
        if self.valid:
            self.steps.setCurrentRow(max(0, min(len(self.data.steps)-1, self.steps.currentRow()+delta)))

    def fill(self, headers, columns, origins):
        self.pages.setCurrentIndex(0)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(max(map(len, columns), default=0))
        self.table.setVerticalHeaderLabels([str(i+1) for i in range(self.table.rowCount())])
        for col, values in enumerate(columns):
            for row, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(contextual_tooltip(self.data.machine_id, f'{headers[col]}, entry {row+1}: {value}. {origins[col]}', headers[col].lower()))
                self.table.setItem(row, col, item)
        self.table.setCurrentCell(0, 0)
        self.table.resizeRowsToContents()

    def sheet_values(self):
        c = self.data.candidate
        thickness = self.thickness.text().strip()
        try:
            setup = MachineSetup(thickness, self.depth.currentData(), self.job_name.text())
            thickness = machine_inches(Decimal(setup.thickness_inches)*25400) if thickness else 'Required'
        except ValueError:
            thickness = 'Invalid thickness'
        return [machine_inches(c.sheet_height_um), machine_inches(c.sheet_width_um), thickness,
                str(self.depth.currentData()) if self.depth.currentData() is not None else ('Unavailable' if self.automatic_setup else 'Select depth'),
                *([machine_inches(v) for v in self.registration_position] if self.registration_position is not None else ['Not generated', 'Not generated'])]

    def show_main(self):
        self.viewing_main = True
        self.screen_controls()
        d = self.data
        self.screen_title.setText('Program parameters')
        self.set_entry_style(False)
        self.keypad.hide()
        sheet = self.sheet_values()
        sheet_column = [*sheet[:3], '', '', '', '', *sheet[3:]]
        self.fill(['Page', 'Cuts', 'Slitters', 'Crease / cross perf'],
                  [sheet_column, list(map(machine_inches, d.cuts)),
                   [machine_inches(v) for v in d.slits]+['0.000 (unused)']*max(0, 6-len(d.slits)),
                   list(map(machine_inches, d.creases)) or ['0.000 (unused)']],
                  ['Length is along feed; width across feed; thickness in inches; automatic depth 1–5 maps the machine physical thickness range. Page field order beyond supplied references is unverified.', 'Inches from leading edge.', 'Inches from right paper edge; ordered positions, not fixed head slots.', 'Inches from leading edge.'])
        for row, label in ((0,'Length'), (1,'Width'), (2,'Thickness'), (7,'Crease depth'), (8,'Reg: leading'), (9,'Reg: right')):
            item = self.table.item(row, 0)
            item.setText(label+': '+item.text())
        self.table.setIconSize(QSize(48,48))
        for col, kind in enumerate(('Sheet','Slitters','Cuts','Crease')):
            self.table.horizontalHeaderItem(col).setIcon(machine_icon(kind))
        self.target = self.home
        self.instruction.setText('Select a category icon to inspect its entries. Scrolling is application navigation; machine entry capacities and firmware pagination are unverified.')
        self.overlay.update()

    def category(self, name):
        self.viewing_main = False
        self.screen_controls()
        step = 'Cross perf' if name == 'Crease' and self.data.cross_perf else name
        if step in self.data.steps and self.steps.currentRow() != self.data.steps.index(step):
            self.steps.setCurrentRow(self.data.steps.index(step))
            return
        self.keypad.show()
        self.set_entry_style(True)
        self.screen_title.setText({'Sheet':'Set page data', 'Slitters':'Set slit data', 'Cuts':'Set cut data', 'Crease':'Set crease data'}[name])
        d = self.data
        if name == 'Sheet':
            values = self.sheet_values()
            origin = 'Length along feed, width across feed; thickness in inches from the paper profile. Automatic depth 1–5 maps machine minimum to maximum physical thickness; unavailable limits are not guessed.'
        else:
            values = list(map(machine_inches, {'Slitters': d.slits, 'Cuts': d.cuts, 'Crease': d.creases}[name]))
            if name == 'Crease' and not values:
                values = ['0.000 (unused)'] * 16
            if name == 'Slitters':
                values += ['0.000 (unused)']*max(0, 6-len(values))
            origin = 'Inches from '+('right paper edge.' if name == 'Slitters' else 'leading edge.')
        self.fill([name], [values], [origin])
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, 64)
        if name == 'Sheet':
            self.table.setVerticalHeaderLabels(['Length', 'Width', 'Thickness', 'Crease depth', 'Reg: leading edge', 'Reg: right edge'])
            for row, origin in ((4,'leading paper edge to top of mark'),(5,'right paper edge to right of mark')):
                self.table.item(row,0).setToolTip(f'Dedicated machine mark: inches from {origin}. Enable the dedicated mark in Registration setup. Unavailable values must not be entered as zero.')
        self.target = self.categories[name]
        self.instruction.setText(f'Open {name} on the machine and enter the numbered values. {origin} '+('Install cross-perf tool in place of crease tool.' if name == 'Crease' and d.cross_perf else '')+' Scroll here only as application navigation; firmware pagination is unverified.')
        if name == 'Crease' and not d.creases:
            self.instruction.setText('No crease or cross-perf operations are planned. These zero fields are unused reference entries, not instructions to add creases. Add finishing in the layout view and recalculate to populate positions. The 16 visible fields follow the sample screen, not a verified machine capacity.')
        self.overlay.update()

    def show_strikes(self):
        self.viewing_main = False
        self.screen_controls(strikes=True)
        if 'Strike perfs' in self.data.steps and self.steps.currentRow() != self.data.steps.index('Strike perfs'):
            self.steps.setCurrentRow(self.data.steps.index('Strike perfs'))
            return
        self.keypad.hide()
        self.set_entry_style(False)
        self.screen_title.setText('Set strike-perf data')
        columns, origins = [], []
        for i in range(4):
            tool = next((t for t in self.data.strikes if t.number == i+1), None)
            columns.append([machine_inches(v) for pair in tool.segments for v in pair] if tool else ['0.000 (unused)', '0.000 (unused)'])
            origins.append('Alternating start/end in inches from leading edge. Zero start is valid; only 0/0 is unused.'+ (f' Sideways {machine_inches(tool.right_um)} in from right; '+('automatic entry on tool screen.' if tool.automatic else 'physically positioned.') if tool else ' Unused tool.'))
        count = max(map(len, columns))
        for values in columns:
            values.extend(['0.000 (unused)']*(count-len(values)))
        self.fill([f'Strike tool {i}' for i in range(1, 5)], columns, origins)
        self.table.setIconSize(QSize(54,54))
        for i in range(4):
            self.table.horizontalHeaderItem(i).setIcon(machine_icon(f'Strike{i+1}'))
        self.table.setVerticalHeaderLabels([f'{i//2+1} '+('START' if i%2 == 0 else 'END') for i in range(self.table.rowCount())])
        self.target = self.strike_next
        self.instruction.setText('Use Next on the machine overview. Select a tool column header here for its entry screen. Rows alternate START / END; a zero start is valid. Scrolling here is application navigation, not verified firmware pagination.')
        self.overlay.update()

    def strike_entry(self, column):
        if not self.table.horizontalHeaderItem(0) or not self.table.horizontalHeaderItem(0).text().startswith('Strike tool'):
            return
        tool = next((t for t in self.data.strikes if t.number == column+1), None)
        if tool is None:
            return
        self.screen_controls(strikes=True)
        values = ([f'Sideways: {machine_inches(tool.right_um)}'] if tool.automatic else [])
        values += [f'{label}: {machine_inches(v)}' for pair in tool.segments for label, v in zip(('Start', 'End'), pair)]
        self.fill([f'Tool {tool.number} entries'], [values], ['Sideways measured from right paper edge; start/end from leading edge, inches.'])
        self.set_entry_style(True)
        self.screen_title.setText(f'Set strike-perf {tool.number} data')
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row,64)
        self.keypad.show()
        self.instruction.setText(('Enter automatic sideways position, then start/end pairs.' if tool.automatic else 'Position this tool physically from the right edge; enter only start/end pairs.')+' Preserve every planned segment.')

    def show_step(self, row):
        if row < 0:
            return
        name = self.data.steps[row]
        if name in ('Sheet', 'Slitters', 'Cuts'):
            self.category(name)
        elif name in ('Crease', 'Cross perf'):
            self.category('Crease')
        elif name == 'Strike perfs':
            self.show_strikes()
        elif name == 'Physical tooling':
            self.viewing_main = False
            self.screen_controls()
            self.set_entry_style(False)
            self.screen_title.setText('Physical tooling reference')
            self.keypad.hide()
            self.fill(['Physical tool checklist'], [self.data.physical or ('No additional physical perf tooling requested.',)], ['Follow approved machine installation procedure; this guide does not operate equipment.'])
            self.target = self.home
            self.instruction.setText('Check each required physical tool and its right-edge position. Rotary perfs must span the full page and have no program entries.')
        else:
            self.viewing_main = False
            self.screen_controls(layout_screen=True)
            c = self.data.candidate
            self.screen_title.setText(f'Job: {self.job_name.text() or "*"}     L:{machine_inches(c.sheet_height_um)}   W:{machine_inches(c.sheet_width_um)}')
            self.pages.setCurrentIndex(1)
            self.keypad.hide()
            self.target = None
            self.instruction.setText('Review orientation and all operations. Save using your optional job label on the machine. Feeder, adjustments, Test and Run behavior remain unverified; follow the machine manual and approved site procedure.')
        self.overlay.update()

    def set_entry_style(self, enabled):
        self.entry_delegate.entry_mode = enabled
        self.table.setAlternatingRowColors(not enabled)
        self.table.setShowGrid(not enabled)
        self.table.horizontalHeader().setVisible(not enabled)
        self.table.viewport().update()

    def field_selected(self, row, col, *_):
        item = self.table.item(row, col)
        if item:
            self.instruction.setText(item.toolTip())
        self.overlay.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'overlay'):
            self.overlay.setGeometry(self.rect())
            self.overlay.raise_()
