"""Original scalable touchscreen icons drawn to match the supplied machine references."""
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer


def machine_icon(name):
    backgrounds = {'Home': ('#60b95b', '#087740'), 'Slitters': ('#62b348', '#1c6224'),
                   'Cuts': ('#f46a64', '#be1526'), 'Run': ('#45bc72', '#087437')}
    top, bottom = backgrounds.get(name, ('#3bc3fa', '#0056ad'))
    if name in ('Low speed','High speed','Barcode'):
        top,bottom = '#f76565','#c51c2c'
    elif name in ('Feeder table lower','Test'):
        top,bottom = '#42c6a3','#087c62'
    page = '<path d="M17 9 H39 L49 20 V53 H17Z" fill="#ffea76" stroke="#34465a" stroke-width="2"/><path d="M39 9 V21 H49" fill="#fff5ab" stroke="#34465a" stroke-width="2"/>'
    if name == 'Home':
        body = '<path d="M13 27V55H51V27L32 11Z" fill="#ffd66d" stroke="#874f2c" stroke-width="2"/><path d="M5 30L32 5L59 30L53 35L32 16L11 35Z" fill="#ee6439" stroke="#9c422a" stroke-width="2"/><path d="M44 8H51V23H44Z" fill="#ee663c"/><path d="M27 36H39V55H27Z" fill="#af5028"/><path d="M17 30H24V39H17ZM41 30H48V39H41Z" fill="#baf2ff" stroke="white" stroke-width="2"/>'
    elif name in ('Return', 'Back'):
        body = '<path d="M53 50C51 17 36 8 21 23L21 12L5 31L22 44V32C35 21 42 36 43 50Z" fill="#f46b29" stroke="#8c4823" stroke-width="1.5"/><path d="M27 17C44 5 57 26 58 51H46C47 31 40 17 27 17Z" fill="#f5fcff"/>'
    elif name in ('Slitters', 'Cuts'):
        body = '<path d="M24 40L49 7L35 39L17 51M37 40L17 7L27 39L48 51" fill="#e7eef0" stroke="#27333a" stroke-width="3" stroke-linejoin="round"/><ellipse cx="18" cy="48" rx="10" ry="7" transform="rotate(-35 18 48)" fill="none" stroke="#253336" stroke-width="4"/><ellipse cx="46" cy="48" rx="10" ry="7" transform="rotate(35 46 48)" fill="none" stroke="#253336" stroke-width="4"/><circle cx="31" cy="35" r="3" fill="#fafafa" stroke="#24323a"/>'
    elif name == 'Crease':
        body = '<path d="M8 47H26L32 54L38 47H57V53H39L32 60L25 53H8Z" fill="#ffe335" stroke="#4a4b30" stroke-width="1.5"/><path d="M27 7H38L36 36L32 44L28 36Z" fill="#d2d6d8" stroke="#39464d" stroke-width="2"/><path d="M27 7L31 3H35L38 7" fill="#eee"/><path d="M30 12V34" stroke="white" stroke-width="2"/>'
    elif name == 'Save As':
        body = '<path d="M10 6H50L57 13V57H10Z" fill="#1263ac" stroke="#123c66" stroke-width="2"/><path d="M19 7H45V27H19Z" fill="#d6e5ed"/><path d="M36 9H43V23H36Z" fill="#374b59"/><path d="M18 34H49V57H18Z" fill="#fffbed" stroke="#758591"/><path d="M23 40H44M23 46H44M23 52H40" stroke="#8cb0cb" stroke-width="2"/>'
    elif name == 'Run':
        body = '<path d="M19 10L54 32L19 54Z" fill="#f5fff2" stroke="#cceddb" stroke-width="1.5"/>'
    elif name in ('Low speed', 'High speed'):
        body = '<g fill="none" stroke="#131a20" stroke-width="3"><circle cx="15" cy="45" r="11"/><circle cx="49" cy="45" r="11"/><path d="M15 45L26 25L37 45H15L31 32L49 45M37 45L43 25H49"/></g><circle cx="34" cy="12" r="5" fill="#131a20"/><path d="M30 18L22 28L34 33L29 45M30 18L42 23H49" fill="none" stroke="#131a20" stroke-width="5"/>'
        if name == 'High speed':
            body += '<path d="M3 15H20M3 23H16" stroke="white" stroke-width="3"/>'
    elif name == 'Number of sheets':
        body = '<path d="M13 10H44L51 49H13Z" fill="#fff58c" stroke="#464843" stroke-width="2"/><path d="M9 18H39L45 55H9Z" fill="#f3da39" stroke="#464843" stroke-width="2"/><path d="M20 23H53V57H20Z" fill="#ffe96a" stroke="#464843" stroke-width="2"/>'
    elif name == 'Unused':
        body = '<path d="M10 8H39V36H10Z" fill="#e7d33b" stroke="white" stroke-width="2"/><path d="M5 28H33V56H5Z" fill="#57c783" stroke="white" stroke-width="2"/><path d="M28 24H57V53H28Z" fill="#d561ce" stroke="white" stroke-width="2"/>'
    elif name == 'Barcode':
        body = '<rect x="7" y="6" width="50" height="51" fill="#e93d46"/>' + ''.join(f'<rect x="{x}" y="13" width="{w}" height="36" fill="#16212a"/>' for x,w in ((12,3),(18,2),(23,4),(30,2),(35,3),(42,2),(47,4)))
    elif name == 'Reg mark':
        body = page + '<path d="M25 40V30H43M25 45H32" fill="none" stroke="#159cdb" stroke-width="4"/>'
    elif name == 'Feeder table lower':
        body = '<path d="M26 9H39V30H49L32 46L15 30H26Z" fill="#e7fff5"/><path d="M12 43V54H53V43" fill="none" stroke="#e7fff5" stroke-width="5"/>'
    elif name == 'Perf check':
        body = '<path d="M18 7H47V24H18Z" fill="#f5fafb" stroke="#52697b"/><rect x="8" y="22" width="48" height="29" rx="5" fill="#405a6d"/><path d="M18 37H47V59H18Z" fill="#eaf9ff" stroke="#6887a0"/><path d="M23 44H42M23 49H42M23 54H39" stroke="#287bae" stroke-width="2"/><circle cx="48" cy="29" r="3" fill="#59e5b4"/>'
    elif name == 'Test':
        body = '<path d="M26 8H39V30H50L32 47L14 30H26Z" fill="#075df1"/><path d="M8 53H57" stroke="#fff236" stroke-width="7"/>'
    elif name.startswith('Strike'):
        number = int(name[-1])
        y = 18 + (number-1)*10
        body = '<path d="M10 12H39L54 27V54H10Z" fill="#f6e584" stroke="#304c65" stroke-width="2"/><path d="M39 12Q45 16 42 27H54" fill="#fff5b4" stroke="#304c65" stroke-width="2"/>'
        if number > 1:
            body += f'<path d="M14 {y}H49" stroke="#33454f" stroke-width="2.5" stroke-dasharray="3 3"/>'
    elif name == 'Fold':
        body = '<path d="M13 9L26 17L52 52L31 57Z" fill="#fce75f" stroke="#39495a" stroke-width="2"/><path d="M13 9L12 34L31 57L25 18Z" fill="#a9b7c3" stroke="#39495a" stroke-width="2"/>'
    else:
        body = page + '<path d="M44 34V55M34 45H55" stroke="#eafaff" stroke-width="10"/><path d="M44 34V55M34 45H55" stroke="#00a2ee" stroke-width="6"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><defs><linearGradient id="b" x2="0" y2="1"><stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient></defs><rect x="1" y="1" width="62" height="62" fill="url(#b)" stroke="#354d63" stroke-width="2"/><path d="M2 62V2H62" fill="none" stroke="#b4e9ed" stroke-width="2"/>{body}</svg>'
    if name == 'Slitters':
        svg = svg.replace(body, '<g transform="rotate(90 32 32)">'+body+'</g>')
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)
