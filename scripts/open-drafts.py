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
from common import display_error

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DraftsFileSystemEventHandler(FileSystemEventHandler):
    """Handles file system events for the drafts directory."""
    def __init__(self, callback):
        self.callback = callback
        # Debounce mechanism to avoid multiple rapid reloads
        self.last_event_time = 0
        self.debounce_interval = 0.5  # seconds
        
    def on_any_event(self, event):
        """Called for any file system event."""
        # Skip directories and non-eml files
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != '.eml':
            return
            
        # Debounce - only process events if enough time has passed since the last one
        current_time = time.time()
        if current_time - self.last_event_time > self.debounce_interval:
            self.last_event_time = current_time
            self.callback()


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
        self.observer = Observer()
        event_handler = DraftsFileSystemEventHandler(self.signals.reload_needed.emit)
        self.observer.schedule(event_handler, str(self.directory_path), recursive=False)
        self.observer.start()
        
        # Keep the thread running
        while self.running:
            time.sleep(0.5)
            
    def stop(self):
        """Stop monitoring the directory."""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()


class DraftsManager(QMainWindow):
    def __init__(self, drafts_dir_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Drafts")
        self.resize(QSize(900, 700))

        self.current_drafts_dir = None
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
                self.load_drafts(Path(drafts_path_str).expanduser())

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setFont(config.get_interface_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top bar with buttons
        top_bar_layout = QHBoxLayout()
        main_layout.addLayout(top_bar_layout)

        self.drafts_folder_button = QPushButton("Drafts Folder")
        self.drafts_folder_button.setFont(config.get_interface_font())
        self.drafts_folder_button.setMenu(self._create_drafts_menu())
        top_bar_layout.addWidget(self.drafts_folder_button)
        top_bar_layout.addStretch()

        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # Set up the table
        self.drafts_table = QTableWidget()
        self.drafts_table.setColumnCount(4)
        self.drafts_table.setHorizontalHeaderLabels(["Date", "From", "To/Cc", "Subject"])
        
        # Configure the table's appearance
        # FIX: Make the header an instance variable to be accessible in other methods
        self.header = self.drafts_table.horizontalHeader()
        self.header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.drafts_table.verticalHeader().setVisible(False)
        self.drafts_table.setFont(config.get_text_font())
        self.drafts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.drafts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.drafts_table.cellDoubleClicked.connect(self.open_selected_draft)

        main_layout.addWidget(self.drafts_table)
        
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
                action.triggered.connect(lambda checked, p=drafts_path: self.load_drafts(p))
        return menu

    def start_file_system_watcher(self, directory_path):
        """Start watching the drafts directory for changes."""
        # Stop any existing watcher
        self.stop_file_system_watcher()
        
        # Create a new watcher thread
        self.fs_watcher = FileSystemWatcherThread(directory_path)
        self.fs_watcher.signals.reload_needed.connect(self.reload_drafts)
        self.fs_watcher.start()
        logging.info(f"Started file system watcher for {directory_path}")
        
    def stop_file_system_watcher(self):
        """Stop the file system watcher."""
        if self.fs_watcher:
            self.fs_watcher.stop()
            self.fs_watcher.wait()  # Wait for the thread to finish
            self.fs_watcher = None
            logging.info("Stopped file system watcher")

    def closeEvent(self, event):
        """Handle the window close event."""
        self.stop_file_system_watcher()
        super().closeEvent(event)

    def load_drafts(self, directory_path):
        """Loads and displays a list of drafts from a given directory."""
        self.current_drafts_dir = directory_path
        
        # Clear the table and update the window title
        self.drafts_table.setRowCount(0)
        self.setWindowTitle(f"Manage Drafts - {self.current_drafts_dir}")
        
        if not self.current_drafts_dir.is_dir():
            display_error(self, "Directory not found", f"The drafts directory does not exist:\n\n{self.current_drafts_dir}")
            return
            
        logging.info(f"Loading drafts from directory: {self.current_drafts_dir}")
        draft_files = sorted(self.current_drafts_dir.glob('*.eml'))
        
        self.drafts_table.setRowCount(len(draft_files))
        
        for row, file_path in enumerate(draft_files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    msg = email.message_from_file(f, policy=policy.default)
                    
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
                
                # Populate the table row
                self.drafts_table.setItem(row, 0, QTableWidgetItem(date_str))
                self.drafts_table.setItem(row, 1, QTableWidgetItem(from_header))
                self.drafts_table.setItem(row, 2, QTableWidgetItem(to_cc_string))
                self.drafts_table.setItem(row, 3, QTableWidgetItem(subject_header))
                
                # Store the full file path in the item for retrieval later
                self.drafts_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, str(file_path))
                
            except Exception as e:
                logging.error(f"Failed to process draft file {file_path}: {e}")
                # Add an entry to the table to indicate the error
                self.drafts_table.setItem(row, 0, QTableWidgetItem(f"ERROR: {file_path}"))
                self.drafts_table.setSpan(row, 0, 1, 4)

        # Make the headers resize to content
        self.header.resizeSections(QHeaderView.ResizeMode.ResizeToContents)
        
        # Start watching this directory for changes
        self.start_file_system_watcher(self.current_drafts_dir)
    
    def reload_drafts(self):
        """Reload the drafts list."""
        if self.current_drafts_dir:
            logging.info(f"Reloading drafts from {self.current_drafts_dir} due to file system changes")
            self.load_drafts(self.current_drafts_dir)

    def open_selected_draft(self, row, column):
        """Opens the selected draft file in edit-mail.py."""
        file_path_item = self.drafts_table.item(row, 0)
        if not file_path_item:
            return
            
        file_path = file_path_item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return

        try:
            editor_path = os.path.join(os.path.dirname(__file__), "edit-mail.py")
            subprocess.Popen(["python3", editor_path, "--mail-file", file_path])
            logging.info(f"Launched mail editor for draft: {file_path}")
        except Exception as e:
            logging.error(f"Failed to launch mail editor: {e}")
            display_error(self, "Launch Error", f"Could not launch edit-mail.py:\n\n{e}")
            
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
