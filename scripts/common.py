from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QDialogButtonBox, QLabel, QTextEdit,
    QCheckBox, QAbstractItemView, QMenu, QToolTip, QInputDialog,
)
from PySide6.QtCore import Qt, QSize, QPoint, QObject, QTimer, QMetaObject
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging
import sys
from pathlib import Path
from datetime import datetime
import secrets
import os
import subprocess
import shutil
import tempfile
import email
from email import policy
from config import config
import re
import html2text
from bs4 import BeautifulSoup, Comment
import html
import shlex
from email.utils import parseaddr
from datetime import datetime, timezone
from importlib import import_module
from html2text import html2text

def get_run_method ( mod_name ):
    return import_module( mod_name ).run


def setup_tooltip_font():
    """Set the tooltip font to match the popup font."""
    font = config.get_popup_font()
    QToolTip.setFont(font)
    # Set at app level for the QToolTip widget class — this is what actually sticks
    app = QApplication.instance()
    if app:
        app.setFont(font, "QToolTip")

def output_of_cmd(cmd_str: str) -> str:
    """
    Executes a shell command and returns its stdout as a stripped string.
    Fails hard on any error or non-zero exit code.
    """
    args = shlex.split(cmd_str)
    output = subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
    return output.strip()

def get_db_path():
    return ( output_of_cmd( "notmuch config get database.path" ) )

def font_to_html_style(font: QFont) -> str:
    family = font.family()
    size = font.pointSize()
    weight = "bold" if font.bold() else "normal"
    style = "italic" if font.italic() else "normal"
    return (f"font-family: '{family}'; "
            f"font-size: {size}pt; "
            f"font-weight: {weight}; "
            f"font-style: {style};")

def create_summary_text( authors, subject, tags ) -> str:
    return (
        f"<div style=\"white-space: pre-wrap;\">"
        f"<p>{html.escape(authors)}</p><p>{html.escape(subject)}</p><p>{html.escape(tags)}</p>"
        f"</div>"
    )

def html_to_plain_text(html_content: str) -> str:
    if not html_content:
        return ""

    return html2text( html_content )

    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Cleanup non-content tags
    for element in soup(["script", "style", "head", "meta", "title"]):
        element.decompose()

    # 2. Transform links: <a>label</a> -> <a>label (url)</a>
    for a in soup.find_all('a', href=True):
        url = a['href']
        label = a.get_text(strip=True)
        if url.startswith('mailto:'):
            url = url[7:]
        
        # Only append URL if it's not identical to the label
        if label != url:
            new_content = f"{label} ({url})"
            a.string = new_content

    # 3. Structural whitespace: Insert newlines before block elements
    for tag in soup.find_all(['p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3']):
        tag.insert_before('\n')

    # 4. Extract text with a separator to prevent word-clumping
    text = soup.get_text(separator=' ')

    # 5. Decode all entities and normalize whitespace
    text = html.unescape(text)
    
    # Procedural cleanup of whitespace and empty lines
    lines = (line.strip() for line in text.splitlines())
    return '\n'.join(line for line in lines if line)

def html_to_plain_text_b(html_content: str) -> str:
    if not html_content:
        return ""

    # Parse with the built-in parser
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Kill all script, style, and font tags
    # Also kill 'head' and 'meta' if they exist in the blob
    for element in soup(["script", "style", "font", "head", "meta", "title"]):
        element.decompose()

    # 2. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 3. Handle line breaks: 
    # Insert a literal newline before every block-level tag to prevent words from sticking
    for tag in soup.find_all(['p', 'div', 'br', 'li', 'tr']):
        tag.insert_before('\n')

    # 4. Extract text
    # separator=' ' ensures inline tags don't merge words: <span>A</span><span>B</span> -> A B
    text = soup.get_text(separator=' ')

    # 5. Final Cleanup
    # html.unescape handles EVERY entity (&trade;, &#9993;, etc.)
    text = html.unescape(text)

    # Consolidate whitespace
    lines = (line.strip() for line in text.splitlines())
    # Drop empty lines but keep single breaks between paragraphs
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return '\n'.join(chunk for chunk in chunks if chunk)

def html_to_plain_text_stupid(html_content: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False  # Keep URLs in the text
    h.body_width = 0        # Don't wrap lines automatically
    return h.handle(html_content).strip()

def html_to_plain_text_hack(html_content):
    """
    Converts a string of HTML content to plain text.
    
    This function strips HTML tags and cleans up resulting whitespace.
    It is designed for simple conversions, like for email quoting, and may
    not perfectly render complex HTML structures.
    """
    if not html_content:
        return ""
    
    # 1. Remove script and style elements
    text = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Replace <br> and <p> with newlines for better structure
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    
    # 3. Strip all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # 4. Decode HTML entities
    # Note: A more robust solution might use html.unescape, but for now we handle common ones.
    text = text.replace('&nbsp;', ' ').replace('&', '&').replace('<', '<').replace('>', '>')
    
    # 5. Consolidate whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def extract_email_text(file_path: Path) -> str:
    """
    Extracts the subject, from, to, cc, and plain text body from an email file
    to use for classification.
    """
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = msg.get("Subject", "")
        from_field = msg.get("From", "")
        to_field = msg.get("To", "")
        cc_field = msg.get("Cc", "")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain':
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()

        return f"Subject: {subject}\nFrom: {from_field}\nTo: {to_field}\nCc: {cc_field}\n\n{body}"
    except Exception as e:
        sys.stderr.write(f"Error processing {file_path}: {e}\n")
        return ""

def create_date_item ( timestamp ):
    """Creates a sortable QTableWidgetItem for the date."""
    if not isinstance(timestamp, (int, float)):
        timestamp = 0
        
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    date_string = dt.strftime("%Y-%m-%d %H:%M")
    
    item = QTableWidgetItem(date_string)
    item.setData(Qt.ItemDataRole.UserRole, timestamp)
    return item

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

def display_error(parent, title, message):
    dialog = CopyableErrorDialog( title, message, parent=parent )
    dialog.exec()

# drafts
def create_draft(parent, identity_dict):
    """Creates a new draft file for the given identity."""
    try:
        # Use the 'drafts' path from the identity, or fall back to the default
        drafts_path_str = identity_dict.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
        drafts_path = Path(drafts_path_str).expanduser()
        template_path_str = identity_dict.get('template', "~/.config/kubux-mail-client/draft_template.eml")
        template_path = Path(template_path_str).expanduser()

        # Create the directory if it doesn't exist
        drafts_path.mkdir(parents=True, exist_ok=True)
        
        # Create a unique filename with a timestamp and a random component
        timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        random_component = secrets.token_hex(16)
        draft_filename = f"{timestamp_str}-{random_component}.eml"
        draft_path = drafts_path / draft_filename
        
        # Create the draft file by copying the template or creating a minimal one
        if template_path.is_file():
            shutil.copyfile(template_path, draft_path)
            logging.info(f"Created new draft file at {draft_path} from template.")
        else:
            logging.warning(f"Template file not found at {template_path}. Creating a minimal draft instead.")
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(f"From: {identity_dict['name']} <{identity_dict['email']}>\n")
                f.write("To: \n")
                f.write(f"Cc: {identity_dict['name']} <{identity_dict['email']}>\n")
                f.write("Subject: \n\n")
        get_run_method( "edit-mail" )( str(draft_path) )
        logging.info(f"Launched mail editor for new draft: {draft_path}")
    except Exception as e:
        logging.error(f"Failed to create draft or launch editor: {e}")
        display_error(parent, "Action Error", f"Could not complete the action:\n\n{e}")

def create_new_mail_menu(parent):
    """Creates and displays a menu for selecting an email identity."""
    identities = config.get_identities()
    if not identities:
        display_error(parent, "Identities not found", "No email identities are configured. Please check your config file.")
        return

    menu = QMenu(parent)
    menu.setFont(config.get_menu_font())
    for identity in identities:
        action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
        action = menu.addAction(action_text)
        action.triggered.connect(lambda checked, i=identity: create_draft(parent,i))

    # Get the position of the New Mail button and show the menu
    button_pos = parent.new_mail_button.mapToGlobal(QPoint(0, parent.new_mail_button.height()))
    menu.exec(button_pos)

def launch_drafts_manager(parent, identity_dict):
    """Launches the drafts manager script for a given identity's drafts folder."""
    try:
        drafts_path_str = identity_dict.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
        drafts_path = str( Path(drafts_path_str).expanduser() )
        drafts_email = identity_dict.get('email', "" )
        get_run_method( "open-drafts" )( drafts_path, drafts_email )
        logging.info(f"Launched drafts manager for directory: {drafts_path}")
    except Exception as e:
        logging.error(f"Failed to launch drafts manager: {e}")
        display_error(parent, "Launch Error", f"Could not launch open-drafts.py:\n\n{e}")

def normalize_address (addr_string):
    _, extracted_addr = parseaddr(addr_string)
    return extracted_addr.lower()

def match_address (header, address):
    return ( normalize_address( header ) == normalize_address( address ) )

def find_identity( sender_email ):
    if not sender_email:
        return None
    sender_email = sender_email.casefold()
    for i in config.get_identities():
        if sender_email == ( i.get('email') or "" ).casefold():
            return i
    return None

# --- Shared GUI boilerplate (used by all GUI scripts) ---

_keep_alive = []

def show_window(widget):
    """Show a top-level widget, keeping a reference so it isn't garbage-collected."""
    _keep_alive.append(widget)
    widget.setAttribute(Qt.WA_DeleteOnClose)
    widget.destroyed.connect(lambda: _keep_alive.remove(widget))
    widget.show()

def run_gui_app(run_func, *args):
    """Set up the QApplication and run the given run_func(*args) inside it."""
    app = QApplication(sys.argv)
    from event_filter import global_drag_filter
    app.installEventFilter(global_drag_filter)
    app.setApplicationName("KubuxMailClient")
    setup_tooltip_font()
    run_func(*args)
    app.exec()

def edit_drafts_menu(parent, button):
    """Menu of identities; launches open-drafts.py for the selected identity."""
    identities = config.get_identities()
    if not identities:
        display_error(parent, "Identities not found", "No email identities are configured. Please check your config file.")
        return

    menu = QMenu(parent)
    menu.setFont(config.get_menu_font())
    for identity in identities:
        action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
        action = menu.addAction(action_text)
        action.triggered.connect(lambda checked, i=identity: launch_drafts_manager(parent, i))

    button_pos = button.mapToGlobal(button.rect().bottomLeft())
    menu.exec(button_pos)

def edit_config_action(parent):
    """Open the config file in the default editor."""
    try:
        subprocess.Popen(["xdg-open", config.config_path])
        logging.info(f"Launched xdg-open {config.config_path}")
    except Exception as e:
        logging.error(f"Failed to launch config editor: {e}")
        display_error(parent, "Launch Error", f"Could not launch config editor:\n\n{e}")

# --- Shared table/tag helpers (used by show-query-results.py and view-thread.py) ---

def get_row_tags(table, row):
    """Tags from the UserRole payload stored in (row, 0)."""
    item = table.item(row, 0)
    if not item:
        return []
    data = item.data(Qt.ItemDataRole.UserRole)
    return data.get("tags", []) if data else []

def row_has_tag(table, row, tag):
    return tag in get_row_tags(table, row)

def each_selected_row(table):
    """Unique row indices of all selected items."""
    return list(set(item.row() for item in table.selectedItems()))

def toggle_row_tag(table, row, tag, apply_tag):
    """apply_tag(op, row) is called with '+tag' or '-tag'."""
    op = f"-{tag}" if row_has_tag(table, row, tag) else f"+{tag}"
    apply_tag(op, row)

def tag_dialog(parent):
    text, ok = QInputDialog.getText(parent, "Tags", "+/-tag(s) (separated by commas):")
    return [t.strip() for t in text.split(',')] if ok and text else []

def apply_tag_to_selected(table, apply_tag, op_getter):
    """Apply a tag operation to every selected row. op_getter(row) returns the op."""
    for row in each_selected_row(table):
        apply_tag(op_getter(row), row)

def get_sender_receiver(message, config):
    """'From' if not me, else 'to: <To>'."""
    from_field = message.get("headers", {}).get("From", "unknown <nobody@nowhere.net>")
    authors_string_list = [from_field] if isinstance(from_field, str) else from_field
    if not config.is_me(authors_string_list):
        return from_field
    return "to: " + message.get("headers", {}).get("To", "unknown <nobody@nowhere.net>")

def setup_key_bindings(window, actions):
    """Bind config keybindings to actions on the given window."""
    for name, func in actions.items():
        key_seq = config.get_keybinding(name)
        if key_seq:
            action = QAction(window)
            action.setShortcut(QKeySequence(key_seq))
            action.triggered.connect(func)
            window.addAction(action)

# end of file
