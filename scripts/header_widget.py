import sys
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView, QStyle
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QTextDocument, QTextCursor, QTextCharFormat, QMouseEvent, QClipboard
)
from PySide6.QtCore import (
    Qt, QRect, QMargins, QPoint, QEvent, QSize
)
from email.utils import parsedate_to_datetime
from common import create_date_item

class MailHeaderTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.selection_in_progress = False
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Start text selection
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                delegate = self.itemDelegate(index)
                if hasattr(delegate, 'start_text_selection'):
                    delegate.start_text_selection(index, event.position().toPoint())
                    self.selection_in_progress = True
        elif event.button() == Qt.RightButton:
            # Let base class handle for address selection via editorEvent
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.selection_in_progress:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                delegate = self.itemDelegate(index)
                if hasattr(delegate, 'update_text_selection'):
                    delegate.update_text_selection(index, event.position().toPoint())
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.selection_in_progress:
            self.selection_in_progress = False
            # Copy to selection buffer for middle-click paste
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                delegate = self.itemDelegate(index)
                if hasattr(delegate, 'finalize_selection'):
                    delegate.finalize_selection(index)
        super().mouseReleaseEvent(event)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and (event.modifiers() & Qt.ControlModifier):
            self.copy_selection_to_clipboard()
        else:
            super().keyPressEvent(event)
    
    def copy_selection_to_clipboard(self):
        """Copy current selection to clipboard (Ctrl+C)"""
        index = self.currentIndex()
        if index.isValid():
            delegate = self.itemDelegate(index)
            if hasattr(delegate, 'get_selected_text'):
                text = delegate.get_selected_text(index)
                if text:
                    QApplication.clipboard().setText(text, QClipboard.Clipboard)

class TextSelectableDelegate(QStyledItemDelegate):
    """Base delegate with shared text-selection machinery.

    Subclasses override _font() and _text_width() to customise rendering,
    and may add their own paint() highlights / editorEvent() handling.
    """
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.text_selection = {}  # (row, col) -> (start_char, end_char)
        self.selection_start_cell = None

    def _font(self):
        return self.config.get_text_font()

    def _text_width(self, index):
        return None  # no word-wrap by default

    def _make_doc(self, index):
        doc = QTextDocument()
        doc.setDefaultFont(self._font())
        text = index.data(Qt.DisplayRole) if index.data(Qt.DisplayRole) else ""
        doc.setPlainText(text)
        width = self._text_width(index)
        if width:
            doc.setTextWidth(width)
        return doc

    def _char_pos(self, doc, index, pos):
        hit_point = pos - self.parent().visualRect(index).topLeft()
        char_pos = doc.documentLayout().hitTest(hit_point, Qt.HitTestAccuracy.ExactHit)
        text = index.data(Qt.DisplayRole) if index.data(Qt.DisplayRole) else ""
        # hitTest returns -1 when beyond text boundaries
        if char_pos < 0:
            return len(text)
        return max(0, min(char_pos, len(text)))

    def _apply_selection_highlight(self, doc, index):
        row, col = index.row(), index.column()
        selection = self.text_selection.get((row, col))
        if selection and selection[0] != selection[1]:
            cursor = QTextCursor(doc)
            start, end = min(selection[0], selection[1]), max(selection[0], selection[1])
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            char_format = QTextCharFormat()
            char_format.setBackground(QColor(180, 200, 255))  # Light blue
            cursor.setCharFormat(char_format)

    def start_text_selection(self, index, pos):
        row, col = index.row(), index.column()
        doc = self._make_doc(index)
        char_pos = self._char_pos(doc, index, pos)
        self.text_selection.clear()
        self.selection_start_cell = (row, col)
        self.text_selection[(row, col)] = (char_pos, char_pos)
        self.parent().viewport().update()

    def update_text_selection(self, index, pos):
        row, col = index.row(), index.column()
        if self.selection_start_cell != (row, col):
            return
        doc = self._make_doc(index)
        char_pos = self._char_pos(doc, index, pos)
        self.text_selection[(row, col)] = (self.text_selection[(row, col)][0], char_pos)
        self.parent().viewport().update()

    def finalize_selection(self, index):
        text = self.get_selected_text(index)
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text, QClipboard.Mode.Selection)  # For middle-click paste

    def get_selected_text(self, index):
        row, col = index.row(), index.column()
        selection = self.text_selection.get((row, col))
        if selection and selection[0] != selection[1]:
            text = index.data(Qt.DisplayRole) if index.data(Qt.DisplayRole) else ""
            start, end = min(selection[0], selection[1]), max(selection[0], selection[1])
            return text[start:end]
        return None

class LabelDelegate(TextSelectableDelegate):
    def __init__(self, parent, config):
        super().__init__(parent, config)
        self.bold_font = self.config.get_text_font()
        self.bold_font.setBold(True)

    def _font(self):
        return self.bold_font

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Force consistent appearance regardless of selection state
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.State_Selected
        opt.state &= ~QStyle.State_HasFocus

        doc = self._make_doc(index)
        self._apply_selection_highlight(doc, index)

        painter.save()
        painter.translate(opt.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = self._make_doc(index)
        return QSize(doc.idealWidth(), doc.documentLayout().documentSize().height())

def split_addresses(text):
    """Split an address-list into (start, end) spans of each address.
    Handles RFC 5322 §3.4: quoted strings, angle-addr, domain literals,
    nested comments, and quoted-pair escapes. A comma separates addresses
    only when none of these constructs is open."""
    spans = []
    start = 0
    in_quote = False
    in_angle = False
    in_bracket = False
    comment_depth = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n:      # quoted-pair escape
            i += 2
            continue
        if in_quote:
            if c == '"':
                in_quote = False
        elif in_angle:
            if c == '>':
                in_angle = False
        elif in_bracket:
            if c == ']':
                in_bracket = False
        elif comment_depth:
            if c == '(':
                comment_depth += 1
            elif c == ')':
                comment_depth -= 1
        else:
            if c == '"':
                in_quote = True
            elif c == '<':
                in_angle = True
            elif c == '[':
                in_bracket = True
            elif c == '(':
                comment_depth = 1
            elif c == ',':
                spans.append((start, i))
                start = i + 1
        i += 1
    if start < n:
        spans.append((start, n))
    return spans

class AddressDelegate(TextSelectableDelegate):
    def __init__(self, parent, config):
        super().__init__(parent, config)
        self.selected_addresses = {} # Key: (row, col) tuple, Value: list of selected addresses

    def _text_width(self, index):
        return self.parent().visualRect(index).width()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Force consistent appearance regardless of selection state
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.State_Selected
        opt.state &= ~QStyle.State_HasFocus

        doc = self._make_doc(index)
        text = index.data(Qt.DisplayRole) if index.data(Qt.DisplayRole) else ""

        row, col = index.row(), index.column()
        addresses_to_highlight = self.selected_addresses.get((row, col), [])

        cursor = QTextCursor(doc)

        # Apply email address highlighting (yellow)
        for address in addresses_to_highlight:
            for match in re.finditer(re.escape(address), text):
                cursor.setPosition(match.start())
                cursor.setPosition(match.end(), QTextCursor.KeepAnchor)

                char_format = QTextCharFormat()
                char_format.setBackground(QColor("yellow"))
                cursor.setCharFormat(char_format)

        # Apply text selection highlighting (light blue, on top)
        self._apply_selection_highlight(doc, index)

        painter.save()
        painter.translate(opt.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = self._make_doc(index)
        return QSize(doc.idealWidth(), doc.documentLayout().documentSize().height())

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.RightButton:
            text = index.data(Qt.DisplayRole) if index.data(Qt.DisplayRole) else ""
            row, col = index.row(), index.column()
            
            doc = QTextDocument()
            doc.setDefaultFont(self.config.get_text_font())  # Must match font used in paint()
            doc.setPlainText(text)
            doc.setTextWidth(option.rect.width())
            
            hit_point = event.position().toPoint() - option.rect.topLeft()
            
            char_pos = doc.documentLayout().hitTest(hit_point, Qt.HitTestAccuracy.ExactHit)
            
            for (s, e) in split_addresses(text):
                if s <= char_pos <= e:
                    address = text[s:e].strip()
                    
                    if (row, col) not in self.selected_addresses:
                        self.selected_addresses[(row, col)] = []
                    
                    if address in self.selected_addresses[(row, col)]:
                        self.selected_addresses[(row, col)].remove(address)
                    else:
                        self.selected_addresses[(row, col)].append(address)
                    
                    model.dataChanged.emit(index, index, [Qt.DecorationRole, Qt.DisplayRole])
                    return True # Event handled
        else:
            return False # Allow default behavior for left/middle clicks (text selection)


class MailHeaderWidget(QWidget):
    def __init__(self, parent, config, message):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)

        self.table_widget = MailHeaderTableWidget(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.table_widget)

        self.table_widget.setColumnCount(2)
        self.table_widget.horizontalHeader().hide()
        self.table_widget.verticalHeader().hide()
        self.table_widget.setShowGrid(False)
        self.table_widget.setWordWrap(True)

        self.table_widget.setSelectionMode(QAbstractItemView.NoSelection)

        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_widget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.label_delegate = LabelDelegate(self.table_widget, config)
        self.table_widget.setItemDelegateForColumn(0, self.label_delegate)
        self.address_delegate = AddressDelegate(self.table_widget, config)
        self.table_widget.setItemDelegateForColumn(1, self.address_delegate)

        date_header = message.get("Date")
        timestamp = 0
        if date_header:
            try:
                # RFC 5322 §3.3: zone may be 2 or 4 digits ("+02" or "+0200").
                # Python's parsedate_to_datetime misreads 2-digit as minutes (+00:02).
                date_header = re.sub(
                    r"([+-]\d{2})$", r"\g<1>00", date_header.strip()
                )
                dt = parsedate_to_datetime(date_header)
                if dt:
                    timestamp = dt.timestamp()
            except Exception:
                pass

        # Show the parsed timestamp only when a Date header was present;
        # notmuch's search timestamp is not available here (we only have the
        # raw file), so a missing Date header must not show a bogus epoch-0.
        if date_header:
            date_display = f"{date_header}  [{create_date_item(timestamp).text()}]"
        else:
            date_display = "no date given"

        self.data = [   
            ("Subject:", message.get("Subject")),
            ("From:",    message.get("From")),
            ("To:",      message.get("To")),
            ("Cc:",      message.get("Cc")),
            ("Date:",    date_display)
        ]
        
        self.table_widget.setRowCount(len(self.data))
        self.populate_table(config)

        # Set the current item to None to remove initial highlight
        self.table_widget.setCurrentItem(None)

    def populate_table(self, config):
        bold_font = config.get_text_font()
        bold_font.setBold(True)

        row_idx = 0
        for label, value in self.data:
            if value:
                label_item = QTableWidgetItem(label)
                label_item.setFont(bold_font)
                label_item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsSelectable)           
                self.table_widget.setItem(row_idx, 0, label_item)
                value_item = QTableWidgetItem(value)
                value_item.setFlags(value_item.flags() & ~Qt.ItemIsSelectable)
                self.table_widget.setItem(row_idx, 1, value_item)
                row_idx = row_idx + 1
    
    def update_fonts(self):
        """Recreate delegates and repaint after config changes."""
        self.label_delegate = LabelDelegate(self.table_widget, config)
        self.table_widget.setItemDelegateForColumn(0, self.label_delegate)
        self.address_delegate = AddressDelegate(self.table_widget, config)
        self.table_widget.setItemDelegateForColumn(1, self.address_delegate)
        self.table_widget.viewport().update()

    def get_selected_addresses(self):
        """Return list of all selected email addresses"""
        addresses = []
        for cell_addresses in self.address_delegate.selected_addresses.values():
            addresses.extend(cell_addresses)
        return addresses

class MailClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mail Header Widget Demo")
        self.setGeometry(100, 100, 800, 250)

        mail_header_widget = MailHeaderWidget()
        self.setCentralWidget(mail_header_widget)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MailClient()
    window.show()
    sys.exit(app.exec())

# end of file
