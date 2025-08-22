import sys
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QTextDocument, QTextCursor, QTextCharFormat, QMouseEvent
)
from PySide6.QtCore import (
    Qt, QRect, QMargins, QPoint, QEvent, QSize
)


class MailHeaderTableWidget(QTableWidget):
    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.pos())
        if item and item.column() == 1:
            # Allow the base class to handle the event for column 1
            super().mousePressEvent(event)
        # Otherwise, do nothing to prevent setting a current item
        # for column 0 or empty space.

class LabelDelegate(QStyledItemDelegate):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.selected_addresses = {} # Key: (row, col) tuple, Value: list of selected addresses
        self.email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        self.config = config
        self.bold_font = self.config.get_text_font()
        self.bold_font.setBold(True)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.bold_font)
        doc.setPlainText(index.data())
        # doc.setTextWidth(option.rect.width())
        painter.save()
        painter.translate(option.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.bold_font)
        doc.setPlainText(f"{index.data()} ")
        # doc.setTextWidth(option.rect.width())
        return QSize(doc.idealWidth(), doc.documentLayout().documentSize().height())

class AddressDelegate(QStyledItemDelegate):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.selected_addresses = {} # Key: (row, col) tuple, Value: list of selected addresses
        self.email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        self.config = config

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.config.get_text_font())
        doc.setPlainText(index.data())
        doc.setTextWidth(option.rect.width())
        
        row, col = index.row(), index.column()
        addresses_to_highlight = self.selected_addresses.get((row, col), [])
        
        cursor = QTextCursor(doc)
        text = index.data()
        
        for address in addresses_to_highlight:
            for match in re.finditer(re.escape(address), text):
                cursor.setPosition(match.start())
                cursor.setPosition(match.end(), QTextCursor.KeepAnchor)
                
                char_format = QTextCharFormat()
                char_format.setBackground(QColor("yellow"))
                cursor.setCharFormat(char_format)

        painter.save()
        painter.translate(option.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.config.get_text_font())
        doc.setPlainText(index.data())
        doc.setTextWidth(option.rect.width())
        return QSize(doc.idealWidth(), doc.documentLayout().documentSize().height())

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            text = index.data()
            row, col = index.row(), index.column()
            
            doc = QTextDocument()
            doc.setPlainText(text)
            doc.setTextWidth(option.rect.width())
            
            hit_point = event.pos() - option.rect.topLeft()
            
            char_pos = doc.documentLayout().hitTest(hit_point, Qt.HitTestAccuracy.ExactHit)
            
            for match in re.finditer(self.email_regex, text):
                if match.start() <= char_pos <= match.end():
                    address = match.group(0)
                    
                    if (row, col) not in self.selected_addresses:
                        self.selected_addresses[(row, col)] = []
                    
                    if address in self.selected_addresses[(row, col)]:
                        self.selected_addresses[(row, col)].remove(address)
                    else:
                        self.selected_addresses[(row, col)].append(address)
                    
                    model.dataChanged.emit(index, index, [Qt.DecorationRole, Qt.DisplayRole])
                    return True # Event handled
        else:
            return True
        # return super().editorEvent(event, model, option, index) # this would allow editing !


class MailHeaderWidget(QWidget):
    def __init__(self, parent, config, message):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)

        self.table_widget = MailHeaderTableWidget(self)
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

        self.data = [   
            ("From:",    message.get("From")),
            ("To:",      message.get("To")),
            ("Cc:",      message.get("Cc")),
            ("Subject:", message.get("Subject")),
            ("Date:",    message.get("Date"))
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
