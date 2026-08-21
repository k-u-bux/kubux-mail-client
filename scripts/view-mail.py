#!/usr/bin/env python3

import sys
import mailparser
import argparse
import os
import tempfile
import email
from email import policy
from email.header import Header
from email.utils import getaddresses
import re
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl, QRegularExpression, QDate
from PySide6.QtGui import QFont, QKeySequence, QAction, QTextCursor, QTextCharFormat, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTextBrowser, QTextEdit, QHBoxLayout,
    QPushButton, QListWidget, QSplitter, QMessageBox, QMenu, QGroupBox,
    QFormLayout, QLabel, QInputDialog, QScrollArea, QDialog, QDialogButtonBox,
    QFileDialog, QSizePolicy, QAbstractItemView, QCalendarWidget
)

from notmuch_api import find_matching_messages, find_matching_threads, apply_tag_to_query, get_tags_from_query, update_unseen_from_query

import logging
import subprocess
import json
import textwrap
import base64
import hashlib
import mimetypes
import secrets

from config import config, Config
from common import display_error, html_to_plain_text, get_db_path, get_run_method, show_window, run_gui_app, tag_dialog, decision_dialog
from watcher import DirectoryEventHandler
from header_widget import MailHeaderWidget

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class SafeTextBrowser(QTextBrowser):
    """QTextBrowser that blocks remote (http/https) resource loading.

    The remote-content policy is read from config:
      - "enable":   load remote resources silently
      - "disable":  block remote resources silently
      - "ondemand": prompt the user once per instance (per mail) the first
                    time a remote resource is requested, then remember the
                    decision for the rest of that mail.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.load_remote_decision = None  # None = undecided, True = load, False = don't

    def loadResource(self, resource_type, url):
        if url.scheme().lower() in ("http", "https"):
            mode = config.get_remote_content_mode()
            if mode == "enable":
                return super().loadResource(resource_type, url)
            if mode == "disable":
                return None  # always block, no prompt
            # ondemand: the decision is made in display_message (outside the
            # paint event, where a modal dialog would corrupt the painter).
            if not self.load_remote_decision:
                return None
        return super().loadResource(resource_type, url)

def _decode_text_payload(payload, charset):
    """Decode a text/plain or text/html payload per the configured policy.

    No charset -> UTF-8.  Declared charset -> used as-is.  If that fails
    (unknown name or invalid byte sequence) -> latin-1, which never fails.
    """
    if not payload:
        return ""
    try:
        return payload.decode(charset or "utf-8")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("latin-1")


def is_attachment(message):
    """A message is an attachment if it embeds another email (message/*)."""
    return message.get_content_maintype() == 'message'


def _extract_body(html):
    """Return the inner HTML of the <body> element, or the input unchanged
    if there is no <body> (i.e. it is an HTML fragment)."""
    m = re.search(r'<body[^>]*>(.*)</body>', html, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else html


def _normalize_message_id(raw):
    """Normalize a Message-ID the same way notmuch does.

    notmuch strips exactly one leading '<' and one trailing '>' from the
    raw header value (lib/message-file.c).  A naive .strip('<>') would
    remove *all* brackets, which breaks mails whose Message-ID has
    doubled brackets (e.g. '<<...>'), because the resulting id would not
    match the one notmuch stored.
    """
    if not raw:
        return raw
    raw = raw.strip()
    if raw.startswith('<'):
        raw = raw[1:]
    if raw.endswith('>'):
        raw = raw[:-1]
    return raw


def custom_walk(message):
    """Walk the message tree like walk(), but prune message attachment
    subtrees so forwarded/attached emails are not inlined into the body."""
    yield message
    if message.is_multipart() and not is_attachment(message):
        for subpart in message.get_payload():
            yield from custom_walk(subpart)


class MailSourceViewer(QDialog):
    """A simple dialog to display the raw content of the mail file."""
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window)
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


class MailViewer(QMainWindow):
    def __init__(self, mail_file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Mail Client - Viewer")
        self.resize(QSize(1024, 768))

        self.mail_file_path = Path(mail_file_path).expanduser()
        self.tags_state = {}
        self.show_headers = True
        self.attachments = []
        self.message_id = None
        self.message = None
        self.mail_body = ""
        self.mail_html = ""
        self.has_text_body = False
        self.has_html_body = False
        self.parse_mail_file()
        self.force_html = False
        self.shows_html = not self.has_text_body

        self.process_initial_tags()
        self.setup_ui()
        self.setup_key_bindings()
        self.display_message()

        self.dir_watcher = DirectoryEventHandler( self.update_tags_ui )
        self.dir_watcher.watch( get_db_path() )

        Config.register_callback(self._on_config_changed)

    def render_html_button ( self ):
        self.toggle_html_button.setFont(config.get_interface_font())
        if self.shows_html:
            self.toggle_html_button.setText("Text")
            if not self.has_text_body:
                self.toggle_html_button.setStyleSheet("QPushButton { color: gray; }")
            else:
                self.toggle_html_button.setStyleSheet("QPushButton { color: black; }")
        else:
            self.toggle_html_button.setText("Html")
            if not self.has_html_body:
                self.toggle_html_button.setStyleSheet("QPushButton { color: gray; }")
            else:
                self.toggle_html_button.setStyleSheet("QPushButton { color: black; }")

    def toggle_force_html ( self ):
        self.force_html = not self.force_html
        self.shows_html = ( self.force_html and self.has_html_body ) or not self.has_text_body
        self.render_html_button()
        self.display_message()

    def parse_mail_file(self):
        """Parses a real email file from the local filesystem."""
        if not self.mail_file_path.exists():
            logging.error(f"Mail file {self.mail_file_path} does not exist.")
            raise FileNotFoundError(f"Mail file does not exist: {self.mail_file_path}")
        try:
            mail = mailparser.parse_from_file(self.mail_file_path)
            with open(self.mail_file_path, 'rb') as f:
                self.message = email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            logging.error(f"Failed to parse mail file: {e}")
            raise RuntimeError(f"Failed to parse mail file {self.mail_file_path}: {e}") from e
        # print("parsing message")
        for part in custom_walk(self.message):
            if part.get_content_type() == 'text/plain':
                body_text = _decode_text_payload(part.get_payload(decode=True), part.get_content_charset())
                if self.mail_body:
                    self.mail_body += "\n\n" + body_text
                else:
                    self.mail_body = body_text
                self.has_text_body = True
            if part.get_content_type() == 'text/html':
                body_html = _decode_text_payload(part.get_payload(decode=True), part.get_content_charset())
                # Take only the <body> inner content so joining several
                # full HTML documents (each with their own <html>/<body>)
                # does not produce invalid HTML.
                body_html = _extract_body(body_html)
                sanitized_html = self.sanitize_html_fonts(body_html)
                if self.mail_html:
                    self.mail_html += "<br><br>" + sanitized_html
                else:
                    self.mail_html = sanitized_html
                self.has_html_body = True
        self.attachments = mail.attachments 
        # unfortunately not all mail have only one id
        if isinstance(mail.message_id, list):
            self.message_id = _normalize_message_id(mail.message_id[0]) if mail.message_id else None
        else:
            self.message_id = _normalize_message_id(mail.message_id) if mail.message_id else None
        # RFC 5322 §3.6.4: Message-ID is SHOULD, not MUST.  A mail without
        # one is valid.  notmuch indexes such mails under a synthetic id
        # "notmuch-sha1-<sha1_of_entire_file>" (lib/database.cc).  Derive
        # the same id so tags/threads work for id-less mails too.
        if not self.message_id:
            with open(self.mail_file_path, 'rb') as f:
                sha1 = hashlib.sha1(f.read()).hexdigest()
            self.message_id = f"notmuch-sha1-{sha1}"
        print(f"Message-ID = {self.message_id}")


    def process_initial_tags(self):
        """
        Manages initial tag state. If a mail has the $unseen tag,
        it is silently replaced with the $unused tag.
        """
        current_tags = self.get_tags()
        if '$unseen' in current_tags:
            logging.info("Found '$unseen' tag. Silently replacing with '$unused'.")
            command = ['notmuch', 'tag', '-$unseen', '+$unused', f'id:{self.message_id}']
            subprocess.run(command, check=True, capture_output=True, text=True)


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
        self.compose_button.setFont(config.get_interface_font())
        self.compose_menu = QMenu(self)
        self.compose_menu.setFont(config.get_menu_font())
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
        self.tags_button.setFont(config.get_interface_font())
        self.tags_menu = QMenu(self)
        self.tags_menu.setFont(config.get_menu_font())
        for tag in config.get_tags():
            l = lambda checked, dummy=f"{tag}": self.toggle_tag( dummy )
            action = self.tags_menu.addAction(f"+/- {tag}")
            action.triggered.connect( l )
        self.tags_menu.addSeparator()
        for tag in config.get_status_tags():
            l = lambda checked, dummy=f"{tag}": self.toggle_tag( dummy )
            action = self.tags_menu.addAction(f"+/- {tag}")
            action.triggered.connect( l )
        self.tags_menu.addSeparator()
        self.tags_menu.addAction("+/- spam").triggered.connect( lambda: self.toggle_tag("spam") )
        self.tags_menu.addAction("+/- deleted").triggered.connect( lambda: self.toggle_tag("deleted") )
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
        
        self.toggle_html_button =  QPushButton("Html")
        self.toggle_html_button.clicked.connect(self.toggle_force_html)
        top_bar_layout.addWidget(self.toggle_html_button)
        self.render_html_button()

        top_bar_layout.addStretch()

        self.postpone_button = QPushButton("Postpone")
        top_bar_layout.addWidget(self.postpone_button)
        self.update_postpone_button()

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
        self.mail_content = SafeTextBrowser()
        self.mail_content.setFont(config.get_text_font())
        self.mail_content.setReadOnly(True)
        self.mail_content.setOpenLinks(False) 
        self.splitter.addWidget(self.mail_content)
        self.mail_content.anchorClicked.connect(self.handle_link_clicked)
        self.mail_content.setTextInteractionFlags(Qt.TextBrowserInteraction)
        
        # Add a context menu for clipboard actions and view raw
        self.mail_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mail_content.customContextMenuRequested.connect(self.show_content_context_menu)

        # Attachments list
        if self.attachments:
            self.attachments_list = QListWidget()
            self.attachments_list.setFont(config.get_attachment_font())
            self.attachments_list.setMinimumHeight(40)
            self.attachments_list.setMaximumHeight(200)
            self.attachments_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.attachments_list.setMouseTracking(True)
            self.attachments_list.setStyleSheet("""
                QListWidget::item:hover {
                    background-color: #418be6; /* Your preferred blue */
                    color: white;
                }
            """)
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
            "edit_tags": self.edit_tags_action,
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

        if self.shows_html:
            # Prompt for remote content here, before rendering, so the modal
            # dialog runs outside the paint event (a modal dialog during
            # loadResource corrupts the painter and segfaults).  Only prompt
            # in "ondemand" mode; "enable"/"disable" are handled silently by
            # loadResource.
            if (config.get_remote_content_mode() == "ondemand"
                    and self.mail_content.load_remote_decision is None
                    and self._html_has_remote_content(self.mail_html)):
                self.mail_content.load_remote_decision = decision_dialog(
                    self, "Remote content",
                    "This message references remote content (e.g. images).\nLoad it?",
                    "Load remote content", "Don't load")
            self.mail_content.setHtml(self.mail_html)
        else:
            cursor = self.mail_content.textCursor()
            cursor.setCharFormat(QTextCharFormat())
            self.mail_content.setTextCursor(cursor)
            self.mail_content.setPlainText(self.mail_body)
            # For plain text, we need to detect URLs manually
            self.highlight_urls_in_plain_text()
        
    def _html_has_remote_content(self, html):
        """Return True if the HTML auto-loads remote content.

        Matches only attributes that fetch content without user interaction
        (src, srcset, background, poster).  Ordinary <a href="..."> links are
        excluded: they are only fetched when clicked.
        """
        return bool(re.search(r'\b(?:src|srcset|background|poster)\s*=\s*["\']https?://',
                              html, re.IGNORECASE))

    def _strip_trailing_punct(self, url: str):
        """Return (trimmed_url, chars_removed).

        The greedy URL regex can swallow trailing punctuation (e.g. a
        period, comma or closing paren).  Trim that punctuation from the
        value used for the click target and report how many characters
        were removed so the caller can shrink the visible (colored) range
        to match.
        """
        orig_len = len(url)
        url = url.rstrip('.,;:!?)]}')
        # Only strip a trailing quote if it is unpaired
        if url.endswith('"') and url.count('"') % 2 == 1:
            url = url[:-1]
        if url.endswith("'") and url.count("'") % 2 == 1:
            url = url[:-1]
        return url, orig_len - len(url)

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

            # Trim trailing punctuation from the click target, and shrink
            # the visible (colored) range to match.
            href, removed = self._strip_trailing_punct(url)
            # www. links lack a scheme -> make them absolute so they aren't
            # resolved against the guessed base URL in handle_link_clicked.
            if href.startswith("www."):
                href = "https://" + href
            end -= removed

            # Select the text range
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)

            match_format = QTextCharFormat(base_url_format)
            match_format.setAnchorHref(href)

            # Apply URL format
            cursor.setCharFormat(match_format)

            # Update the cursor position to search for the next match
            cursor.setPosition(end)
    

    def handle_link_clicked(self, url):
        """Handle clicking on a URL by opening it in the default browser."""
        if isinstance(url, str):
            url = QUrl(url)
            
        # Relative URLs cannot be resolved safely: the base would have to be
        # guessed from spoofable headers (From/Reply-To/List-Post/List-Id),
        # which an attacker fully controls. Drop them instead.
        if url.isRelative():
            QMessageBox.warning(
                self,
                "Relative URL",
                "This message contains a relative link, which cannot be opened safely.\n\n"
                f"Link: {url.toString()}"
            )
            return
        
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
        """Remove layout-breaking and unscalable constructs from HTML.

        Strips <style> and <script> blocks (a <style> block can e.g. hide
        the whole message with 'body { display: none; }' or force a huge
        table width), then removes hardcoded font-size declarations so Qt
        can scale the font.  Qt's QTextBrowser does not run JS, so
        <script> is inert anyway.
        """
        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content,
                              flags=re.IGNORECASE | re.DOTALL)
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content,
                              flags=re.IGNORECASE | re.DOTALL)
        # This regex finds any font-size declaration in a style attribute and removes it.
        return re.sub(r'font-size:\s*[^;"]+;?', '', html_content, flags=re.IGNORECASE)

    def delete_message(self):
        self.add_tag("deleted")
        self.close()

    def update_postpone_button(self):
        """Sets button text/action based on whether message is currently postponed."""
        try:
            self.postpone_button.clicked.disconnect()
        except RuntimeError:
            pass  # no connections yet

        tags = self.get_tags()
        if 'postponed' in tags:
            self.postpone_button.setText("Unpostpone")
            self.postpone_button.clicked.connect(self.unpostpone_message)
        else:
            self.postpone_button.setText("Postpone")
            self.postpone_button.clicked.connect(self.postpone_message)

    def unpostpone_message(self):
        """Removes postponed + $until tags, flips button back to Postpone."""
        import re
        tags = self.get_tags()
        until_tag = None
        for tag in tags:
            if tag.startswith('$until:'):
                until_tag = tag
                break

        try:
            cmd = ['notmuch', 'tag', '-postponed', f'id:{self.message_id}']
            if until_tag:
                cmd.insert(2, f'-{until_tag}')
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logging.info(f"Unpostponed message {self.message_id}")
        except subprocess.CalledProcessError as e:
            display_error(self, "Failed to Unpostpone", f"Failed to unpostpone message:\n\n{e.stderr}")
            return

        self.update_postpone_button()
        self.update_tags_ui()

    def postpone_message(self):
        """Opens a calendar dialog to pick a date, then adds postpone + $until tags."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Postpone Until")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        label = QLabel("Select date until which to postpone:")
        layout.addWidget(label)

        calendar = QCalendarWidget()
        tomorrow = QDate.currentDate().addDays(1)
        calendar.setSelectedDate(tomorrow)
        calendar.setMinimumDate(QDate.currentDate().addDays(1))
        layout.addWidget(calendar)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() != QDialog.Accepted:
            return

        selected_date = calendar.selectedDate()
        until_str = selected_date.toString("yyyy-MM-dd")

        try:
            subprocess.run(
                ['notmuch', 'tag', '+postponed', f'+$until:{until_str}', f'id:{self.message_id}'],
                check=True, capture_output=True, text=True
            )
            logging.info(f"Postponed message {self.message_id} until {until_str}")
        except subprocess.CalledProcessError as e:
            display_error(self, "Failed to Postpone", f"Failed to postpone message:\n\n{e.stderr}")
            return

        self.update_postpone_button()
        self.update_tags_ui()

    def view_thread(self):
        if self.message_id:
            command = ['notmuch', 'search', '--output=threads', '--format=text', f'id:{self.message_id} and (tag:spam or not tag:spam) and (tag:postponed or not tag:postponed)']
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            threads = result.stdout.strip().split('\n')
            for thread_id in threads:
                try:
                    get_run_method( "view-thread" )( thread_id.replace("thread:","") )
                except Exception as e:
                    display_error(self, "Error", f"Could not launch mail viewer: {e}")

    def view_source(self):
        try:
            viewer_dialog = MailSourceViewer(self.mail_file_path)
            viewer_dialog.setAttribute(Qt.WA_DeleteOnClose)
            mail_source_viewers.append(viewer_dialog)
            viewer_dialog.destroyed.connect(lambda: mail_source_viewers.remove(viewer_dialog))
            viewer_dialog.show()
            logging.info(f"Displayed raw mail source for: {self.mail_file_path.name}")
            
        except Exception as e:
            # Fail hard on unexpected creation error, or rely on the dialog's internal error handling
            raise RuntimeError(f"Failed to display raw mail source window: {e}")

    def get_tags(self):
        """Queries the notmuch database for tags of the current mail's message ID."""
        return get_tags_from_query( f'id:{self.message_id}', lambda *args: display_error( self, *args) )

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
        all_tags = {tag for tag in set(config.get_status_tags()).union( 
            set(self.tags_state.keys()) ).union(current_tags) if not tag.startswith('$')}
        status_tags = sorted( list( set( all_tags ).intersection( set( config.get_status_tags() + [ "unread" ] ) ) ) )
        non_status_tags = sorted( list( set( all_tags ).difference( set( config.get_status_tags() + [ "unread" ] ) ) ) )
                                                  
        self.tags_state = {tag: tag in current_tags for tag in non_status_tags + status_tags}

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

    def edit_tags_action(self):
        """Opens the shared tag dialog and applies the +/-tag ops to this mail."""
        tags = tag_dialog(self)
        for tag in tags:
            if tag.startswith('+'):
                self.add_tag(tag[1:])
            elif tag.startswith('-'):
                self.remove_tag(tag[1:])

    def remove_tag(self, tag):
        """Removes a tag from the current mail using the notmuch command."""
        try:
            command = ['notmuch', 'tag', f'-{tag}', f'tag:{tag} and id:{self.message_id}']
            subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info(f"Tag '{tag}' removed successfully.")
            self.update_tags_ui()
        except subprocess.CalledProcessError as e:
            display_error(self, "Failed to Remove Tag", f"Failed to remove tag '{tag}':\n\n{e.stderr}")
    
    def add_tag(self, tag):
        """Adds a new tag to the current mail."""
        try:
            # Use the more reliable id:<message-id> query
            command = ['notmuch', 'tag', f'+{tag}', f'id:{self.message_id}']
            subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info(f"Tag '{tag}' added successfully.")
            self.update_tags_ui()
        except subprocess.CalledProcessError as e:
            display_error(self, "Failed to Add Tag", f"Failed to add tag '{tag}':\n\n{e.stderr}")


    def _create_draft_and_open_editor(self, to_addrs, cc_addrs, subject_text, body_text, in_reply_to=None):
        """
        Creates a new mail draft and opens it in the external editor.
        """
        msg = email.message.EmailMessage()
        msg['From'] = self.my_first_identity()
        msg['To'] = ", ".join(to_addrs)
        if cc_addrs:
            msg['Cc'] = ", ".join(cc_addrs)

        msg['Subject'] = str(Header(subject_text, 'utf-8'))
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to

        msg.set_content(body_text)
        
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".eml") as temp_file:
                temp_file.write(msg.as_string())
                temp_path = temp_file.name
            get_run_method( "edit-mail" )( temp_path )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create or open draft: {e}")

    def reply_to_addr(self):
        """Returns the Reply-To address if present, else the From address."""
        reply_to = self.message.get("Reply-To")
        if reply_to:
            return getaddresses([reply_to])[0][1]
        sender = self.message.get("From")
        return getaddresses([sender])[0][1] if sender else ""

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

    def get_body(self):
        """
        Extracts the body of the email.
        It prioritizes plain text, but falls back to converting HTML to plain text.
        """
        original_body = ""
        html_body = ""
        for part in custom_walk(self.message):
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                body_text = _decode_text_payload(part.get_payload(decode=True), part.get_content_charset())
                if original_body:
                    original_body += "\n\n" + body_text
                else:
                    original_body = body_text
            elif content_type == 'text/html':
                body_html = _decode_text_payload(part.get_payload(decode=True), part.get_content_charset())
                if html_body:
                    html_body += "\n\n" + body_html
                else:
                    html_body = body_html
        if not original_body and html_body:
            original_body = html_to_plain_text( html_body )
        return original_body

    def get_quoted_body(self):
        original_body = self.get_body()
        lines = original_body.splitlines()
        # Per RFC 3676 the signature separator is a line consisting of exactly
        # "-- " (two hyphens + one space) at column 0.
        for i, line in enumerate(lines):
            if line == "-- ":
                # Only treat it as a separator if something follows.
                if i + 1 < len(lines):
                    lines = lines[:i]
                break
        return textwrap.indent("\n".join(lines), '> ', (lambda line: True))

    def reply(self):
        """
        Creates a reply draft for the single sender.
        """
        if not self.message:
            return
        
        sender_addr = self.reply_to_addr()
        
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
        
        sender_addr = self.reply_to_addr()
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
        selected = self.headers_group_box.get_selected_addresses()
        if not selected:
            QMessageBox.warning(self, "No Addresses Selected", "Please right-click on at least one address to select it before replying.")
            return

        to_list = list(selected)
        cc_list = list(self.all_my_identities())
        
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
        selected = self.headers_group_box.get_selected_addresses()
        to_list = list(selected) if selected else []
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
        
        forwarded_body += self.get_body()
        
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
            menu.setFont(config.get_menu_font())

            open_action = QAction("Open", self)
            open_action.triggered.connect(lambda: self.handle_attachment_open(item))
            menu.addAction(open_action)
            
            save_as_action = QAction("Save As...", self)
            save_as_action.triggered.connect(lambda: self.handle_attachment_save_as(item))
            menu.addAction(save_as_action)
            
            menu.exec(self.attachments_list.mapToGlobal(pos))


    def get_attachment_payload(self, part):
        if part['binary']:
            return base64.b64decode(part['payload'])
        else:
            # CONVERSION: The payload is a string (str), so we must encode it to bytes.
            # mailparser decodes the payload with the part's charset already;
            # re-encode with that same charset to restore the original bytes.
            # (The dict key is 'charset', not 'encoding'.)
            text_payload_str = part['payload']
            if not isinstance(text_payload_str, str):
                raise TypeError("Expected attachment payload to be a string when 'binary' is false.")
            encoding = part.get('charset') or 'utf-8'
            return text_payload_str.encode(encoding)


    def handle_attachment_open(self, item):
        """Saves the attachment to a temporary file and opens it."""
        try:
            part_index = self.attachments_list.row(item)
            attachment_part = self.attachments[part_index]
            filename = attachment_part.get('filename')
            if not filename:
                # No filename (common for inline parts) — derive a random one
                # with an extension from the content-type.
                ext = mimetypes.guess_extension(attachment_part.get('mail_content_type', '')) or '.bin'
                filename = f"attachment_{secrets.token_hex(4)}{ext}"

            # Decode the base64 payload
            payload_bytes = self.get_attachment_payload( attachment_part )

            # Sanitize the filename: keep only the basename, strip path
            # separators and null bytes (path-traversal protection).
            safe_name = os.path.basename(filename.replace("\\", "/"))
            safe_name = safe_name.replace("\x00", "").strip()
            # Short hash of the original filename keeps the suffix unique even
            # if two attachments share a basename after sanitization.
            name_hash = hashlib.sha1(filename.encode("utf-8", "replace")).hexdigest()[:8]

            with tempfile.NamedTemporaryFile(suffix=f"_{name_hash}_{safe_name}", delete=False) as temp_file:
                temp_file.write(payload_bytes)
                temp_file.flush()
                os.fsync(temp_file.fileno()) # Force write to disk
                temp_path = temp_file.name
                stats = os.stat(temp_path)
                print(f"DEBUG: File size on disk: {stats.st_size} bytes")
                mime_check = subprocess.run(["xdg-mime", "query", "filetype", temp_path], 
                                            capture_output=True, text=True)
                print(f"DEBUG: Detected MIME = {mime_check.stdout.strip()}")
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
                payload_bytes = self.get_attachment_payload( attachment_part )
                with open(save_path, 'wb') as f:
                    f.write(payload_bytes)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save attachment: {e}")


    def show_content_context_menu(self, pos):
        """Creates a context menu for the mail content area."""
        menu = QMenu(self)
        menu.setFont(config.get_menu_font())
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.mail_content.copy)
        menu.addAction(copy_action)

        menu.exec(self.mail_content.mapToGlobal(pos))
        
    def _on_config_changed(self):
        """Reapply fonts and relayout after config changes."""
        central_widget = self.centralWidget()
        if central_widget:
            central_widget.setFont(config.get_interface_font())
        self.compose_button.setFont(config.get_interface_font())
        self.compose_menu.setFont(config.get_menu_font())
        self.tags_button.setFont(config.get_interface_font())
        self.tags_menu.setFont(config.get_menu_font())
        self.view_thread_button.setFont(config.get_interface_font())
        self.view_source_button.setFont(config.get_interface_font())
        self.toggle_header_visibility_button.setFont(config.get_interface_font())
        self.toggle_html_button.setFont(config.get_interface_font())
        self.postpone_button.setFont(config.get_interface_font())
        self.delete_button.setFont(config.get_interface_font())
        self.quit_button.setFont(config.get_interface_font())
        self.mail_content.setFont(config.get_text_font())
        if hasattr(self, 'attachments_list') and self.attachments_list:
            self.attachments_list.setFont(config.get_attachment_font())
        self.headers_group_box.update_fonts()
        # Rebuild tags UI to pick up new interface font
        self.update_tags_ui()

    def closeEvent(self, event):
        """Clean up the directory watcher when closing."""
        logging.info(f"Closing mail viewer for mail file = {self.mail_file_path}")
        Config.unregister_callback(self._on_config_changed)
        self.dir_watcher.stop()
        super().closeEvent(event)


# --- Main Entry Point ---

mail_source_viewers = []

def run ( args_mail_file ):
    try:
        viewer = MailViewer( args_mail_file )
    except Exception as e:
        logging.error(f"Could not open mail viewer: {e}")
        QMessageBox.critical(None, "Cannot Open Mail", f"Could not open the mail file:\n\n{e}")
        return
    show_window( viewer )

def main():
    parser = argparse.ArgumentParser(description="View a single mail file.")
    parser.add_argument("mail_file", help="The full path to the mail file to view.")
    args = parser.parse_args()
    run_gui_app( run, args.mail_file )

if __name__ == "__main__":
    main()

# end of file
