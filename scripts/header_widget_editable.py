#!/usr/bin/env python3

import sys
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView, QLineEdit, QItemDelegate, QMenu
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QTextDocument, QTextCursor, QTextCharFormat, QMouseEvent,
    QAction, QDrag
)
from PySide6.QtCore import (
    Qt, QRect, QMargins, QPoint, QEvent, QSize, QMimeData, Signal
)


# Shared comprehensive regex for RFC 5322 email addresses with or without display names
EMAIL_ADDRESS_REGEX = re.compile(r'(?:"[^"]*"|[^,<>"])*?(?:<([^<>]+)>|([^,<>\s]+@[^,<>\s]+))')


class AddressEditLineEdit(QLineEdit):
    """
    A QLineEdit subclass that handles email addresses as draggable units.
    It supports moving a full email address from one field to another.
    """
    addressRemoved = Signal(str)  # Signal emitted when an address is removed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # Initialize drag-related attributes
        self.dragged_address = None
        self.dragged_start = -1
        self.dragged_end = -1

    def mousePressEvent(self, event):
        """Finds the address to be dragged when the mouse is pressed."""
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            text = self.text()
            cursor_pos = self.cursorPosition()
            
            # Find the address that contains the cursor position
            match = self.find_address_at_pos(text, cursor_pos)
            
            if match:
                self.dragged_address = match.group().strip()
                self.dragged_start = match.start()
                self.dragged_end = match.end()
            else:
                self.dragged_address = None
                self.dragged_start = -1
                self.dragged_end = -1

    def mouseMoveEvent(self, event):
        """Executes the drag if a valid address was selected and the mouse moved."""
        if self.dragged_address and (event.buttons() & Qt.MouseButton.LeftButton):
            # Minimum drag distance
            if (event.pos() - self.mousePressPos).manhattanLength() < QApplication.startDragDistance():
                return
                
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.dragged_address)
            drag.setMimeData(mime_data)
            
            # Start the drag and get the final drop action
            drop_action = drag.exec(Qt.MoveAction | Qt.CopyAction)
            
            # If the drop was a move action, remove the address from this field
            if drop_action == Qt.MoveAction:
                self.remove_address()
                # Emit signal with the removed address
                self.addressRemoved.emit(self.dragged_address)
                self.dragged_address = None
                
        super().mouseMoveEvent(event)

    def dropEvent(self, event):
        """Handles dropping an address into this field."""
        if event.mimeData().hasText():
            dropped_text = event.mimeData().text()
            # Ensure the dropped text is a valid email address
            if EMAIL_ADDRESS_REGEX.fullmatch(dropped_text.strip()):
                current_text = self.text()
                if current_text:
                    new_text = f"{current_text}, {dropped_text}"
                else:
                    new_text = dropped_text
                
                self.setText(new_text)
                
                # Accept the event as a move action to signal the source to clear
                event.acceptProposedAction()
                event.setDropAction(Qt.MoveAction)
                return

        super().dropEvent(event)

    def find_address_at_pos(self, text, pos):
        """Helper to find the regex match at a specific cursor position."""
        for match in EMAIL_ADDRESS_REGEX.finditer(text):
            if match.start() <= pos <= match.end():
                return match
        return None

    def remove_address(self):
        """Removes the last dragged address from the line edit."""
        current_text = self.text()
        if self.dragged_start != -1 and self.dragged_end != -1:
            # Remove the address and any leading/trailing comma/whitespace
            prefix = current_text[:self.dragged_start].rstrip(' ,')
            suffix = current_text[self.dragged_end:].lstrip(' ,')
            
            if prefix and suffix:
                new_text = f"{prefix}, {suffix}"
            elif prefix:
                new_text = prefix
            elif suffix:
                new_text = suffix
            else:
                new_text = ""
                
            self.setText(new_text)


class ReadOnlyDelegate(QStyledItemDelegate):
    """Delegate for read-only cells in the header table (like label column)."""
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.bold_font = self.config.get_text_font()
        self.bold_font.setBold(True)

    def paint(self, painter, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.bold_font)
        doc.setPlainText(index.data())
        
        painter.save()
        painter.translate(option.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(self.bold_font)
        doc.setPlainText(f"{index.data()} ")
        return QSize(doc.idealWidth(), doc.documentLayout().documentSize().height())


class EditableAddressDelegate(QItemDelegate):
    """Delegate for editable email address fields."""
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config

    def createEditor(self, parent, option, index):
        editor = AddressEditLineEdit(parent)
        editor.setFont(self.config.get_text_font())
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data() or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text())

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class MailHeaderTableWidgetEditable(QTableWidget):
    """Editable table for email headers."""
    def __init__(self, parent, config, message=None):
        super().__init__(parent)
        self.config = config
        self.message = message
        self.setColumnCount(2)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setWordWrap(True)

        # Configure header behavior
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Set up delegates
        self.label_delegate = ReadOnlyDelegate(self, config)
        self.setItemDelegateForColumn(0, self.label_delegate)
        self.address_delegate = EditableAddressDelegate(self, config)
        self.setItemDelegateForColumn(1, self.address_delegate)

        # Define the header fields
        self.header_fields = [
            ("Subject:", ""),
            ("From:", ""),
            ("To:", ""),
            ("Cc:", ""),
            ("Bcc:", ""),
            ("Reply-To:", "")
        ]

        # Populate the table
        self.setup_table()
        
        # If a message is provided, populate from it
        if message:
            self.populate_from_message(message)

        # Set up context menu for value cells
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def setup_table(self):
        """Initialize the table with header rows."""
        self.setRowCount(len(self.header_fields))
        
        bold_font = self.config.get_text_font()
        bold_font.setBold(True)
        
        for row, (label, _) in enumerate(self.header_fields):
            # Create label item (read-only)
            label_item = QTableWidgetItem(label)
            label_item.setFont(bold_font)
            label_item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row, 0, label_item)
            
            # Create value item (editable)
            value_item = QTableWidgetItem("")
            self.setItem(row, 1, value_item)

    def populate_from_message(self, message):
        """Populate the header fields from an email message."""
        header_mapping = {
            "Subject:": message.get("Subject", ""),
            "From:": message.get("From", ""),
            "To:": message.get("To", ""),
            "Cc:": message.get("Cc", ""),
            "Bcc:": message.get("Bcc", ""),
            "Reply-To:": message.get("Reply-To", "")
        }
        
        for row in range(self.rowCount()):
            label = self.item(row, 0).text()
            if label in header_mapping:
                self.item(row, 1).setText(header_mapping[label])

    def get_header_values(self):
        """Return a dictionary of header field values."""
        headers = {}
        for row in range(self.rowCount()):
            label = self.item(row, 0).text().rstrip(':')
            value = self.item(row, 1).text().strip()
            if value:  # Only include non-empty headers
                headers[label] = value
        return headers

    def show_context_menu(self, pos):
        """Show context menu for the cell at the given position."""
        item = self.itemAt(pos)
        if item and item.column() == 1:  # Only for value cells
            menu = QMenu(self)
            
            # Add Copy action
            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(lambda: self.copy_cell_value(item))
            menu.addAction(copy_action)
            
            # Add Clear action
            clear_action = QAction("Clear", self)
            clear_action.triggered.connect(lambda: self.clear_cell_value(item))
            menu.addAction(clear_action)
            
            menu.exec(self.mapToGlobal(pos))

    def copy_cell_value(self, item):
        """Copy the cell value to clipboard."""
        QApplication.clipboard().setText(item.text())

    def clear_cell_value(self, item):
        """Clear the cell value."""
        item.setText("")


class MailHeaderEditableWidget(QWidget):
    """Widget that wraps the editable mail header table."""
    def __init__(self, parent, config, message=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.header_table = MailHeaderTableWidgetEditable(self, config, message)
        main_layout.addWidget(self.header_table)
        
    def get_header_values(self):
        """Return the header values from the table."""
        return self.header_table.get_header_values()
    
    def set_from_options(self, from_options):
        """Set options for the 'From' field (e.g., if using a combo box)."""
        # This would be implemented if using a combo box for the From field
        pass
    
    def populate_from_message(self, message):
        """Populate header fields from a message."""
        self.header_table.populate_from_message(message)


# Demo application
if __name__ == "__main__":
    from email.message import EmailMessage
    
    class DummyConfig:
        """Dummy config class for testing."""
        def get_text_font(self):
            return QFont("Arial", 10)
    
    app = QApplication(sys.argv)
    
    # Create a sample message
    msg = EmailMessage()
    msg["Subject"] = "Test Subject"
    msg["From"] = "John Doe <john@example.com>"
    msg["To"] = "Jane Smith <jane@example.com>, Alice <alice@example.com>"
    msg["Cc"] = "Bob <bob@example.com>"
    
    window = QMainWindow()
    window.setWindowTitle("Editable Mail Header Widget Demo")
    window.setGeometry(100, 100, 800, 300)
    
    config = DummyConfig()
    header_widget = MailHeaderEditableWidget(window, config, msg)
    window.setCentralWidget(header_widget)
    
    window.show()
    sys.exit(app.exec())
