"""Dark interface with Graphic Whizard blue/green brand accents."""
from PySide6.QtGui import QColor, QPalette


def dark_palette():
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, '#121B24'),
        (QPalette.ColorRole.WindowText, '#E5EDF3'),
        (QPalette.ColorRole.Base, '#101820'),
        (QPalette.ColorRole.AlternateBase, '#1B2935'),
        (QPalette.ColorRole.Text, '#E5EDF3'),
        (QPalette.ColorRole.Button, '#243543'),
        (QPalette.ColorRole.ButtonText, '#E5EDF3'),
        (QPalette.ColorRole.Highlight, '#004B7F'),
        (QPalette.ColorRole.HighlightedText, '#FFFFFF'),
        (QPalette.ColorRole.PlaceholderText, '#91A3B2'),
        (QPalette.ColorRole.ToolTipBase, '#243543'),
        (QPalette.ColorRole.ToolTipText, '#FFFFFF'),
        (QPalette.ColorRole.Light, '#425566'),
        (QPalette.ColorRole.Mid, '#304454'),
        (QPalette.ColorRole.Dark, '#0B1118'),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#748593'))
    return palette


STYLE = """
QWidget { color: #E5EDF3; }
QMainWindow { background: #121B24; }
QWidget#finishingBody, QWidget#registrationBody { background: #121B24; }
QDoubleSpinBox:disabled { color: #748593; background: #1A2631; }
QTabWidget::pane { border: 1px solid #354A5B; }
QTabBar::tab { background: #243543; color: #E5EDF3; padding: 8px 14px; }
QTabBar::tab:selected { background: #004B7F; border-bottom: 2px solid #B3D485; }
QGroupBox { background: #1B2935; border: 1px solid #354A5B; border-radius: 6px;
            margin-top: 12px; padding: 10px; }
QGroupBox::title { color: #B3D485; subcontrol-origin: margin; left: 12px; font-weight: bold; }
QPushButton { background: #243543; color: #E5EDF3; border: 1px solid #425D70;
              border-radius: 4px; padding: 6px 10px; }
QPushButton:hover { background: #2C4446; border-color: #B3D485; }
QPushButton:pressed { background: #B3D485; color: #121B24; }
QPushButton:disabled { color: #748593; background: #1A2631; border-color: #30414E; }
QPushButton#calculate { background: #004B7F; color: white; padding: 10px; font-weight: bold;
                       border: 1px solid #086397; border-bottom: 3px solid #B3D485; }
QPushButton#calculate:hover { background: #086397; }
QPushButton#calculate:disabled { background: #263C4B; color: #91A3B2; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QTableWidget { background: #101820; color: #E5EDF3;
    border: 1px solid #354A5B; border-radius: 3px; selection-background-color: #004B7F;
    selection-color: white; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { padding: 4px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #B3D485; }
QComboBox QAbstractItemView { background: #1B2935; color: #E5EDF3;
    selection-background-color: #004B7F; selection-color: white; }
QHeaderView::section { background: #243543; color: #B3D485;
    border: none; border-bottom: 2px solid #B3D485; padding: 5px; font-weight: bold; }
QTableWidget { gridline-color: #304454; }
QTableWidget::item:selected { background: #004B7F; color: white; }
QTableCornerButton::section { background: #243543; border: none; }
QCheckBox { spacing: 5px; }
QStatusBar { background: #1E3034; color: #B3D485; }
QToolTip { background: #243543; color: #FFFFFF; border: 1px solid #B3D485; }
"""

# “Lead becomes gold when properly described to an investor.”
LIGHT_STYLE = """
QWidget { color: #173447; }
QMainWindow { background: #F3F6F8; }
QWidget#finishingBody, QWidget#registrationBody { background: #F3F6F8; }
QDoubleSpinBox:disabled { color: #81909A; background: #EDF1F3; }
QTabWidget::pane { border: 1px solid #BCCDD8; }
QTabBar::tab { background: #E8F1DC; color: #004B7F; padding: 8px 14px; }
QTabBar::tab:selected { background: white; border-bottom: 2px solid #004B7F; }
QGroupBox { background: white; border: 1px solid #CCD9E1; border-radius: 6px;
            margin-top: 12px; padding: 10px; }
QGroupBox::title { color: #004B7F; subcontrol-origin: margin; left: 12px; font-weight: bold; }
QPushButton { background: white; color: #004B7F; border: 1px solid #9AB3C4;
              border-radius: 4px; padding: 6px 10px; }
QPushButton:hover { background: #E8F1DC; border-color: #6E9449; }
QPushButton:pressed { background: #B3D485; }
QPushButton:disabled { color: #81909A; background: #EDF1F3; border-color: #D5DEE4; }
QPushButton#calculate { background: #004B7F; color: white; padding: 10px; font-weight: bold;
                       border: 1px solid #004B7F; border-bottom: 3px solid #B3D485; }
QPushButton#calculate:hover { background: #086397; }
QPushButton#calculate:disabled { background: #91A9B8; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QTableWidget { background: white; color: #173447;
    border: 1px solid #BCCDD8; border-radius: 3px; selection-background-color: #004B7F;
    selection-color: white; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { padding: 4px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #004B7F; }
QComboBox QAbstractItemView { background: white; color: #173447;
    selection-background-color: #004B7F; selection-color: white; }
QHeaderView::section { background: #E8F1DC; color: #004B7F;
    border: none; border-bottom: 2px solid #B3D485; padding: 5px; font-weight: bold; }
QTableWidget { gridline-color: #D5DEE4; }
QTableWidget::item:selected { background: #004B7F; color: white; }
QTableCornerButton::section { background: #E8F1DC; border: none; }
QCheckBox { spacing: 5px; }
QStatusBar { background: #E8F1DC; color: #004B7F; }
QToolTip { background: white; color: #173447; border: 1px solid #004B7F; }
"""
