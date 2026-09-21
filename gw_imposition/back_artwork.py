"""Optional back artwork, using the same isolated PDF loader as the front."""
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QPushButton, QLabel, QFileDialog
from .pdf_loader import PdfLoader, source_signature


class BackArtwork(QWidget):
    changed = Signal()
    ready = Signal()

    def __init__(self):
        super().__init__()
        self.path = None
        self.front_path = None
        self.pages = ()
        self.png = None
        self.signature = None
        self.busy = False
        self.token = 0
        self.error = ''
        self.loader = PdfLoader(self)
        self.loader.ready.connect(self.loaded)
        self.loader.failed.connect(self.failed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.mode = QComboBox()
        self.mode.addItems(['Front only','Back from same PDF','Back from another PDF'])
        layout.addWidget(self.mode)
        self.choose = QPushButton('Select back PDF…')
        self.choose.clicked.connect(self.select)
        layout.addWidget(self.choose)
        self.filename = QLabel()
        self.filename.setWordWrap(True)
        layout.addWidget(self.filename)
        self.page = QComboBox()
        self.page.currentIndexChanged.connect(self.page_changed)
        layout.addWidget(self.page)
        self.alignment = QComboBox()
        self.alignment.addItems(['Back: mirror positions left/right','Back: same positions'])
        self.alignment.setToolTip('Changes positions, not the artwork itself. Confirm printer duplex feed orientation with a test sheet.')
        self.alignment.currentIndexChanged.connect(self.changed)
        layout.addWidget(self.alignment)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.mode_changed()

    @property
    def enabled(self): return self.mode.currentIndex() != 0

    def mode_changed(self):
        self.choose.setVisible(self.mode.currentIndex()==2)
        for control in (self.filename,self.page,self.alignment): control.setVisible(self.enabled)
        self.pages = ()
        self.png = None
        self.signature = None
        self.error = ''
        self.loader.close()
        self.token += 1
        self.busy = False
        if self.mode.currentIndex()==1 and self.front_path:
            self.load(self.front_path,1)
        else:
            self.path = None
            self.filename.clear()
            self.page.clear()
            self.changed.emit()

    def select(self):
        path,_ = QFileDialog.getOpenFileName(self,'Select back artwork','','PDF files (*.pdf)')
        if path: self.load(path,0)

    def sync_front(self,path):
        self.front_path = path
        if self.mode.currentIndex()==1:
            try: same = self.path == Path(path) and self.signature == source_signature(path)
            except OSError: same = False
            if not same: self.load(path,self.page.currentIndex() if self.page.currentIndex()>=0 else 1)

    def load(self,path,index=0):
        self.path = Path(path)
        self.filename.setText(self.path.name)
        self.filename.setToolTip(str(self.path))
        self.pages = ()
        self.png = None
        self.error = ''
        self.busy = True
        self.requested_index = index
        self.token = self.loader.request(self.path,index)
        self.changed.emit()

    def page_changed(self,index):
        if self.path and index>=0: self.load(self.path,index)

    def loaded(self,token,pages,index,png):
        if token!=self.token or not self.enabled:return
        if index != self.requested_index:
            self.failed(token,'The selected back page is unavailable. Select an existing back page or another PDF.')
            self.page.blockSignals(True)
            self.page.clear()
            self.page.addItems([f'Back page {n+1}' for n in range(len(pages))])
            self.page.setCurrentIndex(-1)
            self.page.blockSignals(False)
            return
        self.pages,self.png,self.signature,self.busy = pages,png,self.loader.signature,False
        self.page.blockSignals(True)
        self.page.clear()
        self.page.addItems([f'Back page {n+1}' for n in range(len(pages))])
        self.page.setCurrentIndex(index)
        self.page.blockSignals(False)
        self.ready.emit()

    def failed(self,token,error):
        if token!=self.token:return
        self.busy = False
        self.pages = ()
        self.error = error
        self.ready.emit()

    def validate(self):
        if not self.enabled:return
        if self.busy:raise ValueError('Back PDF is still loading.')
        if not self.pages:raise ValueError(self.error or 'Select a back PDF and page.')
        if source_signature(self.path)!=self.signature:raise ValueError('Back PDF changed; reload the back artwork.')

    def snapshot(self):
        return dict(mode=self.mode.currentIndex(),path=str(self.path.resolve()) if self.path else None,
                    page=max(0,self.page.currentIndex()),mirror=self.alignment.currentIndex()==0)
