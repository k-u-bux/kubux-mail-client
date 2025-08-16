#!/usr/bin/env python3

import sys
import argparse
import os
import tempfile
import email
from email import policy
from email.utils import getaddresses
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QListWidget, QSplitter, QMessageBox, QMenu, QGroupBox,
    QFormLayout, QLabel, QInputDialog, QScrollArea, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging
import subprocess
import json
import toml  # Import the TOML library

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

# --- 1. Main Application Window ---
class MailViewer(QMainWindow):
    """Main application window for the mail viewer."""

    def __init__(self, mail_file):
        super().__init__()
        self.mail_file = Path(mail_file)
        self.attachments = []
        self.config = self.load_config()
        self.setup_ui()
        self.load_mail()

    def load_config(self):
        """Loads configuration from a config.toml file."""
        config_path = Path('config.toml')
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return toml.load(f)
            except Exception as e:
                logging.warning(f"Failed to load config.toml: {e}. Using default settings.")
        return {}

    def setup_ui(self):
        """Sets up the user interface."""
        self.setWindowTitle("Mail Viewer")
        self.setMinimumSize(QSize(800, 600))
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header section
        header_groupbox = QGroupBox("Header")
        header_layout = QFormLayout(header_groupbox)
        self.subject_label = QLabel("Subject:")
        self.from_label = QLabel("From:")
        self.to_label = QLabel("To:")
        self.date_label = QLabel("Date:")
        
        header_layout.addRow(QLabel("<b>Subject:</b>"), self.subject_label)
        header_layout.addRow(QLabel("<b>From:</b>"), self.from_label)
        header_layout.addRow(QLabel("<b>To:</b>"), self.to_label)
        header_layout.addRow(QLabel("<b>Date:</b>"), self.date_label)
        
        main_layout.addWidget(header_groupbox)

        # Main content and attachments splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Main mail content area
        self.mail_content = QTextEdit()
        self.mail_content.setReadOnly(True)
        # To disable the automatic conversion of text sequences (like :-) to emojis,
        # set the environment variable QT_DISABLE_EMOJI_SEGMENTER=1 before running the application.
        # This is a Qt-level setting, and cannot be controlled directly from Python at runtime.
        # Example: QT_DISABLE_EMOJI_SEGMENTER=1 python3 mail-viewer.py <mail_file>
        self.mail_content.setAcceptRichText(True)
        splitter.addWidget(self.mail_content)
        
        # Attachments list
        attachments_groupbox = QGroupBox("Attachments")
        attachments_layout = QVBoxLayout(attachments_groupbox)
        self.attachments_list = QListWidget()
        self.attachments_list.itemClicked.connect(self.handle_attachment_click)
        attachments_layout.addWidget(self.attachments_list)
        splitter.addWidget(attachments_groupbox)
        
        # Set stretch factors to give a reasonable default layout
        # This ensures both the mail content and attachments bar are visible by default.
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        
        # Toolbar (mock actions)
        toolbar_layout = QHBoxLayout()
        self.reply_button = QPushButton("Reply (Mock)")
        self.reply_button.clicked.connect(lambda: self.show_mock_action("Reply action will be implemented here."))
        toolbar_layout.addWidget(self.reply_button)
        
        self.reply_all_button = QPushButton("Reply All (Mock)")
        self.reply_all_button.clicked.connect(lambda: self.show_mock_action("Reply All action will be implemented here."))
        toolbar_layout.addWidget(self.reply_all_button)
        
        self.forward_button = QPushButton("Forward (Mock)")
        self.forward_button.clicked.connect(lambda: self.show_mock_action("Forward action will be implemented here."))
        toolbar_layout.addWidget(self.forward_button)
        
        toolbar_layout.addStretch()
        
        main_layout.addLayout(toolbar_layout)

        # Actions and key bindings
        quit_key = self.config.get('key_bindings', {}).get('quit', 'Ctrl+Q')
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence(quit_key))
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def load_mail(self):
        """Loads and displays the email from the specified file."""
        try:
            with open(self.mail_file, 'rb') as fp:
                msg = email.message_from_binary_file(fp, policy=policy.default)
            self.display_message(msg)
        except FileNotFoundError:
            self.show_error_dialog("File Not Found", f"The specified mail file was not found: {self.mail_file}")
            
    def display_message(self, msg):
        """Extracts and displays headers, body, and attachments."""
        # Clear previous content
        self.mail_content.clear()
        self.attachments_list.clear()
        self.attachments = []
        
        # Display headers
        self.subject_label.setText(msg.get("Subject", "No Subject"))
        self.from_label.setText(msg.get("From", "Unknown Sender"))
        self.to_label.setText(msg.get("To", "Unknown Recipient"))
        self.date_label.setText(msg.get("Date", "Unknown Date"))

        # Find and display the main body of the email
        body = ""
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = part.get_content_disposition()
            
            if content_disposition is None or content_disposition.startswith("inline"):
                if content_type == "text/plain":
                    body = part.get_content()
                    self.mail_content.setPlainText(body)
                    break
                elif content_type == "text/html":
                    html_content = part.get_content()
                    # A basic attempt to clean HTML,
                    # this is not robust and a full HTML renderer is needed
                    # for a production-ready application.
                    plain_text = re.sub(r'<[^>]+>', '', html_content)
                    self.mail_content.setPlainText(plain_text)
                    break
            elif content_disposition.startswith("attachment"):
                filename = part.get_filename()
                if filename:
                    self.attachments.append({'filename': filename, 'part': part})
                    self.attachments_list.addItem(filename)

    def handle_attachment_click(self, item):
        """Handles a click on an attachment item."""
        filename = item.text()
        for attachment in self.attachments:
            if attachment['filename'] == filename:
                self.save_attachment(attachment)
                return

    def save_attachment(self, attachment):
        """Saves a selected attachment to a temporary directory."""
        try:
            temp_dir = Path(tempfile.gettempdir())
            save_path = temp_dir / attachment['filename']
            with open(save_path, 'wb') as f:
                f.write(attachment['part'].get_content())
            
            QMessageBox.information(self, "Attachment Saved", f"Attachment saved to:\n{save_path}")
            
        except Exception as e:
            self.show_error_dialog("Save Error", f"Failed to save attachment: {e}")

    def show_error_dialog(self, title, message):
        """Shows a copyable error dialog for detailed errors."""
        dialog = CopyableErrorDialog(title, message, self)
        dialog.exec()

    def mail_content_contextMenuEvent(self, event):
        """Defines a context menu for the mail content area."""
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.mail_content.copy)
        menu.addAction(copy_action)
        menu.addSeparator()
        
        view_raw_action = QAction("View Raw Message", self)
        view_raw_action.triggered.connect(lambda: self.show_mock_action("Raw message will be opened in $EDITOR."))
        menu.addAction(view_raw_action)

        menu.exec(self.mail_content.mapToGlobal(event.pos()))
        
    def mail_content_keyPressEvent(self, event):
        """Handles key press events for the mail content area."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.mail_content.zoomIn()
                return
            elif event.key() == Qt.Key.Key_Minus:
                self.mail_content.zoomOut()
                return

        QTextEdit.keyPressEvent(self.mail_content, event)

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
