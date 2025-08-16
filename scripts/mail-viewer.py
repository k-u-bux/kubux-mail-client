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
    QFormLayout, QLabel, QInputDialog, QScrollArea, QDialog, QDialogButtonBox,
    QFileDialog
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging
import subprocess
import json
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

# Custom widget for clickable email addresses
class ClickableLabel(QLabel):
    clicked = Signal(str, bool)
    
    def __init__(self, text, address, parent=None):
        super().__init__(text, parent)
        self.address = address
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.selected = False
        self.update_style()
        self.setToolTip(address)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected = not self.selected
            self.update_style()
            self.clicked.emit(self.address, self.selected)
        super().mousePressEvent(event)
    
    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background-color: lightgray;")
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.update_style()
        super().leaveEvent(event)
        
    def update_style(self):
        if self.selected:
            self.setStyleSheet("background-color: #aaddff;")
        else:
            self.setStyleSheet("background-color: transparent;")

class MailViewer(QMainWindow):
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Viewer")
        self.setMinimumSize(QSize(1024, 768))

        self.mail_file_path = Path(mail_file_path).expanduser()
        self.message = self.parse_mail_file()
        self.attachments = []
        self.selected_addresses = set()
        self.tags = []
        
        self.notmuch_enabled = self.check_notmuch()

        if not self.message:
            QMessageBox.critical(self, "Error", "Could not load or parse the mail file.")
            sys.exit(1)

        self.setup_ui()
        self.display_message()

    def check_notmuch(self):
        """Checks if the notmuch command is available."""
        try:
            subprocess.run(['notmuch', '--version'], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            dialog = CopyableErrorDialog(
                "Notmuch Not Found",
                f"The 'notmuch' command was not found or is not executable.\n"
                f"Tag-related functionality will be disabled.\n\nError: {e}"
            )
            dialog.exec()
            return False

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
        self.compose_menu.addAction("Reply to Selected").triggered.connect(self.reply_to_selected)
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
        if not self.notmuch_enabled:
            self.tags_button.setDisabled(True)
        top_bar_layout.addWidget(self.tags_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(lambda: self.show_mock_action("Message will be tagged as +deleted."))
        top_bar_layout.addWidget(self.delete_button)

        self.view_thread_button = QPushButton("View Thread")
        self.view_thread_button.clicked.connect(lambda: self.show_mock_action("Thread viewer to be implemented."))
        top_bar_layout.addWidget(self.view_thread_button)
        
        top_bar_layout.addStretch()

        # Add the Quit button here to be flush right
        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)


        # Tags display area in a horizontal scroll area
        self.tags_scroll_area = QScrollArea()
        self.tags_scroll_area.setWidgetResizable(True)
        self.tags_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tags_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tags_scroll_area.setFixedHeight(40) # Set a fixed, minimal height

        tags_container = QWidget()
        self.tags_layout = QHBoxLayout(tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_scroll_area.setWidget(tags_container)
        
        if self.notmuch_enabled:
            main_layout.addWidget(self.tags_scroll_area)
        else:
            self.tags_scroll_area.hide()

        # Splitter for Headers, Content, and Attachments
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter)

        # Mail Headers section as a GroupBox
        self.headers_group_box = QGroupBox()
        self.headers_layout = QFormLayout(self.headers_group_box)
        self.headers_group_box.setStyleSheet("QGroupBox { border: 1px solid gray; }")
        self.splitter.addWidget(self.headers_group_box)
        
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
        
        # Set context menu policy for the attachments list
        self.attachments_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.attachments_list.customContextMenuRequested.connect(self.show_attachment_context_menu)

        # Set initial sizes
        self.splitter.setSizes([100, 500, 50])
        
        # Add the quit action to the main window
        # Get key binding from the new config logic
        quit_key = config.get_setting("bindings", "quit_action") or "Ctrl+Q"
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence(quit_key))
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def display_message(self):
        if not self.message:
            return

        if self.notmuch_enabled:
            self.update_tags_ui()

        # Clear existing header widgets
        while self.headers_layout.rowCount() > 0:
            self.headers_layout.removeRow(0)

        # Populate headers
        header_fields = {"From": self.message.get("From"),
                         "To": self.message.get("To"),
                         "Cc": self.message.get("Cc"),
                         "Subject": self.message.get("Subject"),
                         "Date": self.message.get("Date")}

        for field, value in header_fields.items():
            if value:
                label = QLabel(f"<b>{field}:</b>")
                label.setFont(config.interface_font)
                
                # Create a widget for addresses
                addresses_widget = QWidget()
                addresses_layout = QHBoxLayout(addresses_widget)
                addresses_layout.setContentsMargins(0, 0, 0, 0)
                
                # Parse and add clickable labels for addresses
                if field in ["From", "To", "Cc"]:
                    addresses = getaddresses([value])
                    for name, address in addresses:
                        display_text = f"{name} &lt;{address}&gt;" if name else address
                        addr_label = ClickableLabel(display_text, address)
                        addr_label.clicked.connect(self.handle_address_selection)
                        addresses_layout.addWidget(addr_label)
                else:
                    addresses_layout.addWidget(QLabel(value))
                
                addresses_layout.addStretch()
                self.headers_layout.addRow(label, addresses_widget)

        # Find the plain text or HTML body of the email and attachments
        body_text = ""
        self.attachments.clear()
        self.attachments_list.clear()
        for part in self.message.walk():
            # Check for attachments
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename:
                    self.attachments.append(part)
                    self.attachments_list.addItem(filename)
                    
            # Prioritize plain text over HTML
            if part.get_content_type() == 'text/plain':
                body_text = part.get_content()
                self.mail_content.setHtml("")
                self.mail_content.setPlainText(body_text)
                return

            if part.get_content_type() == 'text/html' and not body_text:
                body_text = part.get_content()
                sanitized_html = self.sanitize_html_fonts(body_text)
                self.mail_content.setHtml(sanitized_html)

    def sanitize_html_fonts(self, html_content: str) -> str:
        """Removes hardcoded font-size declarations from HTML to allow Qt to scale the font."""
        # This regex finds any font-size declaration in a style attribute and removes it.
        return re.sub(r'font-size:\s*[^;"]+;?', '', html_content, flags=re.IGNORECASE)

    def get_tags(self):
        """Queries the notmuch database for tags of the current mail file."""
        try:
            # Use a more compatible format that should work on older versions of notmuch
            command = ['notmuch', 'search', '--output=tags', '--format=text', f'filename:{self.mail_file_path}']
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            
            # The output is a simple list of tags, one per line.
            # We filter out any empty lines.
            tags_list = [tag.strip() for tag in result.stdout.strip().split('\n') if tag.strip()]
            self.tags = sorted(tags_list)

        except subprocess.CalledProcessError as e:
            dialog = CopyableErrorDialog(
                "Notmuch Command Failed",
                f"An error occurred while running notmuch:\n\n{e.stderr}"
            )
            dialog.exec()
            self.tags = []
        
        return self.tags

    def update_tags_ui(self):
        """Clears and rebuilds the UI to display the current tags."""
        # Clear existing tag widgets
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Fetch the latest tags
        self.tags = self.get_tags()
        
        # Add a button for each tag
        for tag in self.tags:
            tag_button = QPushButton(tag)
            # Use lambda to pass the tag name to the slot
            tag_button.clicked.connect(lambda checked, t=tag: self.remove_tag(t))
            self.tags_layout.addWidget(tag_button)

        # Add stretch to push the next button to the right
        self.tags_layout.addStretch()

        # Add "Add tags" button
        add_tag_button = QPushButton("Add tags")
        add_tag_button.clicked.connect(self.add_tag)
        self.tags_layout.addWidget(add_tag_button)


    def remove_tag(self, tag):
        """Removes a tag from the current mail using the notmuch command."""
        try:
            # Use the full path with the 'filename:' query term.
            command = ['notmuch', 'tag', f'-{tag}', f'filename:{self.mail_file_path}']
            subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info(f"Tag '{tag}' removed successfully.")
            self.update_tags_ui() # Refresh the UI to reflect the change
        except subprocess.CalledProcessError as e:
            dialog = CopyableErrorDialog("Failed to Remove Tag", f"Failed to remove tag '{tag}':\n\n{e.stderr}")
            dialog.exec()
        except FileNotFoundError:
            dialog = CopyableErrorDialog("Notmuch Not Found", "The 'notmuch' command was not found. Please ensure it is installed and in your PATH.")
            dialog.exec()
    
    def add_tag(self):
        """Mock function for adding a new tag."""
        text, ok = QInputDialog.getText(self, "Add Tags", "Enter tag(s) to add (comma-separated):")
        if ok and text:
            new_tags = [t.strip() for t in text.split(',')]
            for tag in new_tags:
                try:
                    command = ['notmuch', 'tag', f'+{tag}', f'filename:{self.mail_file_path}']
                    subprocess.run(command, check=True, capture_output=True, text=True)
                    logging.info(f"Tag '{tag}' added successfully.")
                except subprocess.CalledProcessError as e:
                    dialog = CopyableErrorDialog("Failed to Add Tag", f"Failed to add tag '{tag}':\n\n{e.stderr}")
                    dialog.exec()
            self.update_tags_ui()


    def handle_address_selection(self, address, is_selected):
        if is_selected:
            self.selected_addresses.add(address)
        else:
            self.selected_addresses.discard(address)
        print(f"Selected Addresses: {self.selected_addresses}")

    def reply_to_selected(self):
        if self.selected_addresses:
            addresses_str = ", ".join(self.selected_addresses)
            self.show_mock_action(f"Replying to selected addresses: {addresses_str}")
        else:
            self.show_mock_action("No addresses selected.")

    def show_attachment_context_menu(self, pos):
        """Shows a context menu with actions for the clicked attachment."""
        item = self.attachments_list.itemAt(pos)
        if item:
            menu = QMenu(self)
            
            open_action = QAction("Open", self)
            open_action.triggered.connect(lambda: self.handle_attachment_open(item))
            menu.addAction(open_action)
            
            save_as_action = QAction("Save As...", self)
            save_as_action.triggered.connect(lambda: self.handle_attachment_save_as(item))
            menu.addAction(save_as_action)
            
            menu.exec(self.attachments_list.mapToGlobal(pos))
            
    def handle_attachment_open(self, item):
        """Saves the attachment to a temporary file and opens it."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part.get_filename()

            with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as temp_file:
                temp_file.write(attachment_part.get_payload(decode=True))
                temp_path = temp_file.name

            # Use system default application to open the file
            if sys.platform == "win32":
                os.startfile(temp_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", temp_path])
            else: # Linux and other POSIX-like systems
                subprocess.run(["xdg-open", temp_path])
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open attachment: {e}")

    def handle_attachment_save_as(self, item):
        """Prompts the user to save the attachment to a chosen location."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part.get_filename()

            save_path, _ = QFileDialog.getSaveFileName(self, "Save Attachment", filename)
            
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(attachment_part.get_payload(decode=True))
                QMessageBox.information(self, "Success", f"Attachment saved to:\n{save_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save attachment: {e}")

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
