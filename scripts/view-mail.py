#!/usr/bin/env python3

import sys
import mailparser
import argparse
import os
import tempfile
import email
from email import policy
from email.utils import getaddresses
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextBrowser, QTextEdit, QHBoxLayout,
    QPushButton, QListWidget, QSplitter, QMessageBox, QMenu, QGroupBox,
    QFormLayout, QLabel, QInputDialog, QScrollArea, QDialog, QDialogButtonBox,
    QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, Signal, QUrl, QRegularExpression, QEvent
from PySide6.QtGui import QFont, QKeySequence, QAction, QTextCursor, QTextCharFormat, QColor, QDesktopServices, QCursor

import logging
import subprocess
import json
import textwrap
import base64

from config import config
from common import display_error, html_to_plain_text
from header_widget import MailHeaderWidget

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION (PLACEHOLDER) ---
# NOTE: Replace this with your actual email address.
# In a future version, this should be loaded from the config file.
MY_EMAIL_ADDRESS = "your.email@example.com"


class MailSourceViewer(QDialog):
    """A simple dialog to display the raw content of the mail file."""
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raw Message Source")
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)

        # 1. Use QTextEdit for content display and selection
        self.source_content = QTextEdit()
        # Set it as read-only, but keep text interaction enabled
        self.source_content.setReadOnly(True)
        self.source_content.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.source_content.setFont(config.get_text_font())
        
        main_layout.addWidget(self.source_content)

        # 2. Load the file content
        try:
            with open(mail_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_source = f.read()
            self.source_content.setPlainText(raw_source)
        except Exception as e:
            self.source_content.setPlainText(f"Error loading source file: {e}")
            self.setWindowTitle("Raw Message Source (Error)")
            
        # 3. Add Close Button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)


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
        self.setWindowTitle("Kubux Mail Client - Viewer")
        self.resize(QSize(1024, 768))

        self.mail_file_path = Path(mail_file_path).expanduser()
        self.selected_addresses = set()
        self.tags = []
        self.tags_state = {}
        self.show_headers = True
        self.attachments = []
        self.message_id = None
        self.message = None
        self.parse_mail_file()
        
        self.process_initial_tags()
        self.setup_ui()
        self.setup_key_bindings()
        self.display_message()

    def parse_mail_file(self):
        """Parses a real email file from the local filesystem."""
        if not self.mail_file_path.exists():
            logging.error(f"Mail file {self.mail_file_path} does not exist.")
            os.exit(1)
        try:
            mail = mailparser.parse_from_file(self.mail_file_path)
            with open(self.mail_file_path, 'rb') as f:
                self.message = email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            logging.error(f"Failed to parse mail file: {e}")
            os.exit(1)
        # print("parsing message")
        body_text = ""
        for part in self.message.walk():
            # Prioritize plain text over HTML
            if part.get_content_type() == 'text/plain':
                body_text = part.get_content()
                self.mail_body = body_text
                self.is_html_body = False
                break
            if part.get_content_type() == 'text/html' and not body_text:
                body_text = part.get_content()
                sanitized_html = self.sanitize_html_fonts(body_text)
                self.mail_body = sanitized_html
                self.is_html_body = True
        self.attachments = mail.attachments 
        # unfortunately not all mail have only one id
        if isinstance(mail.message_id, list):
            if not mail.message_id:
                raise ValueError("Message-ID list is empty.")
            self.message_id = mail.message_id[0].strip('<>')
        else:
            self.message_id = mail.message_id.strip('<>')
        print(f"Message-ID = {self.message_id}")


    def process_initial_tags(self):
        """
        Manages initial tag state. If a mail has the $unseen tag,
        it is silently replaced with the $unused tag.
        """
        current_tags = self.get_tags()
        if '$unseen' in current_tags:
            logging.info("Found '$unseen' tag. Silently replacing with '$unused'.")
            try:
                command = ['notmuch', 'tag', '-$unseen', '+$unused', f'id:{self.message_id}']
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to process initial tags: {e.stderr}")


    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setFont(config.get_interface_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Top section for action buttons
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        main_layout.addWidget(top_bar)

        # Compose button with menu
        self.compose_button = QPushButton("Compose")
        self.compose_menu = QMenu(self)
        self.compose_menu.addAction("Reply").triggered.connect(self.reply)
        self.compose_menu.addAction("Reply All").triggered.connect(self.reply_all)
        self.compose_menu.addAction("Follow Up").triggered.connect(self.follow_up)
        self.compose_menu.addAction("Forward").triggered.connect(self.forward)
        self.compose_menu.addAction("Forward (cc all)").triggered.connect(self.forward_cc)
        self.compose_menu.addAction("Reply to Selected").triggered.connect(self.reply_to_selected)
        self.compose_menu.addSeparator()
        self.compose_menu.addAction("Compose New").triggered.connect(self.compose_new)
        self.compose_button.setMenu(self.compose_menu)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.addWidget(self.compose_button)
        
        # Tags button with menu
        self.tags_button = QPushButton("Tags")
        self.tags_menu = QMenu(self)
        for tag in config.get_tags():
            l = lambda checked, dummy=f"{tag}": self.really_toggle_tag( dummy )
            action = self.tags_menu.addAction(f"+/- {tag}")
            action.triggered.connect( l )
        self.tags_menu.addSeparator()
        self.tags_menu.addAction("+/- spam").triggered.connect( lambda: self.really_toggle_tag("spam") )
        self.tags_menu.addAction("+/- deleted").triggered.connect( lambda: self.really_toggle_tag("deleted") )
        self.tags_menu.addSeparator()
        self.tags_menu.addAction("Add Tags").triggered.connect( lambda: self.add_tag_dialog() )
        self.tags_button.setMenu(self.tags_menu)
        top_bar_layout.addWidget(self.tags_button)

        self.view_thread_button = QPushButton("Thread")
        self.view_thread_button.clicked.connect( lambda: self.view_thread() )
        top_bar_layout.addWidget(self.view_thread_button)
        self.view_source_button = QPushButton("Source")
        self.view_source_button.clicked.connect( lambda: self.view_source() )
        top_bar_layout.addWidget(self.view_source_button)

        self.toggle_header_visibility_button =  QPushButton("Hide Headers")
        self.toggle_header_visibility_button.clicked.connect(self.toggle_header_visibility)
        top_bar_layout.addWidget(self.toggle_header_visibility_button)
        
        top_bar_layout.addStretch()

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect( lambda: self.delete_message() )
        top_bar_layout.addWidget(self.delete_button)

        top_bar_layout.addStretch()

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
        main_layout.addWidget(self.tags_scroll_area)

        # Splitter for Headers, Content, and Attachments
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.splitter)

        # Mail Headers section as a GroupBox
        self.headers_group_box = MailHeaderWidget(self, config, self.message)
        self.splitter.addWidget(self.headers_group_box)
        self.show_or_hide_headers()

        # Mail Content area
        self.mail_content = QTextBrowser()
        self.mail_content.setFont(config.get_text_font())
        self.mail_content.setReadOnly(True)
        self.mail_content.setFont(config.get_text_font())
        self.mail_content.setOpenLinks(False) 
        self.splitter.addWidget(self.mail_content)
        
        # Add a context menu for clipboard actions and view raw
        self.mail_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mail_content.customContextMenuRequested.connect(self.show_content_context_menu)

        # Attachments list
        if self.attachments:
            self.attachments_list = QListWidget()
            self.attachments_list.setFont(config.get_interface_font())
            self.attachments_list.setMinimumHeight(40)
            self.attachments_list.setMaximumHeight(200)
            self.splitter.addWidget(self.attachments_list)
            
            # Set context menu policy for the attachments list
            self.attachments_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.attachments_list.customContextMenuRequested.connect(self.show_attachment_context_menu)

            for part in self.attachments:
                print(f"attachment {part.keys()}")
                self.attachments_list.addItem(part.get('filename'))

            self.splitter.setSizes([100, 500, 50])
        else:
            self.splitter.setSizes([100, 500])

    def show_or_hide_headers(self):
        if self.show_headers:
            self.toggle_header_visibility_button.setText("Hide Headers")
            self.headers_group_box.show()
        else:
            self.toggle_header_visibility_button.setText("Show Headers")
            self.headers_group_box.hide()

    def toggle_header_visibility(self):
        self.show_headers = not self.show_headers
        self.show_or_hide_headers()

    def setup_key_bindings(self):
        """Sets up key bindings based on the config file."""
        # Core viewer actions
        actions = {
            "quit": self.close,
            "close_viewer": self.close,
            "reply": self.reply,
            "reply_all": self.reply_all,
            "forward": self.forward,
            "edit_tags": lambda: self.show_mock_action("Edit Tags action triggered by key binding."),
            "zoom_in": lambda: self.mail_content.zoomIn(1),
            "zoom_out": lambda: self.mail_content.zoomOut(1),
            "select_all": self.mail_content.selectAll
        }

        for name, func in actions.items():
            key_seq = config.get_keybinding(name)
            if key_seq:
                action = QAction(self)
                action.setShortcut(QKeySequence(key_seq))
                action.triggered.connect(func)
                self.addAction(action)

   
    def display_message(self):
        if not self.message:
            return

        self.update_tags_ui()

        try:
            self.mail_content.anchorClicked.disconnect(self.handle_link_clicked)
        except TypeError:
            pass # Ignore if not connected yet
        self.mail_content.anchorClicked.connect(self.handle_link_clicked)
        self.mail_content.setTextInteractionFlags(Qt.TextBrowserInteraction)

        if self.is_html_body:
            self.mail_content.setHtml(self.mail_body)
        else:
            self.mail_content.setPlainText(self.mail_body)
            # For plain text, we need to detect URLs manually
            self.highlight_urls_in_plain_text()
        
    def highlight_urls_in_plain_text(self):
        """Find and highlight URLs in plain text content."""
        # Comprehensive URL regex pattern
        url_pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+|file://[^\s<>"\[\]]+)'
        
        # Create a QRegularExpression for matching
        url_regex = QRegularExpression(url_pattern)
        
        # Get the document from the QTextEdit
        document = self.mail_content.document()
        
        # Create a base format for highlighting URLs (no AnchorHref yet)
        base_url_format = QTextCharFormat()
        base_url_format.setForeground(QColor("#0000FF"))  # Blue color for links
        base_url_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        base_url_format.setAnchor(True)
        base_url_format.setToolTip("Click to open link")
        
        # Start finding all matches in the document
        cursor = QTextCursor(document)
        
        while not cursor.isNull() and not cursor.atEnd():
            # Search for the URL pattern
            match = url_regex.match(document.toPlainText(), cursor.position())
            
            if not match.hasMatch():
                break
                
            # Get the matched URL
            url = match.captured(0)
            start = match.capturedStart(0)
            end = match.capturedEnd(0)
            
            # Select the text range
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            
            match_format = QTextCharFormat(base_url_format)
            match_format.setAnchorHref(url)
            
            # Apply URL format
            cursor.setCharFormat(match_format)
            
            # Update the cursor position to search for the next match
            cursor.setPosition(end)
    
    def handle_link_clicked(self, url):
        """Handle clicking on a URL by opening it in the default browser."""
        if isinstance(url, str):
            url = QUrl(url)
            
        # Check for relative URLs and convert them to absolute if needed
        if url.isRelative():
            # Try to determine base URL from message
            base_url = None
            for header in ["List-Post", "List-Id", "Reply-To", "From"]:
                if self.message.get(header):
                    domain = self.extract_domain_from_header(self.message.get(header))
                    if domain:
                        base_url = f"https://{domain}"
                        break
            
            if base_url:
                url = QUrl(base_url).resolved(url)
        
        # Validate the URL scheme for security
        scheme = url.scheme().lower()
        if scheme in ["http", "https", "file"]:
            # Open the URL in the default browser or file handler
            QDesktopServices.openUrl(url)
        else:
            # For security, only allow http, https, and file schemes
            QMessageBox.warning(
                self,
                "Unsafe URL Scheme",
                f"The URL uses an unsafe scheme: {scheme}://"
                "\n\nOnly http://, https://, and file:// URLs can be opened."
            )
    
    def extract_domain_from_header(self, header_value):
        """Extract domain from email address in header."""
        # Simple regex to extract domain from email
        match = re.search(r'@([^>\s]+)', header_value)
        if match:
            return match.group(1)
        return None


    def sanitize_html_fonts(self, html_content: str) -> str:
        """Removes hardcoded font-size declarations from HTML to allow Qt to scale the font."""
        # This regex finds any font-size declaration in a style attribute and removes it.
        return re.sub(r'font-size:\s*[^;"]+;?', '', html_content, flags=re.IGNORECASE)

    def delete_message(self):
        self.add_tag("deleted")
        self.close()

    def view_thread(self):
        if self.message_id:
            command = ['notmuch', 'search', '--output=threads', '--format=text', f'id:{self.message_id} and (tag:spam or not tag:spam)']
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            threads = result.stdout.strip().split('\n')
            for thread_id in threads:
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-thread")
                    subprocess.Popen([viewer_path, thread_id.replace("thread:","")])
                except Exception as e:
                    display_error(self, "Error", f"Could not launch mail viewer: {e}")

    def view_source(self):
        try:
            viewer_dialog = MailSourceViewer(self.mail_file_path, self)
            viewer_dialog.exec()
            logging.info(f"Displayed raw mail source for: {self.mail_file_path.name}")
            
        except Exception as e:
            # Fail hard on unexpected creation error, or rely on the dialog's internal error handling
            raise RuntimeError(f"Failed to display raw mail source window: {e}")

    def get_tags(self):
        """Queries the notmuch database for tags of the current mail's message ID."""
        if not self.message_id:
            return []

        # try:
        #     command = ['notmuch', 'search', '--output=tags', '--format=text', f'id:{self.message_id} and (tag:spam or not tag:spam)']
        #     # command = ['notmuch', 'search', '--output=tags', '--format=text', f'id:{self.message_id}']
        #     result = subprocess.run(command, capture_output=True, text=True, check=True)            
        #     tags_list = [tag.strip() for tag in result.stdout.strip().split('\n') if tag.strip()]
        #     self.tags = sorted(tags_list)
        # except subprocess.CalledProcessError as e:
        #     display_error(
        #         "Notmuch Command Failed",
        #         f"An error occurred while running notmuch:\n\n{e.stderr}\n\nCommand was: {' '.join(command)}"
        #     )
        #     self.tags = []
        
        self.tags = get_tags_from_query( f'id:{self.message_id}', display_error )
        return self.tags

    def update_tags_ui(self):
        """Clears and rebuilds the UI to display the current tags and their states."""
        # Clear existing tag widgets
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Fetch the latest tags
        current_tags = set(self.get_tags())
        # Filter out special tags starting with '$'
        all_tags = {tag for tag in set(self.tags_state.keys()).union(current_tags) if not tag.startswith('$')}
        self.tags_state = {tag: tag in current_tags for tag in sorted(list(all_tags))}

        # Add a button for each tag, styled by its state
        for tag, is_attached in self.tags_state.items():
            tag_button = QPushButton(tag)
            tag_button.setFont(config.get_interface_font())
            if not is_attached:
                tag_button.setStyleSheet("QPushButton { color: gray; }")

            # Connect the button click to the toggle function
            tag_button.clicked.connect(lambda checked, t=tag: self.toggle_tag(t))
            self.tags_layout.addWidget(tag_button)

        # Add stretch to push the next button to the right
        self.tags_layout.addStretch()

        # Add a button to add new tags
        add_tag_button = QPushButton("Add tags")
        add_tag_button.clicked.connect(self.add_tag_dialog)
        self.tags_layout.addWidget(add_tag_button)

    def toggle_tag(self, tag):
        """Toggles a tag's state (add or remove)."""
        is_attached = self.tags_state.get(tag, False)
        if is_attached:
            self.remove_tag(tag)
        else:
            self.add_tag(tag)

    def add_tag_dialog(self):
        """Opens a dialog to add new tags."""
        text, ok = QInputDialog.getText(self, "Add Tags", "Enter tag(s) to add (comma-separated):")
        if ok and text:
            new_tags = [t.strip() for t in text.split(',')]
            for tag in new_tags:
                self.add_tag(tag)
            self.update_tags_ui()

    def remove_tag(self, tag):
        """Removes a tag from the current mail using the notmuch command."""
        try:
            command = ['notmuch', 'tag', f'-{tag}', f'tag:{tag} and id:{self.message_id}']
            subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info(f"Tag '{tag}' removed successfully.")
            self.update_tags_ui()
        except subprocess.CalledProcessError as e:
            display_error("Failed to Remove Tag", f"Failed to remove tag '{tag}':\n\n{e.stderr}")
        except FileNotFoundError:
            display_eerro("Notmuch Not Found", "The 'notmuch' command was not found. Please ensure it is installed and in your PATH.")
    
    def really_remove_tag(self, tag):
        self.tags_state.pop(tag)
        self.remove_tag(tag)

    def really_toggle_tag(self, tag):
        is_attached = self.tags_state.get(tag, False)
        if is_attached:
            self.really_remove_tag(tag)
        else:
            self.add_tag(tag)

    def add_tag(self, tag):
        """Adds a new tag to the current mail."""
        try:
            # Use the more reliable id:<message-id> query
            command = ['notmuch', 'tag', f'+{tag}', f'id:{self.message_id}']
            subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info(f"Tag '{tag}' added successfully.")
            self.update_tags_ui()
        except subprocess.CalledProcessError as e:
            display_error("Failed to Add Tag", f"Failed to add tag '{tag}':\n\n{e.stderr}")


    def handle_address_selection(self, address, is_selected):
        if is_selected:
            self.selected_addresses.add(address)
        else:
            self.selected_addresses.discard(address)
        print(f"Selected Addresses: {self.selected_addresses}")

    def _create_draft_and_open_editor(self, to_addrs, cc_addrs, subject_text, body_text, in_reply_to=None):
        """
        Creates a new mail draft and opens it in the external editor.
        """
        msg = email.message.EmailMessage()
        msg['From'] = self.my_first_identity()
        msg['To'] = ", ".join(to_addrs)
        if cc_addrs:
            msg['Cc'] = ", ".join(cc_addrs)

        msg['Subject'] = subject_text
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to

        msg.set_content(body_text)
        
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".eml") as temp_file:
                temp_file.write(msg.as_string())
                temp_path = temp_file.name

            # Assuming edit-mail.py is in the same directory.
            # You might need to adjust this path based on your project structure.
            editor_path = os.path.join(os.path.dirname(__file__), "edit-mail")
            if not os.path.exists(editor_path):
                QMessageBox.critical(self, "Error", f"Could not find mail editor at {editor_path}")
                return

            subprocess.Popen([editor_path, "--mail-file", temp_path])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create or open draft: {e}")

    def all_involved(self):
        sender = self.message.get("From")
        sender_addr = getaddresses([sender])[0][1] if sender else ""
        original_to = self.message.get("To", "")
        original_cc = self.message.get("Cc", "")
        all_recipients = {addr for name, addr in getaddresses([original_to, original_cc])}
        if sender:
            all_recipients.add(sender_addr)
        return all_recipients
        
    def all_my_identities(self):
        return { addr for addr in self.all_involved() if config.is_me( [addr] ) }

    def my_first_identity(self):
        dummy = list( self.all_my_identities() )
        if dummy:
            return dummy[0]
        return ""

    def all_other_identities(self):
        return { addr for addr in self.all_involved() if not config.is_me( [addr] ) }

    def get_quoted_body(self):
        """
        Extracts and quotes the body of the email.
        It prioritizes plain text, but falls back to converting HTML to plain text.
        """
        original_body = ""
        html_body = ""
        for part in self.message.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain' and not original_body:
                original_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
            elif content_type == 'text/html' and not html_body:
                html_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')

        if not original_body and html_body:
            original_body = html_to_plain_text(html_body)

        return textwrap.indent(original_body, '> ')

    def reply(self):
        """
        Creates a reply draft for the single sender.
        """
        if not self.message:
            return
        
        sender = self.message.get("From")
        sender_addr = getaddresses([sender])[0][1] if sender else ""
        
        from_addr = self.my_first_identity()

        to_list = [sender_addr]
        cc_list = list( self.all_my_identities() )
        
        original_subject = self.message.get("Subject", "")
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        quoted_body = self.get_quoted_body()
        
        self._create_draft_and_open_editor(to_list, cc_list, subject, f"\n\n{quoted_body}", self.message.get('Message-ID'))

    def reply_all(self):
        """
        Creates a reply-all draft for all original recipients and me.
        """
        if not self.message:
            return
        
        sender = self.message.get("From")
        sender_addr = getaddresses([sender])[0][1] if sender else ""
        to_list = [sender_addr]
       
        all_recipients = self.all_involved()
        all_recipients.discard(sender_addr)
        cc_list = list(all_recipients)
        
        original_subject = self.message.get("Subject", "")
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        quoted_body = self.get_quoted_body()

        self._create_draft_and_open_editor(to_list, cc_list, subject, f"\n\n{quoted_body}", self.message.get('Message-ID'))

    def follow_up(self):
        """
        Creates a draft with the same to and from as the original.
        """
        if not self.message:
            return
        
        to_list = { addr for name, addr in getaddresses( [self.message.get("To", "")] ) }
        cc_list = { addr for name, addr in getaddresses( [self.message.get("Cc", "")] ) }

        original_subject = self.message.get("Subject", "")
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        quoted_body = self.get_quoted_body()

        self._create_draft_and_open_editor(to_list, cc_list, subject, f"\n\n{quoted_body}", self.message.get('Message-ID'))

    def reply_to_selected(self):
        """
        Creates a reply draft for currently selected addresses.
        """
        if not self.selected_addresses:
            QMessageBox.warning(self, "No Addresses Selected", "Please click on at least one address to select it before replying.")
            return

        to_list = list(self.selected_addresses)
        cc_list = self.all_my_identities()
        
        original_subject = self.message.get("Subject", "")
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject
            
        quoted_body = self.get_quoted_body()
        
        self._create_draft_and_open_editor(to_list, cc_list, subject, f"\n\n{quoted_body}", self.message.get('Message-ID'))
    
    def compose_new(self):
        """
        Creates a new, empty mail draft.
        """
        to_list = list(self.selected_addresses)
        self._create_draft_and_open_editor(to_list, [], "", "")

    def do_forward(self, cc_all):
        """
        Creates a draft for forwarding the current mail.
        """
        if not self.message:
            return

        to_list = []
       
        if cc_all:
            all_recipients = self.all_involved()
            cc_list = list(all_recipients)
        else:
            cc_list = self.all_my_identities()

        # Prepare forwarded body
        headers = ["From", "To", "Cc", "Subject", "Date"]
        forwarded_body = f"---------- Forwarded message ----------\n"
        for h in headers:
            if self.message.get(h):
                forwarded_body += f"{h}: {self.message.get(h)}\n"
        forwarded_body += "\n"
        
        original_body = ""
        for part in self.message.walk():
            if part.get_content_type() == 'text/plain':
                original_body = part.get_content()
                break
        forwarded_body += original_body
        
        original_subject = self.message.get("Subject", "")
        if not original_subject.lower().startswith("fwd:"):
            subject = f"Fwd: {original_subject}"
        else:
            subject = original_subject

        self._create_draft_and_open_editor([], cc_list, subject, forwarded_body)


    def forward(self):
        self.do_forward( False )


    def forward_cc(self):
        self.do_forward( True )


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
            filename = attachment_part['filename']

            # Decode the base64 payload
            payload_bytes = base64.b64decode(attachment_part['payload'])

            with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as temp_file:
                temp_file.write(payload_bytes)
                temp_path = temp_file.name
                subprocess.run(["xdg-open", temp_path])
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open attachment: {e}")


    def handle_attachment_save_as(self, item):
        """Prompts the user to save the attachment to a chosen location."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part['filename']

            save_path, _ = QFileDialog.getSaveFileName(self, "Save Attachment", filename)
        
            if save_path:
                payload_bytes = base64.b64decode(attachment_part['payload'])
                with open(save_path, 'wb') as f:
                    f.write(payload_bytes)
                # QMessageBox.information(self, "Success", f"Attachment saved to:\n{save_path}")
            
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
        
    def show_mock_action(self, message):
        QMessageBox.information(self, "Action Mocked", message)


# --- 3. Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View a single mail file.")
    parser.add_argument("mail_file", help="The full path to the mail file to view.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    # app.setApplicationDisplayName( "Kubux Mail Client" )
    app.setApplicationName( "KubuxMailClient" )
    viewer = MailViewer(args.mail_file)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
