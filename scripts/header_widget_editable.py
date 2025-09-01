#!/usr/bin/env python3

import sys
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QScrollArea,
    QTextEdit, QGridLayout, QSizePolicy, QFrame, QHBoxLayout, QComboBox,
    QCompleter
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QTextCursor, QDrag, QTextCharFormat, 
    QTextDocument, QPalette, QKeySequence, QShortcut
)
from PySide6.QtCore import (
    Qt, Signal, QMimeData, QPoint, QSize, QEvent, QRect, QStringListModel
)

# Import the real config instead of using a dummy
from config import config

# Shared comprehensive regex for RFC 5322 email addresses with or without display names
EMAIL_ADDRESS_REGEX = re.compile(r'(?:"[^"]*"|[^,<>"])*?(?:<([^<>]+)>|([^,<>\s]+@[^,<>\s]+))')

def sanitize_email_list(address_text):
    """
    Sanitize a comma-separated list of email addresses.
    
    Fixes issues like multiple commas, extra whitespace, and ensures
    consistent ", " formatting between addresses.
    
    Args:
        address_text (str): The input text containing email addresses
        
    Returns:
        str: Properly formatted list with addresses separated by ", "
    """
    if not address_text:
        return ""
        
    # Step 1: Split the text by commas (this handles multiple commas)
    addresses = address_text.split(',')
    
    # Step 2: Strip whitespace from each address and filter out empty ones
    clean_addresses = [addr.strip() for addr in addresses if addr.strip()]
    
    # Step 3: Join with the standard ", " separator
    return ", ".join(clean_addresses)

class AddressAwareTextEdit(QTextEdit):
    """
    A QTextEdit subclass that is aware of email addresses for drag-and-drop operations,
    and provides autocomplete functionality for email addresses.
    """
    addressDragged = Signal(str)  # Signal emitted when an address is dragged

    def __init__(self, parent=None, read_only=False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameStyle(QFrame.NoFrame)
        self.setTabChangesFocus(True)  # Tab moves to next field
        
        # Set read-only state if requested
        self.setReadOnly(read_only)
        
        # Enable rich text to allow for highlighting, but maintain plain text input
        self.setAcceptRichText(False)
        
        # Adjust minimum height to be single line by default
        self.document().documentLayout().documentSizeChanged.connect(self.adjustHeight)
        
        # Drag support (only needed for editable fields)
        self.drag_start_position = None
        self.drag_address = None
        
        # Apply different background for read-only fields
        if read_only:
            palette = self.palette()
            palette.setColor(QPalette.Base, palette.color(QPalette.Window))
            self.setPalette(palette)
            return  # Skip autocomplete setup for read-only fields
        
        # Set up autocomplete functionality
        self.setup_autocomplete()
        
    def setup_autocomplete(self):
        """Set up autocomplete for email addresses"""
        # Create completer
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.activated.connect(self.insert_completion)
        
        # Get autocomplete options from config
        self.update_autocomplete_model()
        
        # Install event filter to catch key events
        self.installEventFilter(self)
        
        # Flag to track if completer is visible
        self.completer_active = False
        
        # Connect signals
        self.textChanged.connect(self.handle_text_changed)
        
        # Create keyboard shortcut for autocomplete
        self.autocomplete_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.autocomplete_shortcut.activated.connect(self.force_show_completer)
    
    def update_autocomplete_model(self):
        """Update the completer with options from config"""
        # Get autocomplete options from config
        autocomplete_options = config.get_autocompletions()
        
        # Set the model for the completer
        model = QStringListModel(autocomplete_options)
        self.completer.setModel(model)
        
    def force_show_completer(self):
        """Force the completer to show even if current word is short."""
        text_cursor = self.textCursor()
        
        # Find the current word under cursor
        pos = text_cursor.position()
        text_cursor.movePosition(QTextCursor.StartOfWord, QTextCursor.MoveAnchor)
        text_cursor.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
        
        current_word = text_cursor.selectedText().strip()
        
        # Reset cursor position
        text_cursor.setPosition(pos)
        self.setTextCursor(text_cursor)
        
        # Update completer with more lenient criteria
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                     self.completer.popup().verticalScrollBar().sizeHint().width())
        
        if current_word:  # Even if it's just 1 character
            # Filter completions based on current text
            self.completer.setCompletionPrefix(current_word)
        else:
            # If no current word, show all completions
            self.completer.setCompletionPrefix("")
            
        # Show popup if there are completions
        if self.completer.completionCount() > 0:
            self.completer.complete(rect)
            self.completer_active = True
    
    def eventFilter(self, obj, event):
        """Filter events to handle key presses for the completer."""
        if obj is self and event.type() == QEvent.KeyPress:
            key_event = event
            
            # Handle key combinations
            if key_event.modifiers() == Qt.ControlModifier and key_event.key() == Qt.Key_Space:
                # Ctrl+Space - already handled by shortcut
                return False
                
            # If completer popup is visible, handle navigation and selection keys
            if self.completer and self.completer.popup() and self.completer.popup().isVisible():
                # Keys that select the current completion
                if key_event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
                    self.completer.activated.emit(self.completer.currentCompletion())
                    return True
                    
                # Keys for navigation within the popup
                if key_event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                    # Pass these to the popup
                    QApplication.sendEvent(self.completer.popup(), key_event)
                    return True
                    
                # Escape closes the popup
                if key_event.key() == Qt.Key_Escape:
                    self.completer.popup().hide()
                    return True
                    
                # Custom shortcut keys for selecting options
                # Alt+1 through Alt+9 select items 1-9 in the completer
                if key_event.modifiers() == Qt.AltModifier and Qt.Key_1 <= key_event.key() <= Qt.Key_9:
                    index = key_event.key() - Qt.Key_1  # 0-based index
                    if index < self.completer.completionCount():
                        # Get the completion at the specified index
                        model = self.completer.model()
                        completion_index = model.index(index, 0)
                        completion = model.data(completion_index, Qt.DisplayRole)
                        
                        # Insert it
                        self.completer.activated.emit(completion)
                        return True
        
        return super().eventFilter(obj, event)
    
    def handle_text_changed(self):
        """Called when the text content changes."""
        # Update autocomplete suggestions
        if hasattr(self, 'completer'):
            self.update_completer()
        
        # Adjust the height based on content
        self.adjustHeight()
    
    def update_completer(self):
        """Update the completer popup with relevant suggestions."""
        text_cursor = self.textCursor()
        
        # Find the current word under cursor by moving to word boundaries
        pos = text_cursor.position()
        text_cursor.movePosition(QTextCursor.StartOfWord, QTextCursor.MoveAnchor)
        text_cursor.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
        
        current_word = text_cursor.selectedText().strip()
        
        # Only show completer if we have text to complete and it's at least 2 chars
        if current_word and len(current_word) >= 2:
            # Reset cursor position
            text_cursor.setPosition(pos)
            self.setTextCursor(text_cursor)
            
            # Update completer
            rect = self.cursorRect()
            rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                         self.completer.popup().verticalScrollBar().sizeHint().width())
            
            # Filter completions based on current text
            self.completer.setCompletionPrefix(current_word)
            
            # Show popup if there are completions
            if self.completer.completionCount() > 0:
                self.completer.complete(rect)
                self.completer_active = True
            else:
                self.completer.popup().hide()
                self.completer_active = False
        else:
            self.completer.popup().hide()
            self.completer_active = False
    
    def insert_completion(self, completion):
        """Insert the selected completion into the text."""
        if self.completer.widget() != self:
            return
            
        text_cursor = self.textCursor()
        
        # Replace the current word with the completion
        text_cursor.movePosition(QTextCursor.StartOfWord, QTextCursor.MoveAnchor)
        text_cursor.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
        
        # Insert completion and add a comma if not at the end
        text_cursor.insertText(completion)
        
        # Check if we need to add a comma and space
        text_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
        next_char = text_cursor.selectedText()
        
        if not next_char or next_char not in [',', ' ']:
            text_cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.MoveAnchor)
            text_cursor.insertText(", ")
        
        self.setTextCursor(text_cursor)
        self.completer.popup().hide()
        
        # Apply sanitization to ensure consistent formatting
        self.sanitize_email_list()

    def adjustHeight(self):
        """Adjust the height of the widget to fit the content."""
        margins = self.contentsMargins()
        doc_height = self.document().size().height() + margins.top() + margins.bottom() + 4
        self.setMinimumHeight(doc_height)
        self.setMaximumHeight(doc_height)

    def keyPressEvent(self, event):
        """Override keyPressEvent to handle special keys."""
        # If Tab key pressed and completer is visible, use it for completion
        if hasattr(self, 'completer') and event.key() == Qt.Key_Tab and self.completer_active:
            if self.completer.popup().isVisible():
                self.completer.activated.emit(self.completer.currentCompletion())
                event.accept()
                return
                
        # Handle keyboard shortcuts for selecting completions
        if hasattr(self, 'completer') and event.modifiers() == Qt.AltModifier and Qt.Key_1 <= event.key() <= Qt.Key_9:
            # This is handled in the event filter
            return
            
        super().keyPressEvent(event)
    
    def sanitize_email_list(self):
        """Clean up the email list formatting."""
        # Get current text
        current_text = self.toPlainText()
        
        # Sanitize it
        clean_text = sanitize_email_list(current_text)
        
        # Only update if it actually changed
        if clean_text != current_text:
            # Preserve cursor position
            cursor = self.textCursor()
            rel_pos = cursor.position() / max(1, len(current_text))
            
            # Update text
            self.setPlainText(clean_text)
            
            # Restore cursor to approximately the same relative position
            new_pos = min(int(rel_pos * len(clean_text)), len(clean_text))
            cursor.setPosition(new_pos)
            self.setTextCursor(cursor)

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
                cursor_pos = cursor.position()
                
                # Check if the cursor is within an existing email address
                text = self.toPlainText()
                inside_address = False
                
                for match in EMAIL_ADDRESS_REGEX.finditer(text):
                    start, end = match.span()
                    if start < cursor_pos < end:  # Cursor is inside an address
                        inside_address = True
                        # Determine whether to move cursor before or after the address
                        if cursor_pos - start < end - cursor_pos:  # Closer to start
                            cursor.setPosition(start)
                        else:  # Closer to end
                            cursor.setPosition(end)
                        break
                
                # Update cursor position after potential adjustment
                self.setTextCursor(cursor)
                cursor_pos = cursor.position()
                
                # Now let's handle comma insertion
                current_text = self.toPlainText()
                
                if not current_text:
                    # Empty field, just insert the text
                    comma_handled_text = dropped_text
                else:
                    # Handle based on position
                    if cursor_pos == 0:
                        # At the beginning
                        comma_handled_text = dropped_text + ", "
                    elif cursor_pos == len(current_text):
                        # At the end
                        comma_handled_text = ", " + dropped_text
                    else:
                        # In the middle
                        comma_handled_text = ", " + dropped_text + ", "
                
                # Insert the text
                cursor.insertText(comma_handled_text)
                
                # Apply the sanitization to the entire field
                self.sanitize_email_list()
                
                # Ensure the inserted text is visible
                self.ensureCursorVisible()
                
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
        self.layout.setContentsMargins( 0, 0, 0, 0 )
        self.layout.setSpacing(8)
        
        # Configure fonts
        self.label_font = self.config.get_text_font()
        self.label_font.setBold(True)
        self.text_font = self.config.get_text_font()
        
        # Define and create header fields
        self.header_fields = [
            ("From:", "from_edit", "combo"),  # Special case for "From:" - use combo box
            ("To:", "to_edit", "text"),
            ("Cc:", "cc_edit", "text"),
            ("Bcc:", "bcc_edit", "text"),
            ("Reply-To:", "reply_to_edit", "text"),
            ("Subject:", "subject_edit", "text")
        ]
        
        # Track which fields should be shown in "more headers"
        self.more_headers_fields = ["bcc_edit", "reply_to_edit"]
        self.more_headers_visible = False
        
        self.create_header_fields()
        
        # Populate with message data if provided
        if message:
            self.populate_from_message(message)
            
        # Store message_id for the host application to use
        self.message_id_loc = None
        if message and message.get('Message-ID'):
            self.message_id_loc, _ = message.get('Message-ID').split('@', 1)

    def _getWidthBold(self, text):
        doc = QTextDocument()
        bold_font = self.config.get_text_font()
        bold_font.setBold(True)
        doc.setDefaultFont(bold_font)
        doc.setPlainText(f"{text} ")
        return doc.idealWidth()

    def create_header_fields(self):
        """Create all header field labels and editors."""
        self.editors = {}  # Store references to editor widgets
        self.labels = {}   # Store references to label widgets
        
        for row, (label_text, editor_name, editor_type) in enumerate(self.header_fields):
            # Create label
            label_widget = AddressAwareTextEdit(read_only=True)
            label_widget.setFont(self.label_font)
            label_widget.setPlainText(label_text)
            
            # Critical: Set document margin to 0 to force text to the top
            label_widget.document().setDocumentMargin(0)
            
            # Set right alignment for the label text
            option = label_widget.document().defaultTextOption()
            option.setAlignment(Qt.AlignLeft)
            label_widget.document().setDefaultTextOption(option)
            
            # Fixed width and size policy for label
            label_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            label_widget.setFixedWidth( self._getWidthBold( "Reply-To:" ) )  # Set a fixed width for all labels
            
            # Store reference to the label
            self.labels[editor_name + "_label"] = label_widget
            
            # Add to layout WITH EXPLICIT ALIGNMENT FLAG
            self.layout.addWidget(label_widget, row, 0, Qt.AlignTop)
            
            # Create editor based on type
            if editor_type == "combo":
                # Create combo box for "From:" field
                editor = QComboBox()
                editor.setFont(self.text_font)
                editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                # Make it tall enough to match other fields visually
                editor.setMinimumHeight(30)
            else:
                # Create text editor for other fields
                editor = AddressAwareTextEdit()
                editor.setFont(self.text_font)
                editor.setProperty("headerField", True)  # For styling
                
                # Critical: Set document margin to 0 to force text to the top
                editor.document().setDocumentMargin(0)
                
                # Connect drag-and-drop signals (only for text editors)
                editor.addressDragged.connect(self.handle_address_dragged)
            
            # Store reference to the editor
            self.editors[editor_name] = editor
            
            # Set initial visibility based on more_headers setting
            if editor_name in self.more_headers_fields:
                editor.setVisible(self.more_headers_visible)
                label_widget.setVisible(self.more_headers_visible)
            
            # Add to layout WITH EXPLICIT ALIGNMENT FLAG
            self.layout.addWidget(editor, row, 1, Qt.AlignTop)
        
        # Add a spacer at the bottom to push everything up
        self.layout.setRowStretch(len(self.header_fields), 1)

    def toggle_more_headers(self):
        """Toggle the visibility of additional header fields."""
        self.more_headers_visible = not self.more_headers_visible
        
        for field_name in self.more_headers_fields:
            if field_name in self.editors:
                self.editors[field_name].setVisible(self.more_headers_visible)
                self.labels[field_name + "_label"].setVisible(self.more_headers_visible)
        
        return self.more_headers_visible

    def set_from_options(self, from_options, current_value=None):
        """Configure the From field with options from a dropdown."""
        if "from_edit" in self.editors and isinstance(self.editors["from_edit"], QComboBox):
            combo = self.editors["from_edit"]
            combo.clear()
            
            for display_text, email_value in from_options:
                combo.addItem(display_text, email_value)
            
            # Set current value if provided
            if current_value:
                for i in range(combo.count()):
                    if combo.itemText(i) == current_value or combo.itemData(i) == current_value:
                        combo.setCurrentIndex(i)
                        break

    def populate_from_message(self, message):
        """Populate the header fields from an email message."""
        # Handle the From field specially
        from_header = message.get("From", "")
        if from_header and "from_edit" in self.editors:
            if isinstance(self.editors["from_edit"], QComboBox):
                # For combo box, we'll set it through set_from_options later
                self.current_from_value = from_header
            else:
                self.editors["from_edit"].setPlainText(from_header)
        
        # Map message headers to editor fields
        header_mapping = {
            "to_edit": message.get("To", ""),
            "cc_edit": message.get("Cc", ""),
            "bcc_edit": message.get("Bcc", ""),
            "reply_to_edit": message.get("Reply-To", ""),
            "subject_edit": message.get("Subject", "")
        }
        
        # Set text for each editor
        for editor_name, value in header_mapping.items():
            if editor_name in self.editors:
                if isinstance(self.editors[editor_name], AddressAwareTextEdit):
                    self.editors[editor_name].setPlainText(value)
                elif isinstance(self.editors[editor_name], QComboBox):
                    # This should be handled by set_from_options
                    pass
                    
        # Show more headers if they have content
        if message.get("Bcc") or message.get("Reply-To"):
            self.more_headers_visible = True
            self.toggle_more_headers()
            
        # Extract message ID
        message_id = message.get('Message-ID', '')
        if message_id:
            try:
                self.message_id_loc, _ = message_id.split('@', 1)
            except ValueError:
                self.message_id_loc = None

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
                editor = self.editors[editor_name]
                
                if isinstance(editor, AddressAwareTextEdit):
                    value = editor.toPlainText().strip()
                elif isinstance(editor, QComboBox):
                    value = editor.currentText().strip()
                else:
                    value = ""
                    
                if value:  # Only include non-empty headers
                    headers[header_name] = value
        
        return headers

    def handle_address_dragged(self, address):
        """Handles notification that an address was dragged from one field to another."""
        # This can be used for additional processing if needed
        pass


# Demo application
if __name__ == "__main__":
    from email.message import EmailMessage
    
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
