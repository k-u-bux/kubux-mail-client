#!/usr/bin/env python3

import sys
import argparse
import os
import email
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from email import policy
from pathlib import Path
import tempfile
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QSplitter, QMessageBox, QDialog,
    QFormLayout, QLabel, QFileDialog, QSizePolicy, QMenu, QComboBox,
    QDialogButtonBox, QGroupBox
)
from PySide6.QtCore import Qt, QSize, QUrl, QMimeData
from PySide6.QtGui import QFont, QAction, QKeySequence, QDrag
import logging
import mimetypes
import subprocess
import email.utils
from config import config

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Custom Widgets ---

class CopyableErrorDialog(QDialog):
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("The following error occurred:")
        layout.addWidget(label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(message)
        layout.addWidget(self.text_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

class EmailAddressLineEdit(QLineEdit):
    """
    A QLineEdit subclass that handles email addresses as draggable units.
    It supports moving a full email address from one field to another.
    """
    # Regex to find an email address with or without a name
    ADDRESS_REGEX = re.compile(r'[^,<>]+<[^,<>]+>|[^,<>]+@\S+')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        # Initialize drag-related attributes to prevent AttributeError
        self.dragged_address = None
        self.dragged_start = -1
        self.dragged_end = -1

    def mousePressEvent(self, event):
        """Starts a drag operation if a full address is clicked."""
        if event.button() == Qt.MouseButton.LeftButton:
            text = self.text()
            cursor_pos = self.cursorPosition()
            
            # Find the address under the cursor
            for match in self.ADDRESS_REGEX.finditer(text):
                if match.start() <= cursor_pos <= match.end():
                    self.dragged_address = match.group().strip()
                    self.dragged_start = match.start()
                    self.dragged_end = match.end()
                    break
            else:
                self.dragged_address = None
                self.dragged_start = -1
                self.dragged_end = -1
                
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Executes the drag if a valid address was clicked and the mouse moved."""
        if self.dragged_address and (event.buttons() & Qt.MouseButton.LeftButton):
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.dragged_address)
            drag.setMimeData(mime_data)
            
            # Start the drag and get the final drop action
            drop_action = drag.exec(Qt.MoveAction)
            
            # If the drop was a move action, remove the address from this field
            if drop_action == Qt.MoveAction:
                current_text = self.text()
                # Remove the address and any surrounding comma/whitespace
                new_text = (current_text[:self.dragged_start].rstrip(' ,') + 
                            current_text[self.dragged_end:].lstrip(' ,'))
                
                # Clean up multiple spaces or commas
                new_text = re.sub(r', *', ', ', new_text)
                new_text = new_text.strip(' ,')
                
                self.setText(new_text)
                self.dragged_address = None
                
        super().mouseMoveEvent(event)

    def dropEvent(self, event):
        """Handles dropping an address into this field."""
        if event.mimeData().hasText():
            dropped_text = event.mimeData().text()
            if self.ADDRESS_REGEX.fullmatch(dropped_text.strip()):
                # It's a valid email address, insert it
                current_text = self.text()
                if current_text and not current_text.endswith(','):
                    self.setText(current_text + ', ' + dropped_text)
                else:
                    self.setText(current_text + dropped_text)
                
                # Accept the event as a move action to signal the source to clear
                event.acceptProposedAction()
                event.setDropAction(Qt.MoveAction)
                return

        super().dropEvent(event)

# --- Mail Editor Main Class ---

class MailEditor(QMainWindow):
    def __init__(self, parent=None, mail_file_path=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Composer")
        self.setMinimumSize(QSize(800, 600))
        
        self.attachments = []
        self.mail_file_path = Path(mail_file_path).expanduser() if mail_file_path else None
        self.draft_message = self.parse_draft_mail(self.mail_file_path) if self.mail_file_path else None
        
        if self.draft_message is None and self.mail_file_path and self.mail_file_path.exists():
            self.close()
            return
            
        self.setup_ui()
        self.setup_key_bindings()
        self.populate_from_draft()

    def parse_draft_mail(self, mail_file_path):
        """Parses an email file to get headers and content for drafting."""
        if not mail_file_path or not mail_file_path.exists():
            return None
        
        try:
            with open(mail_file_path, 'rb') as f:
                return email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            logging.error(f"Failed to parse draft mail file: {e}")
            dialog = CopyableErrorDialog("Parsing Error", f"Failed to parse draft mail file:\n{e}")
            dialog.exec()
            return None

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        main_layout.addWidget(top_bar)

        self.add_attachment_button = QPushButton("Attachments")
        self.add_attachment_button.clicked.connect(self.add_attachment)
        top_bar_layout.addWidget(self.add_attachment_button)
        
        self.more_headers_button = QPushButton("More Headers")
        self.more_headers_button.clicked.connect(self.toggle_more_headers)
        top_bar_layout.addWidget(self.more_headers_button)

        top_bar_layout.addStretch()

        self.send_button = QPushButton("Send")
        self.save_button = QPushButton("Save")
        self.discard_button = QPushButton("Discard")
        
        self.send_button.clicked.connect(self.send_message)
        self.save_button.clicked.connect(self.save_message)
        self.discard_button.clicked.connect(self.discard_draft)
        
        top_bar_layout.addWidget(self.send_button)
        top_bar_layout.addWidget(self.save_button)
        top_bar_layout.addWidget(self.discard_button)

        headers_group_box = QWidget()
        self.headers_layout = QFormLayout(headers_group_box)
        
        self.from_combo = QComboBox()
        self.populate_from_field()
        
        # Use our new custom widget for the address fields
        self.to_edit = EmailAddressLineEdit()
        self.cc_edit = EmailAddressLineEdit()
        self.subject_edit = QLineEdit()
        
        self.headers_layout.addRow("From:", self.from_combo)
        self.headers_layout.addRow("To:", self.to_edit)
        self.headers_layout.addRow("Cc:", self.cc_edit)
        self.headers_layout.addRow("Subject:", self.subject_edit)

        self.more_headers_group = QGroupBox()
        self.more_headers_layout = QFormLayout(self.more_headers_group)
        
        # Use the custom widget for Bcc as well
        self.bcc_edit = EmailAddressLineEdit()
        self.reply_to_edit = QLineEdit()
        
        self.more_headers_layout.addRow("Bcc:", self.bcc_edit)
        self.more_headers_layout.addRow("Reply-To:", self.reply_to_edit)
        self.more_headers_group.setVisible(False)
        
        main_layout.addWidget(headers_group_box)
        main_layout.addWidget(self.more_headers_group)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)

        self.body_edit = QTextEdit()
        self.body_edit.setFont(config.text_font)
        self.splitter.addWidget(self.body_edit)

        attachments_group = QWidget()
        attachments_layout = QVBoxLayout(attachments_group)
        attachments_layout.setContentsMargins(0, 0, 0, 0)
        
        self.attachments_list = QListWidget()
        self.attachments_list.setMaximumHeight(80)
        self.attachments_list.setAcceptDrops(True)
        self.attachments_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.attachments_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attachments_list.customContextMenuRequested.connect(self.show_attachment_context_menu)
        
        attachments_layout.addWidget(self.attachments_list)
        
        self.splitter.addWidget(attachments_group)
        self.splitter.setSizes([400, 100])

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        
        self.attachments_list.dragEnterEvent = self.dragEnterEvent
        self.attachments_list.dragMoveEvent = self.dragMoveEvent
        self.attachments_list.dropEvent = self.dropEvent

    def setup_key_bindings(self):
        actions = {
            "undo": self.body_edit.undo,
            "redo": self.body_edit.redo,
            "cut": self.body_edit.cut,
            "copy": self.body_edit.copy,
            "paste": self.body_edit.paste,
            "select_all": self.body_edit.selectAll,
            "zoom_in": lambda: self.body_edit.zoomIn(1),
            "zoom_out": lambda: self.body_edit.zoomOut(1),
        }

        for name, func in actions.items():
            key_seq = config.get_keybinding(name)
            if key_seq:
                action = QAction(self)
                action.setShortcut(QKeySequence(key_seq))
                action.triggered.connect(func)
                self.addAction(action)

        discard_key_seq = config.get_keybinding("quit_action")
        if discard_key_seq:
            discard_action = QAction("Discard", self)
            discard_action.setShortcut(QKeySequence(discard_key_seq))
            discard_action.triggered.connect(self.discard_draft)
            self.addAction(discard_action)
            
    def populate_from_draft(self, draft_message=None):
        if not draft_message and not self.draft_message:
            return

        message = draft_message or self.draft_message

        self.to_edit.setText(message.get('To', ''))
        self.cc_edit.setText(message.get('Cc', ''))
        self.subject_edit.setText(message.get('Subject', ''))
        
        bcc = message.get('Bcc', '')
        reply_to = message.get('Reply-To', '')
        if bcc or reply_to:
            self.bcc_edit.setText(bcc)
            self.reply_to_edit.setText(reply_to)
            self.toggle_more_headers()

        plain_text_body = ""
        for part in message.walk():
            if part.get_content_type() == 'text/plain':
                plain_text_body = part.get_content()
                break
        self.body_edit.setPlainText(plain_text_body)

        for part in message.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename:
                    self.attachments_list.addItem(filename)

    def populate_from_field(self):
        identities = config.get_setting("email_identities", "identities", [])
        for identity in identities:
            if isinstance(identity, dict) and "name" in identity and "email" in identity:
                display_text = f"{identity['name']} <{identity['email']}>"
                self.from_combo.addItem(display_text, identity['email'])
            elif isinstance(identity, str):
                self.from_combo.addItem(identity, identity)

    def toggle_more_headers(self):
        is_visible = self.more_headers_group.isVisible()
        self.more_headers_group.setVisible(not is_visible)
        self.more_headers_button.setText("Less Headers" if not is_visible else "More Headers")
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                self.add_attachment(file_path)
        event.acceptProposedAction()

    def show_attachment_context_menu(self, pos):
        item = self.attachments_list.itemAt(pos)
        if item:
            menu = QMenu(self)
            remove_action = QAction("Remove", self)
            remove_action.triggered.connect(lambda: self.remove_attachment(item))
            menu.addAction(remove_action)
            menu.exec(self.attachments_list.mapToGlobal(pos))

    def add_attachment(self, file_path=None):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(self, "Add Attachment")
            if not file_path:
                return

        file_path = Path(file_path)
        try:
            mimetype, _ = mimetypes.guess_type(file_path)
            if mimetype is None:
                mimetype = 'application/octet-s'
            maintype, subtype = mimetype.split('/')
            
            with open(file_path, 'rb') as f:
                part = email.message.EmailMessage()
                part.set_content(f.read(), maintype=maintype, subtype=subtype)
                part.add_header('Content-Disposition', 'attachment', filename=file_path.name)
                self.attachments.append(part)
                self.attachments_list.addItem(file_path.name)
        except Exception as e:
            dialog = CopyableErrorDialog("Failed to Add Attachment", f"Failed to add attachment:\n{e}")
            dialog.exec()

    def remove_attachment(self, item):
        row = self.attachments_list.row(item)
        if 0 <= row < len(self.attachments):
            del self.attachments[row]
            self.attachments_list.takeItem(row)

    def _create_draft_file(self):
        try:
            draft = email.message.EmailMessage()
            
            if self.draft_message:
                in_reply_to = self.draft_message.get('In-Reply-To')
                if in_reply_to:
                    draft['In-Reply-To'] = in_reply_to
                references = self.draft_message.get('References')
                if references:
                    draft['References'] = references

            from_address = email.utils.parseaddr(self.from_combo.currentText())[1]
            domain = from_address.split('@')[1] if '@' in from_address else 'local.machine'
            draft['Message-ID'] = email.utils.make_msgid(domain=domain)
            
            draft['From'] = self.from_combo.currentText()
            if self.to_edit.text():
                draft['To'] = self.to_edit.text()
            if self.cc_edit.text():
                draft['Cc'] = self.cc_edit.text()
            if self.bcc_edit.text():
                draft['Bcc'] = self.bcc_edit.text()
            if self.reply_to_edit.text():
                draft['Reply-To'] = self.reply_to_edit.text()
            if self.subject_edit.text():
                draft['Subject'] = self.subject_edit.text()

            draft.set_content(self.body_edit.toPlainText())

            for part in self.attachments:
                draft.attach(part)
            
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, dir=self.mail_file_path.parent) as tmp_file:
                tmp_file.write(draft.as_bytes())
                tmp_path = Path(tmp_file.name)
            
            if self.mail_file_path:
                tmp_path.rename(self.mail_file_path)
                return self.mail_file_path
            else:
                return tmp_path

        except Exception as e:
            dialog = CopyableErrorDialog("Draft Creation Error", f"Failed to create draft file:\n{e}")
            dialog.exec()
            return None

    def save_message(self):
        if self._create_draft_file():
            self.close()

    def send_message(self):
        draft_path = self._create_draft_file()
        if not draft_path:
            return

        try:
            send_mail_path = Path(__file__).parent / "send-mail.py"
            if not send_mail_path.exists():
                QMessageBox.critical(self, "Error", f"Could not find send mail script at {send_mail_path}")
                return

            subprocess.Popen([sys.executable, str(send_mail_path), str(draft_path)])
            self.close()

        except Exception as e:
            QMessageBox.critical(self, "Send Error", f"Failed to send mail: {e}")

    def discard_draft(self):
        if self.mail_file_path and self.mail_file_path.exists():
            try:
                os.remove(self.mail_file_path)
            except Exception as e:
                logging.error(f"Failed to delete draft file: {e}")
                dialog = CopyableErrorDialog("Discard Error", f"Failed to delete draft file:\n{e}")
                dialog.exec()
                return
        
        self.close()

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Edit a pre-drafted email.")
    parser.add_argument("--mail-file", required=True, help="The full path to the mail file containing the pre-drafted email.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    editor = MailEditor(mail_file_path=args.mail_file)
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
