#!/usr/bin/env python3

import sys
import argparse
import os
import email
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from email import policy
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QSplitter, QMessageBox, QDialog,
    QFormLayout, QLabel, QFileDialog, QSizePolicy, QMenu, QComboBox,
    QDialogButtonBox, QGroupBox
)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QFont, QAction, QKeySequence
import logging
import mimetypes
from config import config

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Custom dialog for displaying copyable error messages
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

class MailEditor(QMainWindow):
    def __init__(self, parent=None, action=None, mail_file_path=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Composer")
        self.setMinimumSize(QSize(800, 600))
        
        self.attachments = []
        self.draft_action = action
        self.original_message = self.parse_original_mail(mail_file_path) if mail_file_path else None
        
        if self.original_message is None and mail_file_path:
            self.close()
            return
            
        self.setup_ui()
        self.draft_message()

    def parse_original_mail(self, mail_file_path):
        """Parses an email file to get headers and content for drafting."""
        mail_path = Path(mail_file_path).expanduser()
        if not mail_path.exists():
            dialog = CopyableErrorDialog("Original Mail File Not Found", f"Original mail file not found: {mail_path}")
            dialog.exec()
            return None
        
        try:
            with open(mail_path, 'rb') as f:
                return email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            logging.error(f"Failed to parse original mail file: {e}")
            dialog = CopyableErrorDialog("Parsing Error", f"Failed to parse original mail file:\n{e}")
            dialog.exec()
            return None

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top section for action buttons and attachments
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        main_layout.addWidget(top_bar)

        # Attachments button (left)
        self.add_attachment_button = QPushButton("Attachments")
        self.add_attachment_button.clicked.connect(self.add_attachment)
        top_bar_layout.addWidget(self.add_attachment_button)
        
        # More Headers button
        self.more_headers_button = QPushButton("More Headers")
        self.more_headers_button.clicked.connect(self.toggle_more_headers)
        top_bar_layout.addWidget(self.more_headers_button)

        top_bar_layout.addStretch()

        # Control buttons (right)
        self.send_button = QPushButton("Send")
        self.save_button = QPushButton("Save Draft")
        self.cancel_button = QPushButton("Cancel")
        
        self.send_button.clicked.connect(self.send_message)
        self.save_button.clicked.connect(self.save_message)
        self.cancel_button.clicked.connect(self.cancel)
        
        top_bar_layout.addWidget(self.send_button)
        top_bar_layout.addWidget(self.save_button)
        top_bar_layout.addWidget(self.cancel_button)

        # Header fields
        headers_group_box = QWidget()
        self.headers_layout = QFormLayout(headers_group_box)
        
        self.from_combo = QComboBox()
        self.populate_from_field()
        self.to_edit = QLineEdit()
        self.cc_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        
        self.headers_layout.addRow("From:", self.from_combo)
        self.headers_layout.addRow("To:", self.to_edit)
        self.headers_layout.addRow("Cc:", self.cc_edit)
        self.headers_layout.addRow("Subject:", self.subject_edit)

        # Additional headers, initially hidden
        self.more_headers_group = QGroupBox()
        self.more_headers_layout = QFormLayout(self.more_headers_group)
        self.bcc_edit = QLineEdit()
        self.reply_to_edit = QLineEdit()
        self.more_headers_layout.addRow("Bcc:", self.bcc_edit)
        self.more_headers_layout.addRow("Reply-To:", self.reply_to_edit)
        self.more_headers_group.setVisible(False)
        
        main_layout.addWidget(headers_group_box)
        main_layout.addWidget(self.more_headers_group)
        
        # Splitter for Body and Attachments
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)

        # Body text editor
        self.body_edit = QTextEdit()
        self.body_edit.setFont(config.text_font)
        self.body_edit.keyPressEvent = self.body_edit_keyPressEvent
        self.splitter.addWidget(self.body_edit)

        # Attachment section
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
        
        self.attachments_list.dragEnterEvent = self.dragEnterEvent
        self.attachments_list.dragMoveEvent = self.dragMoveEvent
        self.attachments_list.dropEvent = self.dropEvent

    def populate_from_field(self):
        """Populates the From: QComboBox with identities from the config file."""
        identities = config.get_setting("email_identities", "identities", [])
        for identity in identities:
            if isinstance(identity, dict) and "name" in identity and "email" in identity:
                display_text = f"{identity['name']} <{identity['email']}>"
                self.from_combo.addItem(display_text, identity['email'])
            elif isinstance(identity, str):
                self.from_combo.addItem(identity, identity)

    def toggle_more_headers(self):
        """Toggles the visibility of the additional headers section."""
        is_visible = self.more_headers_group.isVisible()
        self.more_headers_group.setVisible(not is_visible)
        self.more_headers_button.setText("Less Headers" if not is_visible else "More Headers")
        
    def body_edit_keyPressEvent(self, event):
        """Handles key press events for the mail content area for font zooming."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.body_edit.zoomIn(1)
                return
            elif event.key() == Qt.Key.Key_Minus:
                self.body_edit.zoomOut(1)
                return
        
        QTextEdit.keyPressEvent(self.body_edit, event)


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

    def draft_message(self):
        """Initializes the editor with content based on the draft action."""
        if not self.original_message or not self.draft_action:
            return

        subject = self.original_message.get('Subject', '')
        from_addr = self.original_message.get('From', '')
        to_addrs = self.original_message.get('To', '')
        cc_addrs = self.original_message.get('Cc', '')

        original_body = ""
        for part in self.original_message.walk():
            if part.get_content_type() == 'text/plain':
                original_body = part.get_content()
                break

        if self.draft_action == 'reply':
            self.to_edit.setText(from_addr)
            self.subject_edit.setText(f"Re: {subject}")
            quoted_text = self.quote_message(original_body, from_addr)
            self.body_edit.setPlainText(f"\n\n{quoted_text}")
        
        elif self.draft_action == 'reply-all':
            all_recipients = getaddresses([to_addrs]) + getaddresses([cc_addrs])
            recipients = [addr for name, addr in all_recipients if addr != from_addr]
            self.to_edit.setText(', '.join(recipients))
            self.cc_edit.setText(from_addr)
            self.subject_edit.setText(f"Re: {subject}")
            quoted_text = self.quote_message(original_body, from_addr)
            self.body_edit.setPlainText(f"\n\n{quoted_text}")

        elif self.draft_action == 'forward':
            self.subject_edit.setText(f"Fwd: {subject}")
            
            quoted_headers = []
            quoted_headers.append(f"From: {self.original_message.get('From', 'N/A')}")
            quoted_headers.append(f"Date: {self.original_message.get('Date', 'N/A')}")
            quoted_headers.append(f"Subject: {self.original_message.get('Subject', 'N/A')}")
            quoted_headers.append(f"To: {self.original_message.get('To', 'N/A')}")
            if self.original_message.get('Cc'):
                 quoted_headers.append(f"Cc: {self.original_message.get('Cc', 'N/A')}")
            
            forward_text = f"\n-------- Original Message --------\n{''.join(line + '\\n' for line in quoted_headers)}\n{original_body}"
            self.body_edit.setPlainText(forward_text)
            
            for part in self.original_message.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        self.attachments.append(part)
                        self.attachments_list.addItem(filename)

    def quote_message(self, body, from_addr):
        """Formats the original message body for a reply."""
        prefix = f"On {self.original_message.get('Date', 'a date')}, {from_addr} wrote:\n"
        quoted_lines = [f"> {line}" for line in body.splitlines()]
        return prefix + "\n".join(quoted_lines)

    def add_attachment(self, file_path=None):
        """Opens a file dialog to add an attachment, or adds a dropped file."""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(self, "Add Attachment")
            if not file_path:
                return

        file_path = Path(file_path)
        try:
            mimetype, _ = mimetypes.guess_type(file_path)
            if mimetype is None:
                mimetype = 'application/octet-stream'
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
        """Removes the selected attachment from the list and internal storage."""
        row = self.attachments_list.row(item)
        if 0 <= row < len(self.attachments):
            del self.attachments[row]
            self.attachments_list.takeItem(row)

    def send_message(self):
        """Mocks the send action and quits."""
        dialog = CopyableErrorDialog("Action Mocked", "Sending mail...")
        dialog.exec()
        self.close()

    def save_message(self):
        """Mocks the save action and quits."""
        dialog = CopyableErrorDialog("Action Mocked", "Saving mail as draft...")
        dialog.exec()
        self.close()

    def cancel(self):
        """Mocks the cancel action and quits."""
        self.close()

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Compose or draft a new email.")
    parser.add_argument("--action", choices=['new', 'reply', 'reply-all', 'forward'], default='new', help="Type of mail to draft.")
    parser.add_argument("--mail-file", help="The full path to the mail file to reference for reply/forward actions.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    editor = MailEditor(action=args.action, mail_file_path=args.mail_file)
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
