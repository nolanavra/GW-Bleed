"""Page library with bounded, process-isolated inspection and lazy thumbnails."""
from collections import deque
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QListWidgetItem,QLabel,QFileDialog
from .pdf_loader import PdfLoader,source_signature


class PageList(QListWidget):
    files_dropped = Signal(object)
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setIconSize(QSize(58,58))
        self.setMinimumHeight(150)
        self.setMaximumHeight(260)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self,event): event.acceptProposedAction()
    def dropEvent(self,event):
        self.files_dropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class ArtworkLibrary(QWidget):
    assign_front = Signal(str,int)
    assign_back = Signal(str,int)
    clear_back = Signal()
    swap = Signal()
    undo = Signal()
    rotate_front = Signal()
    rotate_back = Signal()
    relinked = Signal(str,str)
    compare = Signal()

    def __init__(self):
        super().__init__()
        self.documents = {}
        self.assignments = {}
        self.queue = deque()
        self.active = None
        self.loader = PdfLoader(self)
        self.loader.ready.connect(self.loaded)
        self.loader.failed.connect(self.failed)
        layout = QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        add = QPushButton('Import PDFs…');add.clicked.connect(self.choose)
        layout.addWidget(add)
        self.pages = PageList();layout.addWidget(self.pages)
        self.pages.files_dropped.connect(self.import_files)
        self.pages.currentItemChanged.connect(self.thumbnails)
        self.pages.verticalScrollBar().valueChanged.connect(self.thumbnails)
        row = QHBoxLayout()
        for label,signal in (('Use as Front',self.assign_front),('Use as Back',self.assign_back)):
            button=QPushButton(label)
            button.clicked.connect(lambda _=False,s=signal:self.assign(s))
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label,signal in (('Clear Back',self.clear_back),('Swap',self.swap),('Undo',self.undo)):
            button=QPushButton(label);button.clicked.connect(lambda _=False,s=signal:s.emit());row.addWidget(button)
        layout.addLayout(row)
        self.front = QLabel('Front: unassigned');self.front.setWordWrap(True)
        self.back = QLabel('Back: unassigned');self.back.setWordWrap(True)
        self.front_icon,self.back_icon = QLabel(),QLabel()
        for icon,label in ((self.front_icon,self.front),(self.back_icon,self.back)):
            icon.setFixedSize(44,44)
            row=QHBoxLayout();row.addWidget(icon);row.addWidget(label,1);layout.addLayout(row)
        row = QHBoxLayout()
        for label,signal in (('Rotate front 90°',self.rotate_front),('Rotate back 90°',self.rotate_back)):
            button=QPushButton(label);button.clicked.connect(lambda _=False,s=signal:s.emit());row.addWidget(button)
        layout.addLayout(row)
        relink=QPushButton('Relink / reload selected PDF…');relink.clicked.connect(self.relink);layout.addWidget(relink)
        compare=QPushButton('Compare front and back…');compare.clicked.connect(lambda:self.compare.emit());layout.addWidget(compare)
        self.status = QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)

    def choose(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Import artwork PDFs','','PDF files (*.pdf)')
        self.import_files(paths)

    def import_files(self,paths):
        for path in paths:
            path=str(Path(path).resolve())
            if Path(path).suffix.lower()!='.pdf':continue
            if path not in self.documents and not any(p==path for p,_ in self.queue):
                if len(set(self.documents)|{p for p,_ in self.queue}|({self.active[0]} if self.active else set()))>=100:
                    self.status.setText('Library limit: 100 PDFs.');break
                self.queue.append((path,0))
        self.next_request()
        QTimer.singleShot(0,self.thumbnails)

    def next_request(self):
        if self.active or not self.queue:return
        self.active=self.queue.popleft()
        self.loader.request(*self.active)
        self.status.setText('Reading artwork…')

    def loaded(self,token,pages,index,png):
        if not self.active:return
        path,_=self.active
        self.add_document(path,pages,self.loader.signature)
        pix=QPixmap();pix.loadFromData(png)
        for i in range(self.pages.count()):
            item=self.pages.item(i)
            if item.data(Qt.ItemDataRole.UserRole)==(path,index):
                item.setIcon(QIcon(pix.scaled(58,58,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)))
                item.setData(Qt.ItemDataRole.UserRole+1,True)
        self.active=None
        self.status.clear()
        self.next_request()
        QTimer.singleShot(0,self.thumbnails)

    def failed(self,token,error):
        self.status.setText(error)
        self.active=None
        self.next_request()

    def add_document(self,path,pages,signature):
        path=str(Path(path).resolve())
        old=self.documents.get(path)
        if old and old['signature']==signature:return
        if sum(len(d['pages']) for key,d in self.documents.items() if key!=path)+len(pages)>1000:
            self.status.setText('Library limit: 1,000 pages.');return
        self.documents[path]=dict(pages=pages,signature=signature)
        self.pages.blockSignals(True)
        for i in reversed(range(self.pages.count())):
            if self.pages.item(i).data(Qt.ItemDataRole.UserRole)[0]==path:self.pages.takeItem(i)
        for index,page in enumerate(pages):
            item=QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole,(path,index))
            item.setToolTip(path)
            self.pages.addItem(item)
        self.pages.blockSignals(False)
        self.refresh_labels()

    def thumbnails(self,*_):
        # Load only selected/visible rows. Full-resolution previews stay in bounded loaders.
        for i in range(self.pages.count()):
            item=self.pages.item(i)
            pair=item.data(Qt.ItemDataRole.UserRole)
            if not item.data(Qt.ItemDataRole.UserRole+1) and (item==self.pages.currentItem() or self.pages.visualItemRect(item).intersects(self.pages.viewport().rect())):
                if pair!=self.active and pair not in self.queue:self.queue.append(pair)
        self.next_request()

    def assign(self,signal):
        item=self.pages.currentItem()
        if item:
            path,index=item.data(Qt.ItemDataRole.UserRole)
            try:
                if source_signature(path)!=self.documents[path]['signature']:
                    raise ValueError('PDF changed. Relink/reload it and review the page before assignment.')
                signal.emit(path,index)
            except (ValueError,OSError) as exc:self.status.setText(str(exc))

    def refresh_labels(self):
        for i in range(self.pages.count()):
            item=self.pages.item(i);path,index=item.data(Qt.ItemDataRole.UserRole)
            page=self.documents[path]['pages'][index]
            roles=', '.join(side for side,pair in self.assignments.items() if pair==(path,index))
            item.setText(f'{Path(path).name} · {index+1}'+(f' [{roles}]' if roles else '')+f'\n{page.width_points/72:.3f} × {page.height_points/72:.3f} in')
        for side,icon in (('Front',self.front_icon),('Back',self.back_icon)):
            icon.clear()
            for i in range(self.pages.count()):
                item=self.pages.item(i)
                if item.data(Qt.ItemDataRole.UserRole)==self.assignments.get(side):
                    icon.setPixmap(item.icon().pixmap(44,44));break

    def set_assignments(self,front,back,front_angle=0,back_angle=0):
        self.assignments={key:(str(Path(pair[0]).resolve()),pair[1]) for key,pair in (('Front',front),('Back',back)) if pair}
        for name,label,angle in (('Front',self.front,front_angle),('Back',self.back,back_angle)):
            pair=self.assignments.get(name)
            label.setText(f'{name}: {Path(pair[0]).name} · page {pair[1]+1} · {angle}°' if pair else f'{name}: unassigned')
        self.refresh_labels()

    def relink(self):
        item=self.pages.currentItem()
        if not item:return
        old,_=item.data(Qt.ItemDataRole.UserRole)
        new,_=QFileDialog.getOpenFileName(self,'Relink or reload PDF',old,'PDF files (*.pdf)')
        if new:
            self.documents.pop(str(Path(new).resolve()),None)
            self.import_files([new])
            self.relinked.emit(old,new)

    def snapshot(self): return list(self.documents)

    def close(self):
        self.queue.clear();self.loader.close()
        return super().close()
