#!/usr/bin/env python3

import sys
import argparse
import os
import tempfile
import email
from email import policy
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QListWidget, QSplitter, QMessageBox, QMenu, QWidgetAction
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QKeySequence, QAction, QGuiApplication
import logging
from config import config

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MailViewer(QMainWindow):
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Viewer")
        self.setMinimumSize(QSize(1024, 768))

        self.mail_file_path = Path(mail_file_path).expanduser()
        self.message = self.parse_mail_file()
        self.attachments = []

        if not self.message:
            QMessageBox.critical(self, "Error", "Could not load or parse the mail file.")
            sys.exit(1)

        self.setup_ui()
        self.display_message()

    def parse_mail_file(self):
        """Parses a real email file from the local filesystem."""
        if not self.mail_file_path.exists():
            return None
        
        try:
            with open(self.mail_file_path, 'rb') as f:
                return email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            logging.error(f"Failed to parse mail file: {e}")
            return None

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top section for action buttons
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        main_layout.addWidget(top_bar)

        # Compose button with menu
        self.compose_button = QPushButton("Compose")
        self.compose_menu = QMenu(self)
        self.compose_menu.addAction("Reply").triggered.connect(lambda: self.show_mock_action("Reply to be implemented"))
        self.compose_menu.addAction("Reply All").triggered.connect(lambda: self.show_mock_action("Reply All to be implemented"))
        self.compose_menu.addAction("Forward").triggered.connect(lambda: self.show_mock_action("Forward to be implemented"))
        self.compose_menu.addSeparator()
        self.compose_menu.addAction("Compose New").triggered.connect(lambda: self.show_mock_action("Compose new mail to be implemented"))
        self.compose_button.setMenu(self.compose_menu)
        top_bar_layout.addWidget(self.compose_button)
        
        # Tags button with menu
        self.tags_button = QPushButton("Tags")
        self.tags_menu = QMenu(self)
        self.tags_menu.addAction("Add/Remove Spam").triggered.connect(lambda: self.show_mock_action("Message will be tagged as +spam."))
        self.tags_menu.addAction("Add/Remove Todo").triggered.connect(lambda: self.show_mock_action("Message will be tagged as +todo."))
        self.tags_menu.addAction("Add/Remove Read").triggered.connect(lambda: self.show_mock_action("Message will be tagged as +read."))
        self.tags_menu.addSeparator()
        self.tags_menu.addAction("Edit All Tags").triggered.connect(lambda: self.show_mock_action("Full tag management to be implemented."))
        self.tags_button.setMenu(self.tags_menu)
        top_bar_layout.addWidget(self.tags_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(lambda: self.show_mock_action("Message will be tagged as +deleted."))
        top_bar_layout.addWidget(self.delete_button)

        self.view_thread_button = QPushButton("View Thread")
        self.view_thread_button.clicked.connect(lambda: self.show_mock_action("Thread viewer to be implemented."))
        top_bar_layout.addWidget(self.view_thread_button)
        
        top_bar_layout.addStretch()

        # Splitter for Headers, Content, and Attachments
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)

        # Mail Headers section
        self.headers_content = QTextEdit()
        self.headers_content.setReadOnly(True)
        self.headers_content.setFixedHeight(120)
        self.headers_content.setMinimumHeight(80)
        self.headers_content.setFont(config.interface_font)
        self.splitter.addWidget(self.headers_content)
        
        # Header context menu
        self.headers_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.headers_content.customContextMenuRequested.connect(self.show_header_context_menu)

        # Mail Content area
        self.mail_content = QTextEdit()
        self.mail_content.setReadOnly(True)
        self.mail_content.setFont(config.text_font)
        self.splitter.addWidget(self.mail_content)
        
        # Add a context menu for clipboard actions and view raw
        self.mail_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mail_content.customContextMenuRequested.connect(self.show_content_context_menu)

        # Add a key press event handler for dynamic font sizing
        self.mail_content.keyPressEvent = self.mail_content_keyPressEvent

        # Attachments list
        self.attachments_list = QListWidget()
        self.attachments_list.setMinimumHeight(40)
        self.attachments_list.setMaximumHeight(200)
        self.splitter.addWidget(self.attachments_list)
        self.attachments_list.itemClicked.connect(self.handle_attachment_click)

        # Set initial sizes
        self.splitter.setSizes([100, 500, 50])

    def display_message(self):
        if not self.message:
            return

        # Display headers
        headers_text = ""
        for name in ["From", "To", "Subject", "Date", "Cc"]:
            if self.message.get(name):
                headers_text += f"{name}: {self.message.get(name)}\n"
        self.headers_content.setPlainText(headers_text)

        # Find the plain text or HTML body of the email
        body_text = ""
        self.attachments.clear()
        for part in self.message.walk():
            # Check for attachments
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename:
                    self.attachments.append(part)
                    self.attachments_list.addItem(f"Attachment: {filename}")
                    
            # Prioritize plain text over HTML
            if part.get_content_type() == 'text/plain':
                body_text = part.get_content()
                self.mail_content.setHtml("")
                self.mail_content.setPlainText(body_text)
                return

            if part.get_content_type() == 'text/html' and not body_text:
                body_text = part.get_content()
                self.mail_content.setHtml(body_text)

    def handle_attachment_click(self, item):
        """Saves the attachment to a temporary file and opens it."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part.get_filename()

            with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as temp_file:
                temp_file.write(attachment_part.get_payload(decode=True))
                temp_path = temp_file.name

            os.system(f"xdg-open '{temp_path}'")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open attachment: {e}")

    def show_content_context_menu(self, pos):
        """Creates a context menu for the mail content area."""
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.mail_content.copy)
        menu.addAction(copy_action)
        menu.addSeparator()
        
        view_raw_action = QAction("View Raw Message", self)
        view_raw_action.triggered.connect(lambda: self.show_mock_action("Raw message will be opened in $EDITOR."))
        menu.addAction(view_raw_action)

        menu.exec(self.mail_content.mapToGlobal(pos))
        
    def mail_content_keyPressEvent(self, event):
        """Handles key press events for the mail content area."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
                self.mail_content.zoomIn()
                return
            elif event.key() == Qt.Key.Key_Minus:
                self.mail_content.zoomOut()
                return

        QTextEdit.keyPressEvent(self.mail_content, event)

    def show_header_context_menu(self, pos):
        """Mocks a context menu for header fields."""
        menu = QMenu(self)
        
        # Get the cursor position and try to find an email address
        cursor = self.headers_content.cursorForPosition(pos)
        cursor.select(cursor.SelectionType.WordUnderCursor)
        selected_text = cursor.selectedText().strip()
        
        # Regex to find a valid email address
        email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        match = re.search(email_regex, selected_text)
        
        if match:
            email_address = match.group(0)
            
            add_contact_action = QAction(f"Add {email_address} to Contacts", self)
            add_contact_action.triggered.connect(lambda: self.show_mock_action(f"Adding '{email_address}' to contacts."))
            menu.addAction(add_contact_action)
            
            new_mail_action = QAction(f"Compose new mail to {email_address}", self)
            new_mail_action.triggered.connect(lambda: self.show_mock_action(f"Composing new mail to '{email_address}'."))
            menu.addAction(new_mail_action)
            
            search_action = QAction(f"Search for mail from {email_address}", self)
            search_action.triggered.connect(lambda: self.show_mock_action(f"Searching for mail from '{email_address}'."))
            menu.addAction(search_action)

        menu.exec(self.headers_content.mapToGlobal(pos))
        
    def show_mock_action(self, message):
        QMessageBox.information(self, "Action Mocked", message)

# --- 3. Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View a single mail file.")
    parser.add_argument("mail_file", help="The full path to the mail file to view.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    viewer = MailViewer(args.mail_file)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
