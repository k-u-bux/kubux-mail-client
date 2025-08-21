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
from PySide6.QtCore import Qt, QSize, QTimer, QObject, Signal, QThread
from PySide6.QtGui import QFont

# Import watchdog for directory monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import the shared components
from config import config
from common import display_error, create_new_mail_menu

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DraftsFileSystemEventHandler(FileSystemEventHandler):
    """Handles file system events for the drafts directory."""
    def __init__(self, callback):
        self.callback = callback
        # Track the timer for debouncing
        self.timer = None
        self.debounce_interval = 0.5  # seconds
        
    def on_any_event(self, event):
        """Called for any file system event."""
        try:
            # Don't filter by file extension - we want to catch all events
            # including temp files that might be part of the edit-save cycle
            
            # Cancel any existing timer
            if self.timer and self.timer.is_alive():
                self.timer.cancel()
            
            # Create a new standard Python timer (works in any thread)
            self.timer = Timer(self.debounce_interval, self.callback)
            self.timer.daemon = True  # Allow the timer to be killed when the program exits
            self.timer.start()
            
            logging.debug(f"File system event: {event.event_type} - {event.src_path}")
            
        except Exception as e:
            # Log the error but don't propagate it to avoid affecting the UI
            logging.error(f"Error in file system event handler: {e}")
            logging.debug(traceback.format_exc())


class FSWatcherSignals(QObject):
    """Signals for the file system watcher thread."""
    reload_needed = Signal()


class FileSystemWatcherThread(QThread):
    """Thread for watching file system changes."""
    def __init__(self, directory_path):
        super().__init__()
        self.directory_path = directory_path
        self.signals = FSWatcherSignals()
        self.observer = None
        self.running = True
        
    def run(self):
        """Start monitoring the directory."""
        try:
            self.observer = Observer()
            event_handler = DraftsFileSystemEventHandler(self.signals.reload_needed.emit)
            # Monitor the entire directory, not just .eml files
            self.observer.schedule(event_handler, str(self.directory_path), recursive=False)
            self.observer.start()
            
            # Keep the thread running
            while self.running:
                time.sleep(0.5)
        except Exception as e:
            # Log the error but don't propagate it to avoid affecting the UI
            logging.error(f"Error in file system watcher thread: {e}")
            logging.debug(traceback.format_exc())
        finally:
            # Make sure to stop the observer if it was started
            if hasattr(self, 'observer') and self.observer:
                try:
                    self.observer.stop()
                    self.observer.join()
                except Exception as e:
                    logging.error(f"Error stopping observer: {e}")
            
    def stop(self):
        """Stop monitoring the directory."""
        self.running = False
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join()
            except Exception as e:
                logging.error(f"Error stopping observer: {e}")


class DraftsManager(QMainWindow):
    def __init__(self, drafts_dir_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Drafts")
        self.resize(QSize(900, 700))

        self.current_drafts_dir = None
        self.current_identity = None
        self.fs_watcher = None
        
        self.setup_ui()
        
        # Load the initial drafts directory from the command-line argument
        if drafts_dir_path:
            self.load_drafts(Path(drafts_dir_path))
        else:
            # If no argument is provided, default to the first identity's drafts folder
            identities = config.get_identities()
            if identities:
                first_identity = identities[0]
                drafts_path_str = first_identity.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
                self.load_drafts(Path(drafts_path_str).expanduser(), identity=first_identity)

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setFont(config.get_interface_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

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
        self.drafts_table = QTableWidget()
        self.drafts_table.setColumnCount(4)
        self.drafts_table.setHorizontalHeaderLabels(["Date", "To/Cc", "Subject", "From"])
        
        # Configure the table's appearance and make columns user-resizable
        self.header = self.drafts_table.horizontalHeader()
        
        # Set initial column widths to use available space more efficiently
        # Date column gets a reasonable fixed width
        self.header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.drafts_table.setColumnWidth(0, 120)  # Date column width
        
        # To/Cc and Subject share most of the space
        self.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        
        # From column gets a reasonable width
        self.header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        
        # When the table is first shown, stretch the To/Cc and Subject columns
        # We'll use a timer to adjust column widths after the UI is visible
        QTimer.singleShot(0, self.adjust_initial_column_widths)

        self.drafts_table.verticalHeader().setVisible(False)
        self.drafts_table.setFont(config.get_text_font())
        self.drafts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.drafts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.drafts_table.cellDoubleClicked.connect(self.open_selected_draft)

        main_layout.addWidget(self.drafts_table)
    
    def adjust_initial_column_widths(self):
        """Adjust initial column widths once the UI is visible."""
        total_width = self.drafts_table.width()
        # Reserve 120px for Date and 200px for From
        remaining_width = total_width - 120 - 200
        # Split the remaining width between To/Cc and Subject (40% and 60%)
        if remaining_width > 0:
            to_cc_width = int(remaining_width * 0.4)
            subject_width = remaining_width - to_cc_width
            
            self.drafts_table.setColumnWidth(0, 120)  # Date
            self.drafts_table.setColumnWidth(1, to_cc_width)  # To/Cc
            self.drafts_table.setColumnWidth(2, subject_width)  # Subject
            self.drafts_table.setColumnWidth(3, 200)  # From
        
    def _create_drafts_menu(self):
        """Creates a dropdown menu for selecting an identity's drafts folder."""
        menu = QMenu(self)
        menu.setFont(config.get_text_font())
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
        """Start watching the drafts directory for changes."""
        try:
            # Stop any existing watcher
            self.stop_file_system_watcher()
            
            # Create a new watcher thread
            self.fs_watcher = FileSystemWatcherThread(directory_path)
            self.fs_watcher.signals.reload_needed.connect(self.reload_drafts)
            self.fs_watcher.start()
            logging.info(f"Started file system watcher for {directory_path}")
        except Exception as e:
            # Log the error but don't affect the UI
            logging.error(f"Failed to start file system watcher: {e}")
            logging.debug(traceback.format_exc())
            # Nullify the watcher if it failed to start
            self.fs_watcher = None
        
    def stop_file_system_watcher(self):
        """Stop the file system watcher."""
        if self.fs_watcher:
            try:
                self.fs_watcher.stop()
                self.fs_watcher.wait()  # Wait for the thread to finish
                self.fs_watcher = None
                logging.info("Stopped file system watcher")
            except Exception as e:
                # Log the error but don't affect the UI
                logging.error(f"Error stopping file system watcher: {e}")
                logging.debug(traceback.format_exc())
                # Ensure we clear the reference even if there was an error
                self.fs_watcher = None

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

    def load_drafts(self, directory_path, identity=None):
        """Loads and displays a list of drafts from a given directory."""
        self.current_drafts_dir = directory_path
        self.current_identity = identity
        
        # Update the drafts folder button text
        self.update_drafts_folder_button()
        
        # Clear the table and update the window title
        self.drafts_table.setRowCount(0)
        self.setWindowTitle(f"Manage Drafts - {self.current_drafts_dir}")
        
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
                    with open(file_path, 'r', encoding='utf-8') as f:
                        msg = email.message_from_file(f, policy=policy.default)
                    # If we get here, the file is a valid email file
                    valid_draft_files.append((file_path, msg))
                except Exception as e:
                    # Log error but don't display in UI
                    logging.error(f"Failed to process draft file {file_path}: {e}")
                    logging.debug(traceback.format_exc())
                    # Skip this file - don't add it to the table
            
            # Set the row count based on valid files only
            self.drafts_table.setRowCount(len(valid_draft_files))
            
            # Only populate with valid files
            for row, (file_path, msg) in enumerate(valid_draft_files):
                try:
                    # Extract headers and file info
                    from_header = msg.get('From', 'No From')
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
                    self.drafts_table.setItem(row, 3, QTableWidgetItem(from_header))
                    
                    # Store the full file path in the item for retrieval later
                    self.drafts_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, str(file_path))
                except Exception as e:
                    # Log any other errors but don't show in UI
                    logging.error(f"Error processing email data for {file_path}: {e}")
                    logging.debug(traceback.format_exc())
                    # Skip this row - we've already allocated it, so just leave it empty
                    # The row count should be correct since we're only looping through valid files

            # Re-adjust the column widths after loading data
            self.adjust_initial_column_widths()
            
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
        """Opens the selected draft file in edit-mail.py."""
        try:
            file_path_item = self.drafts_table.item(row, 0)
            if not file_path_item:
                return
                
            file_path = file_path_item.data(Qt.ItemDataRole.UserRole)
            if not file_path:
                return

            editor_path = os.path.join(os.path.dirname(__file__), "edit-mail.py")
            subprocess.Popen(["python3", editor_path, "--mail-file", file_path])
            logging.info(f"Launched mail editor for draft: {file_path}")
        except Exception as e:
            logging.error(f"Failed to launch mail editor: {e}")
            logging.debug(traceback.format_exc())
            display_error(self, "Launch Error", f"Could not launch edit-mail.py:\n\n{e}")
    
    def resizeEvent(self, event):
        """Handle window resize events to adjust column widths."""
        super().resizeEvent(event)
        # Re-adjust column widths when window is resized
        self.adjust_initial_column_widths()
            
# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Manage email drafts.")
    parser.add_argument("--drafts-dir", help="The full path to the drafts directory.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    manager = DraftsManager(drafts_dir_path=args.drafts_dir)
    manager.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
