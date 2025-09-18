from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QDialogButtonBox, QLabel, QTextEdit,
    QCheckBox, QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging
from pathlib import Path
from datetime import datetime
import secrets
import os
import subprocess
import shutil
from config import config

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
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        random_component = secrets.token_hex(16)
        draft_filename = f"{timestamp_str}__{random_component}.eml"
        draft_path = drafts_path / draft_filename
        
        # Create the draft file by copying the template or creating a minimal one
        if template_path.is_file():
            shutil.copyfile(template_path, draft_path)
            logging.info(f"Created new draft file at {draft_path} from template.")
        else:
            logging.warning(f"Template file not found at {template_path}. Creating a minimal draft instead.")
            with open(draft_path, "w") as f:
                f.write(f"From: {identity_dict['name']} <{identity_dict['email']}>\n")
                f.write("To: \n")
                f.write(f"Cc: {identity_dict['name']} <{identity_dict['email']}>\n")
                f.write("Subject: \n\n")

        # Launch the mail editor on the new draft file
        viewer_path = os.path.join(os.path.dirname(__file__), "edit-mail")
        subprocess.Popen([viewer_path, "--mail-file", str(draft_path)])
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
    menu.setFont(config.get_text_font())
    for identity in identities:
        action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
        action = menu.addAction(action_text)
        action.triggered.connect(lambda checked, i=identity: create_draft(parent,i))

    # Get the position of the New Mail button and show the menu
    button_pos = parent.new_mail_button.mapToGlobal(QPoint(0, parent.new_mail_button.height()))
    menu.exec(button_pos)

def create_draft_from_components_and_open_editor(parent, to_addrs, cc_addrs, subject_text, body_text, in_reply_to=None):
    """
    Creates a new mail draft and opens it in the external editor.
    """
    msg = email.message.EmailMessage()
    msg['From'] = MY_EMAIL_ADDRESS
    msg['To'] = ", ".join(to_addrs)
    if cc_addrs:
        msg['Cc'] = ", ".join(cc_addrs)

    msg['Subject'] = subject_text
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to

    msg.set_content(body_text)
    create_draft_from_message_open_editor(parent, msg)

def create_draft_from_message_open_editor(parent, msg):
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".eml") as temp_file:
            temp_file.write(msg.as_string())
            temp_path = temp_file.name

        # Assuming edit-mail.py is in the same directory.
        # You might need to adjust this path based on your project structure.
        editor_path = os.path.join(os.path.dirname(__file__), "edit-mail")
        if not os.path.exists(editor_path):
            QMessageBox.critical(parent, "Error", f"Could not find mail editor at {editor_path}")
            return

        subprocess.Popen([editor_path, "--mail-file", temp_path])
    except Exception as e:
        QMessageBox.critical(parent, "Error", f"Failed to create or open draft: {e}")

def launch_drafts_manager(parent, identity_dict):
    """Launches the drafts manager script for a given identity's drafts folder."""
    try:
        drafts_path_str = identity_dict.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
        drafts_path = Path(drafts_path_str).expanduser()

        viewer_path = os.path.join(os.path.dirname(__file__), "open-drafts")
        subprocess.Popen([viewer_path, "--drafts-dir", str(drafts_path)])
        logging.info(f"Launched drafts manager for directory: {drafts_path}")
    except Exception as e:
        logging.error(f"Failed to launch drafts manager: {e}")
        display_error(parent, "Launch Error", f"Could not launch open-drafts.py:\n\n{e}")
