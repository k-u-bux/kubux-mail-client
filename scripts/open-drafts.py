#!/usr/bin/env python3

import sys
import os
import argparse
import subprocess
from pathlib import Path
from email import policy
import email.message
from datetime import datetime
from email.utils import getaddresses
import logging
import time
import traceback
from threading import Timer

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QSize, QTimer, QObject, Signal, QThread, QEvent
from PySide6.QtGui import QFont, QAction, QColor

from mail_table_widget import MailTableWidget

# directory monitoring
from watcher import DirectoryEventHandler

# Import the shared components
from config import config
from common import display_error, create_new_mail_menu, match_address, find_identity

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DraftsManager(QMainWindow):
    def __init__(self, drafts_dir_path=None, sender_email="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Mail Client - Drafts")
        self.resize(QSize(1024, 768))

        self.current_drafts_dir = None
        self.current_identity = find_identity( sender_email )
        if not self.current_identity:
            logging.error(f"Sender mail address unknown: {sender_email}")
            os.exit(1)

        self.dir_watcher = DirectoryEventHandler( self.reload_drafts )
        
        self.setup_ui()
        
        # Load the initial drafts directory from the command-line argument
        if drafts_dir_path:
            self.load_drafts(Path(drafts_dir_path).expanduser(), self.current_identity)
        else:
            drafts_path_str = self.current_identity.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
            self.load_drafts(Path(drafts_path_str).expanduser(), self.current_identity)

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setFont(config.get_interface_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Top bar with buttons
        top_bar_layout = QHBoxLayout()
        main_layout.addLayout(top_bar_layout)

        self.new_mail_button = QPushButton("New Mail")
        self.new_mail_button.setFont(config.get_interface_font())
        top_bar_layout.addWidget(self.new_mail_button)
        self.new_mail_button.clicked.connect(self.new_mail_action)

        self.drafts_folder_button = QPushButton("Drafts")
        self.drafts_folder_button.setFont(config.get_interface_font())
        self.drafts_folder_button.setMenu(self._create_drafts_menu())
        top_bar_layout.addWidget(self.drafts_folder_button)

        top_bar_layout.addStretch()

        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # Set up the table with new column order: Date|To/Cc|Subject|From
        self.drafts_table = MailTableWidget()
        self.drafts_table.cellDoubleClicked.connect(self.open_selected_draft)

        # Enable context menu
        self.drafts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.drafts_table.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.drafts_table)
    
    def show_context_menu(self, position):
        """Show context menu with options to delete, edit, or execute a query."""
        # Get the row and column at the context menu position
        row = self.drafts_table.rowAt(position.y())
        column = self.drafts_table.columnAt(position.x())
        
        # Skip if we're outside the table or on the empty input row
        if row < 0 or column < 0 or row == 0:
            return
        
        # Store the row and column for later use
        self.context_menu_row = row
        self.context_menu_column = column
        
        # Create context menu
        context_menu = QMenu(self)
        context_menu.setFont(config.get_menu_font())
        
        selected_items = self.drafts_table.selectedItems();

        # Add actions
        open_action = QAction("Open", self)
        delete_action = QAction("Delete", self)
        if selected_items:
            open_action.triggered.connect( self.open_selected_items )
            delete_action.triggered.connect( self.delete_selected_items )
        else:
            open_action.triggered.connect( lambda r=row: self.open_row( r ) )
            delete_action.triggered.connect( lambda r=row: self.delete_row( r ) )
        
        # Add actions to menu in the preferred order
        context_menu.addAction(open_action)
        context_menu.addAction(delete_action)
        
        # Show context menu at the right position
        context_menu.exec(self.drafts_table.viewport().mapToGlobal(position))

    def _create_drafts_menu(self):
        """Creates a dropdown menu for selecting an identity's drafts folder."""
        menu = QMenu(self)
        menu.setFont(config.get_menu_font())
        identities = config.get_identities()
        if not identities:
            action = menu.addAction("No identities found")
            action.setEnabled(False)
        else:
            for identity in identities:
                action_text = f"Drafts for {identity.get('name', '')} <{identity.get('email', '')}>"
                action = menu.addAction(action_text)
                drafts_path_str = identity.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
                drafts_path = Path(drafts_path_str).expanduser()
                # Pass both the path and the identity when connecting
                action.triggered.connect(lambda checked, p=drafts_path, i=identity: self.load_drafts(p, i))
        return menu

    def start_file_system_watcher(self, directory_path):
        self.dir_watcher.watch( directory_path )
        
    def stop_file_system_watcher(self):
        self.dir_watcher.stop()

    def closeEvent(self, event):
        """Handle the window close event."""
        self.stop_file_system_watcher()
        super().closeEvent(event)
    
    def update_drafts_folder_button(self):
        """Update the drafts folder button text based on the current identity."""
        if self.current_identity:
            name = self.current_identity.get('name', '')
            email = self.current_identity.get('email', '')
            if name and email:
                self.drafts_folder_button.setText(f"Drafts for {name} <{email}>")
            elif email:
                self.drafts_folder_button.setText(f"Drafts for <{email}>")
            else:
                self.drafts_folder_button.setText("Drafts")
        else:
            # Find identity by matching the drafts path
            if self.current_drafts_dir:
                identities = config.get_identities()
                for identity in identities:
                    drafts_path_str = identity.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
                    drafts_path = Path(drafts_path_str).expanduser()
                    if drafts_path == self.current_drafts_dir:
                        name = identity.get('name', '')
                        email = identity.get('email', '')
                        if name and email:
                            self.drafts_folder_button.setText(f"Drafts for {name} <{email}>")
                            self.current_identity = identity
                            return
                        elif email:
                            self.drafts_folder_button.setText(f"Drafts for <{email}>")
                            self.current_identity = identity
                            return
            
            # Fallback if no identity found
            self.drafts_folder_button.setText(f"Drafts: {self.current_drafts_dir.name}")

    def load_drafts(self, directory_path, identity):
        """Loads and displays a list of drafts from a given directory."""
        self.current_drafts_dir = directory_path
        self.current_identity = identity

        sender_email = identity.get('email')
        
        # Update the drafts folder button text
        self.update_drafts_folder_button()
        
        # Clear hover state when refreshing
        self.drafts_table.clear_and_reset_hover()
        
        # Clear the table and update the window title
        self.drafts_table.setRowCount(0)
        self.setWindowTitle(f"Kubux Mail Client - Drafts ({self.current_identity['email']})")
        self.drafts_table.setHorizontalHeaderLabels(["Date", "To/Cc", "Subject"])

        if not self.current_drafts_dir.is_dir():
            display_error(self, "Directory not found", f"The drafts directory does not exist:\n\n{self.current_drafts_dir}")
            return
            
        logging.info(f"Loading drafts from directory: {self.current_drafts_dir}")
        
        try:
            # Look specifically for .eml files for display in the table
            draft_files = sorted(self.current_drafts_dir.glob('*.eml'))
            
            valid_draft_files = []
            for file_path in draft_files:
                try:
                    # Basic validation - check if file can be opened
                    with open(file_path, 'rb') as f:
                        msg = email.message_from_binary_file(f, policy=policy.default)
                    # If we get here, the file is a valid email file
                    valid_draft_files.append((file_path, msg))
                except Exception as e:
                    # Log error but don't display in UI
                    logging.error(f"Failed to process draft file {file_path}: {e}")
                    logging.debug(traceback.format_exc())
                    # Skip this file - don't add it to the table
            
            self.drafts_table.setRowCount(len(valid_draft_files))

            row = 0
            for (file_path, msg) in valid_draft_files:
                # logging.info(f"considering: {file_path}")
                try:
                    # Extract headers and file info
                    from_header = msg.get('From', 'No From')
                    if match_address( from_header, sender_email ):
                        to_header = msg.get('To', '')
                        cc_header = msg.get('Cc', '')
                        subject_header = msg.get('Subject', 'No Subject')
                        
                        # Format To/Cc string
                        to_cc_string = ""
                        if to_header:
                            to_cc_string += f"To: {', '.join([addr for name, addr in getaddresses([to_header])])}"
                        if cc_header:
                            if to_cc_string:
                                to_cc_string += "; "
                            to_cc_string += f"Cc: {', '.join([addr for name, addr in getaddresses([cc_header])])}"
                            
                        # Use file's modification time as a fallback for date
                        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        date_str = mod_time.strftime("%Y-%m-%d %H:%M")
                        
                        # Populate the table row with the new column order: Date|To/Cc|Subject|From
                        self.drafts_table.setItem(row, 0, QTableWidgetItem(date_str))
                        self.drafts_table.setItem(row, 1, QTableWidgetItem(to_cc_string))
                        self.drafts_table.setItem(row, 2, QTableWidgetItem(subject_header))
                        
                        # Store the full file path in the item for retrieval later
                        # logging.info(f"row: {row}")
                        self.drafts_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, str(file_path))
                        row = row + 1
                    else:
                        # logging.info(f"skipping: {from_header}")
                        pass
                except Exception as e:
                    # Log any other errors but don't show in UI
                    logging.error(f"Error processing email data for {file_path}: {e}")
                    logging.debug(traceback.format_exc())
                    # Skip this row - we've already allocated it, so just leave it empty
                    # The row count should be correct since we're only looping through valid files

            # Set the row count based on valid files only
            self.drafts_table.setRowCount(row)
            
            # Re-adjust the column widths after loading data
            # self._fix_column_widths(self._width_ratio)
            
            # Start watching this directory for changes
            self.start_file_system_watcher(self.current_drafts_dir)
            
        except Exception as e:
            # Handle any errors during the overall loading process
            logging.error(f"Error loading drafts: {e}")
            logging.debug(traceback.format_exc())
            display_error(self, "Load Error", f"Failed to load drafts:\n\n{e}")
    
    def reload_drafts(self):
        """Reload the drafts list."""
        try:
            if self.current_drafts_dir:
                logging.info(f"Reloading drafts from {self.current_drafts_dir} due to file system changes")
                # Load drafts but capture any exceptions to prevent UI disruption
                self.load_drafts(self.current_drafts_dir, self.current_identity)
        except Exception as e:
            # Log but don't propagate the error
            logging.error(f"Error reloading drafts: {e}")
            logging.debug(traceback.format_exc())

    def new_mail_action(self):
        """Creates and displays a menu for selecting an email identity."""
        create_new_mail_menu(self)

    def open_selected_draft(self, row, column):
        self.open_row(row)

    def open_row(self, row):
       try:
            file_path_item = self.drafts_table.item(row, 0)
            if not file_path_item:
                return
                
            file_path = file_path_item.data(Qt.ItemDataRole.UserRole)
            if not file_path:
                return

            editor_path = os.path.join(os.path.dirname(__file__), "edit-mail")
            subprocess.Popen([editor_path, "--mail-file", file_path])
            logging.info(f"Launched mail editor for draft: {file_path}")
       except Exception as e:
            logging.error(f"Failed to launch mail editor: {e}")
            logging.debug(traceback.format_exc())
            display_error(self, "Launch Error", f"Could not launch edit-mail.py:\n\n{e}")
    
    def open_selected_items(self):
        for row in list( set( [ item.row() for item in self.drafts_table.selectedItems() ] ) ):
            self.open_row( row )
    
    # delete
    def delete_row(self, row):
       try:
            file_path_item = self.drafts_table.item(row, 0)
            if not file_path_item:
                return
                
            file_path = file_path_item.data(Qt.ItemDataRole.UserRole)
            if not file_path:
                return

            os.remove( file_path )
            logging.info(f"Deleted draft: {file_path}")
       except Exception as e:
            logging.error(f"Failed to delete draft: {e}")
            logging.debug(traceback.format_exc())
 
    def delete_selected_items(self):
        for row in list( set( [ item.row() for item in self.drafts_table.selectedItems() ] ) ):
            self.delete_row( row )
            
# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Manage email drafts.")
    parser.add_argument("--drafts-dir", help="The full path to the drafts directory.")
    parser.add_argument("--email", help="The senders email address.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    # app.setApplicationDisplayName( "Kubux Mail Client" )
    app.setApplicationName( "KubuxMailClient" )
    manager = DraftsManager(drafts_dir_path=args.drafts_dir, sender_email=args.email)
    manager.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
