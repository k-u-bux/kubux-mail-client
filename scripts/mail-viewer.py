#!/usr/bin/env python3

import sys
import argparse
import os
import tempfile
import email
from email import policy
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QListWidget, QSplitter, QMessageBox, QMenu, QWidgetAction
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QAction, QGuiApplication, QKeySequence
import logging
from config import config  # Import the shared config object

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MailViewer(QMainWindow):
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Viewer")
        self.setMinimumSize(QSize(1024, 768))

        self.mail_file_path = Path(mail_file_path).expanduser()
        self.message = self.parse_mail_file()

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

        # Action Buttons
        self.reply_button = QPushButton("Reply")
        self.reply_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Reply functionality to be implemented."))
        top_bar_layout.addWidget(self.reply_button)
        
        self.reply_all_button = QPushButton("Reply All")
        self.reply_all_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Reply All functionality to be implemented."))
        top_bar_layout.addWidget(self.reply_all_button)

        self.forward_button = QPushButton("Forward")
        self.forward_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Forward functionality to be implemented."))
        top_bar_layout.addWidget(self.forward_button)
        
        self.tags_button = QPushButton("Tags...")
        self.tags_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Tag management to be implemented."))
        top_bar_layout.addWidget(self.tags_button)
        
        self.spam_button = QPushButton("Mark as Spam")
        self.spam_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Message will be tagged as +spam."))
        top_bar_layout.addWidget(self.spam_button)
        
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Message will be tagged as +deleted."))
        top_bar_layout.addWidget(self.delete_button)

        self.todo_button = QPushButton("Mark as Todo")
        self.todo_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Message will be tagged as +todo."))
        top_bar_layout.addWidget(self.todo_button)
        
        self.view_thread_button = QPushButton("View Thread")
        self.view_thread_button.clicked.connect(lambda: QMessageBox.information(self, "Mock Action", "Thread viewer to be implemented."))
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
        
        # Header context menu (mocked for now)
        self.headers_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.headers_content.customContextMenuRequested.connect(self.show_header_context_menu)

        # Mail Content area
        self.mail_content = QTextEdit()
        self.mail_content.setReadOnly(True)
        self.mail_content.setFont(config.text_font)
        self.splitter.addWidget(self.mail_content)
        
        # Add a context menu for clipboard actions
        self.mail_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mail_content.customContextMenuRequested.connect(self.show_context_menu)

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
        attachments = []
        for part in self.message.walk():
            # Check for attachments
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename:
                    attachments.append(part)
                    self.attachments_list.addItem(f"Attachment: {filename}")
                    
            # Prioritize plain text over HTML
            if part.get_content_type() == 'text/plain':
                body_text = part.get_content()
                self.mail_content.setHtml("") # Clear any previous HTML rendering
                self.mail_content.setPlainText(body_text)
                return

            if part.get_content_type() == 'text/html' and not body_text:
                body_text = part.get_content()
                self.mail_content.setHtml(body_text)

        self.attachments = attachments

    def handle_attachment_click(self, item):
        """Saves the attachment to a temporary file and opens it."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part.get_filename()

            with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as temp_file:
                temp_file.write(attachment_part.get_payload(decode=True))
                temp_path = temp_file.name

            # Open the temporary file with the system's default application
            os.system(f"xdg-open '{temp_path}'")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open attachment: {e}")

    def show_context_menu(self, pos):
        """Creates a context menu for the mail content area."""
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.mail_content.copy)
        menu.addAction(copy_action)
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

        # Let the default handler process the event if it's not a zoom hotkey
        QTextEdit.keyPressEvent(self.mail_content, event)

    def show_header_context_menu(self, pos):
        """Mocks a context menu for header fields."""
        menu = QMenu(self)
        
        # Get the cursor position to find the email address
        cursor = self.headers_content.textCursor()
        cursor.select(cursor.SelectionType.WordUnderCursor)
        selected_text = cursor.selectedText()
        
        # This is a very simple check, we will need to improve this later
        if '@' in selected_text:
            add_contact_action = QAction(f"Add {selected_text} to Contacts", self)
            add_contact_action.triggered.connect(lambda: QMessageBox.information(self, "Mock Action", f"Adding '{selected_text}' to contacts."))
            menu.addAction(add_contact_action)
            
            new_mail_action = QAction(f"Compose new mail to {selected_text}", self)
            new_mail_action.triggered.connect(lambda: QMessageBox.information(self, "Mock Action", f"Composing new mail to '{selected_text}'."))
            menu.addAction(new_mail_action)
            
            search_action = QAction(f"Search for mail from {selected_text}", self)
            search_action.triggered.connect(lambda: QMessageBox.information(self, "Mock Action", f"Searching for mail from '{selected_text}'."))
            menu.addAction(search_action)

        menu.exec(self.headers_content.mapToGlobal(pos))


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
