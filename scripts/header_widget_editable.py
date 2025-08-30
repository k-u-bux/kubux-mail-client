#!/usr/bin/env python3

import sys
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QScrollArea,
    QTextEdit, QGridLayout, QSizePolicy, QFrame, QHBoxLayout,
    QPlainTextEdit, QLabel
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QTextCursor, QDrag, QTextCharFormat, 
    QTextDocument, QPalette, QTextOption
)
from PySide6.QtCore import (
    Qt, Signal, QMimeData, QPoint, QSize, QEvent, QRect, QMargins
)

# Import the real config
from config import config

# Shared comprehensive regex for RFC 5322 email addresses with or without display names
EMAIL_ADDRESS_REGEX = re.compile(r'(?:"[^"]*"|[^,<>"])*?(?:<([^<>]+)>|([^,<>\s]+@[^,<>\s]+))')


class TopAlignedTextEdit(QTextEdit):
    """
    A QTextEdit subclass that ensures text is always aligned at the top
    and automatically adjusts its height to fit content.
    """
    addressDragged = Signal(str)  # Signal emitted when an address is dragged
    heightChanged = Signal(int)   # Signal emitted when height changes

    def __init__(self, parent=None, read_only=False):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameStyle(QFrame.NoFrame)
        self.setTabChangesFocus(True)  # Tab moves to next field
        
        # Set read-only state if requested
        self.setReadOnly(read_only)
        
        # Force text to top by setting minimal document margin
        self.document().setDocumentMargin(0)
        
        # Connect to document change events to update height
        self.document().contentsChanged.connect(self.adjustHeight)
        
        # Drag support
        self.drag_start_position = None
        self.drag_address = None
        
        # Apply different background for read-only fields
        if read_only:
            palette = self.palette()
            palette.setColor(QPalette.Base, palette.color(QPalette.Window))
            self.setPalette(palette)
            
            # For right-aligned text in labels
            document = self.document()
            option = document.defaultTextOption()
            option.setAlignment(Qt.AlignRight)
            document.setDefaultTextOption(option)
        
        # Initial height adjustment
        QApplication.instance().processEvents()
        self.adjustHeight()

    def sizeHint(self):
        """Override sizeHint to provide height based on content."""
        size = super().sizeHint()
        doc_size = self.document().size().toSize()
        size.setHeight(doc_size.height() + 10)  # Add some padding
        return size

    def adjustHeight(self):
        """Adjust the height of the widget to fit the content."""
        # Get document size plus margins
        doc_size = self.document().size().toSize()
        margins = self.contentsMargins()
        total_height = doc_size.height() + margins.top() + margins.bottom() + 4
        
        # Ensure minimum height is enough for at least one line
        font_metrics = self.fontMetrics()
        min_height = font_metrics.height() + margins.top() + margins.bottom() + 4
        
        # Use maximum between minimum height and content height
        new_height = max(min_height, total_height)
        
        # Set a reasonable maximum height to prevent excessive growth
        max_height = 150  # Maximum height for multi-line content
        new_height = min(new_height, max_height)
        
        # Only update if height changed
        if self.height() != new_height:
            self.setMinimumHeight(new_height)
            self.heightChanged.emit(new_height)

    def mousePressEvent(self, event):
        """Handle mouse press events for potential drag operations."""
        if self.isReadOnly():
            # Skip drag setup for read-only fields
            super().mousePressEvent(event)
            return
            
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
            
            # Check if cursor is within an email address
            cursor = self.cursorForPosition(event.pos())
            cursor_pos = cursor.position()
            
            # Only set up for potential drag if no text is already selected
            if not self.textCursor().hasSelection():
                text = self.toPlainText()
                for match in EMAIL_ADDRESS_REGEX.finditer(text):
                    start, end = match.span()
                    if start <= cursor_pos <= end:
                        # Select the email address
                        cursor.setPosition(start)
                        cursor.setPosition(end, QTextCursor.KeepAnchor)
                        self.setTextCursor(cursor)
                        self.drag_address = match.group()
                        break
            
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move events to initiate drag operations."""
        if self.isReadOnly():
            # Skip drag operations for read-only fields
            super().mouseMoveEvent(event)
            return
            
        if not self.drag_start_position or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
            
        # Check if the mouse has moved far enough to start a drag
        if ((event.pos() - self.drag_start_position).manhattanLength() 
                < QApplication.startDragDistance()):
            super().mouseMoveEvent(event)
            return
            
        # Get the currently selected text
        selected_text = self.textCursor().selectedText()
        if not selected_text:
            super().mouseMoveEvent(event)
            return
            
        # Verify it's an email address
        if not EMAIL_ADDRESS_REGEX.fullmatch(selected_text):
            super().mouseMoveEvent(event)
            return
            
        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(selected_text)
        drag.setMimeData(mime_data)
        
        # Execute the drag and emit signal if successful
        result = drag.exec(Qt.CopyAction | Qt.MoveAction)
        if result == Qt.MoveAction:
            # The address will be removed by the dropEvent of the target
            self.addressDragged.emit(selected_text)
            
            # Remove the text from this field if it was a move
            cursor = self.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()
                
                # Clean up any orphaned commas
                text = self.toPlainText()
                clean_text = re.sub(r'\s*,\s*,\s*', ', ', text)
                clean_text = re.sub(r'^\s*,\s*|\s*,\s*$', '', clean_text)
                if clean_text != text:
                    self.setText(clean_text)
        
        # Reset drag state
        self.drag_start_position = None
        self.drag_address = None

    def dropEvent(self, event):
        """Handle drop events for email addresses."""
        if self.isReadOnly():
            # Skip drop handling for read-only fields
            event.ignore()
            return
            
        if event.mimeData().hasText():
            dropped_text = event.mimeData().text().strip()
            
            # If it's an email address
            if EMAIL_ADDRESS_REGEX.fullmatch(dropped_text):
                cursor = self.cursorForPosition(event.pos())
                self.setTextCursor(cursor)
                
                # Insert the text at cursor position with proper comma formatting
                current_text = self.toPlainText()
                cursor_pos = cursor.position()
                
                if current_text:
                    # Check if we need to add a comma before or after
                    if cursor_pos == 0:
                        # At start of text
                        if not current_text.startswith(', '):
                            dropped_text = dropped_text + ', '
                    elif cursor_pos == len(current_text):
                        # At end of text
                        if not current_text.endswith(', '):
                            dropped_text = ', ' + dropped_text
                    else:
                        # In the middle - check surrounding characters
                        if not (current_text[cursor_pos-1:cursor_pos] == ',' or 
                                current_text[cursor_pos:cursor_pos+1] == ','):
                            dropped_text = ', ' + dropped_text + ', '
                
                cursor.insertText(dropped_text)
                event.accept()
                event.setDropAction(Qt.MoveAction)
                return
                
        super().dropEvent(event)


class MailHeaderEditableWidget(QScrollArea):
    """
    A scrollable widget containing editable email header fields.
    Each field behaves like a mini text editor similar to the body editor.
    """
    def __init__(self, parent, config, message=None):
        super().__init__(parent)
        self.config = config
        self.message = message
        
        # Setup scroll area
        self.setWidgetResizable(True)
        self.setFrameStyle(QFrame.StyledPanel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Container widget
        container = QWidget()
        self.setWidget(container)
        
        # Main layout
        self.layout = QGridLayout(container)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        
        # Configure fonts
        self.label_font = self.config.get_text_font()
        self.label_font.setBold(True)
        self.text_font = self.config.get_text_font()
        
        # Define and create header fields
        self.header_fields = [
            ("From:", "from_edit"),
            ("To:", "to_edit"),
            ("Cc:", "cc_edit"),
            ("Bcc:", "bcc_edit"),
            ("Reply-To:", "reply_to_edit"),
            ("Subject:", "subject_edit")
        ]
        
        self.create_header_fields()
        
        # Populate with message data if provided
        if message:
            self.populate_from_message(message)

    def create_header_fields(self):
        """Create all header field labels and editors."""
        self.editors = {}  # Store references to editor widgets
        self.labels = {}   # Store references to label widgets
        
        for row, (label_text, editor_name) in enumerate(self.header_fields):
            # Create label using the same widget class but read-only
            label_widget = TopAlignedTextEdit(read_only=True)
            label_widget.setFont(self.label_font)
            label_widget.setPlainText(label_text)
            label_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
            label_widget.setFixedWidth(80)  # Set a fixed width for all labels
            label_widget.setContentsMargins(0, 0, 5, 0)  # Add right margin for spacing
            
            # Store reference to the label
            self.labels[editor_name + "_label"] = label_widget
            
            # Add to layout - align to top
            self.layout.addWidget(label_widget, row, 0, Qt.AlignTop)
            
            # Create editor
            editor = TopAlignedTextEdit()
            editor.setFont(self.text_font)
            editor.setProperty("headerField", True)  # For styling
            editor.setContentsMargins(5, 0, 0, 0)  # Add left margin for spacing
            editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            
            # Connect height changes to ensure labels stay aligned
            editor.heightChanged.connect(lambda h, lbl=label_widget: self.sync_label_height(lbl, h))
            
            # Store reference to the editor
            self.editors[editor_name] = editor
            
            # Add to layout - align to top
            self.layout.addWidget(editor, row, 1, Qt.AlignTop)
            
            # Connect signals for drag-and-drop coordination
            editor.addressDragged.connect(self.handle_address_dragged)
        
        # Add a spacer at the bottom to push everything up
        self.layout.setRowStretch(len(self.header_fields), 1)

    def sync_label_height(self, label_widget, height):
        """Keep label height in sync with editor height for alignment."""
        # This is optional but can help with alignment in some cases
        pass

    def handle_address_dragged(self, address):
        """Handles notification that an address was dragged from one field to another."""
        # This can be used for additional processing if needed
        pass

    def populate_from_message(self, message):
        """Populate the header fields from an email message."""
        # Map message headers to editor fields
        header_mapping = {
            "from_edit": message.get("From", ""),
            "to_edit": message.get("To", ""),
            "cc_edit": message.get("Cc", ""),
            "bcc_edit": message.get("Bcc", ""),
            "reply_to_edit": message.get("Reply-To", ""),
            "subject_edit": message.get("Subject", "")
        }
        
        # Set text for each editor
        for editor_name, value in header_mapping.items():
            if editor_name in self.editors and value:
                self.editors[editor_name].setPlainText(value)

    def get_header_values(self):
        """Return a dictionary of header field values."""
        headers = {}
        
        # Map editor names to header field names
        field_mapping = {
            "from_edit": "From",
            "to_edit": "To",
            "cc_edit": "Cc",
            "bcc_edit": "Bcc",
            "reply_to_edit": "Reply-To",
            "subject_edit": "Subject"
        }
        
        # Get values from each editor
        for editor_name, header_name in field_mapping.items():
            if editor_name in self.editors:
                value = self.editors[editor_name].toPlainText().strip()
                if value:  # Only include non-empty headers
                    headers[header_name] = value
        
        return headers
    
    def set_from_options(self, from_options, current_value=None):
        """Configure the From field with options from a dropdown."""
        # If implementing a combo box for From, this would be modified
        if "from_edit" in self.editors and current_value:
            self.editors["from_edit"].setPlainText(current_value)


# Demo application
if __name__ == "__main__":
    from email.message import EmailMessage
    
    app = QApplication(sys.argv)
    
    # Create a sample message with very long content
    msg = EmailMessage()
    msg["Subject"] = "Test Subject"
    msg["From"] = "John Doe <john@example.com>"
    msg["To"] = "Jane Smith <jane@example.com>, Alice <alice@example.com>, Bob <bob@example.com>, Charlie <charlie@example.com>, David <david@example.com>, Eve <eve@example.com>, Frank <frank@example.com>, Grace <grace@example.com>, Heidi <heidi@example.com>, Ivan <ivan@example.com>, Julia <julia@example.com>, Karl <karl@example.com>, Linda <linda@example.com>"
    msg["Cc"] = "Bob <bob@example.com>, Alice <alice@example.com>, Charlie <charlie@example.com>, David <david@example.com>"
    
    window = QMainWindow()
    window.setWindowTitle("Editable Mail Header Widget Demo")
    window.setGeometry(100, 100, 800, 600)
    
    # Create layout with header widget and a body text area
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)
    
    # Add the header widget
    header_widget = MailHeaderEditableWidget(central_widget, config, msg)
    layout.addWidget(header_widget)
    
    # Add a body text edit for comparison
    body_edit = QTextEdit()
    body_edit.setFont(config.get_text_font())
    body_edit.setPlainText("This is the body of the email. You can type here just like in the header fields above.")
    layout.addWidget(body_edit)
    
    # Set layout stretch to give more space to the body
    layout.setStretchFactor(header_widget, 0)
    layout.setStretchFactor(body_edit, 1)
    
    window.setCentralWidget(central_widget)
    window.show()
    sys.exit(app.exec())
