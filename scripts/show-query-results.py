#!/usr/bin/env python3

import sys
import argparse
import subprocess
import json
import os
from pathlib import Path
from email.utils import getaddresses
import re
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QDialogButtonBox, QLabel, QTextEdit,
    QCheckBox, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Assuming a config module similar to the other scripts
try:
    from config import config
except ImportError:
    # A simple mock for demonstration purposes if config.py is not available
    class MockConfig:
        def get_font(self, section):
            if section == "text":
                return QFont("monospace", 10)
            return QFont("sans-serif", 10)
        def get_keybinding(self, action):
            bindings = {
                "refresh": "F5",
                "quit": "Ctrl+Q"
            }
            return bindings.get(action)
    config = MockConfig()

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

class QueryResultsViewer(QMainWindow):
    def __init__(self, query_string="tag:inbox and tag:unread", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Queries")
        self.setMinimumSize(QSize(1024, 768))

        self.view_mode = "threads" # or "mails"
        self.current_query = query_string
        self.results = []

        self.setup_ui()
        self.setup_key_bindings()
        self.execute_query()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # a) Top row: quit button right, on the left two buttons "refresh" and a button that changes
        top_bar_layout = QHBoxLayout()
        main_layout.addLayout(top_bar_layout)
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.execute_query)
        top_bar_layout.addWidget(self.refresh_button)

        # View mode toggle button
        self.view_mode_button = QPushButton("Mail View")
        self.view_mode_button.clicked.connect(self.toggle_view_mode)
        top_bar_layout.addWidget(self.view_mode_button)

        # Spacer to push the quit button to the right
        top_bar_layout.addStretch()
        
        # Quit button
        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # b) below the top row: an edit box for the query.
        self.query_edit = QLineEdit(self.current_query)
        self.query_edit.returnPressed.connect(self.execute_query)
        main_layout.addWidget(self.query_edit)

        # c) I like the table below.
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Date", "Subject", "Sender/Receiver"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Sort by date descending by default
        self.results_table.setSortingEnabled(True)
        self.results_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)

        main_layout.addWidget(self.results_table)
        
        # Connect click to action
        self.results_table.doubleClicked.connect(self.open_selected_item)

    def setup_key_bindings(self):
        """Sets up key bindings based on the config file."""
        actions = {
            "quit": self.close,
            "refresh": self.execute_query
        }
        for name, func in actions.items():
            key_seq = config.get_keybinding(name)
            if key_seq:
                action = QAction(self)
                action.setShortcut(QKeySequence(key_seq))
                action.triggered.connect(func)
                self.addAction(action)

    def toggle_view_mode(self):
        if self.view_mode == "threads":
            self.view_mode = "mails"
            self.view_mode_button.setText("Thread View")
        else:
            self.view_mode = "threads"
            self.view_mode_button.setText("Mail View")
        self.execute_query()

    def get_my_email_address(self):
        """Retrieves the user's email address from notmuch config."""
        try:
            command = ['notmuch', 'config', 'get', 'user.primary_email']
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to get primary email from notmuch config: {e.stderr}")
            return None
    
    def _run_notmuch_command(self, command):
        """
        Executes a notmuch command and handles errors with a GUI dialog.
        
        Args:
            command (list): The command and its arguments.
        
        Returns:
            dict or list: The JSON output from notmuch.
        """
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            dialog = CopyableErrorDialog(
                "Notmuch Query Failed",
                f"An error occurred while running notmuch:\n\n{e.stderr}"
            )
            dialog.exec()
            return []
        except json.JSONDecodeError as e:
            dialog = CopyableErrorDialog(
                "Notmuch Output Error",
                f"Failed to parse JSON output from notmuch:\n\n{e}"
            )
            dialog.exec()
            return []

    def _find_matching_threads(self, query):
        """Finds threads matching the query using `notmuch search --output=summary`."""
        command = [
            'notmuch',
            'search',
            '--format=json',
            '--output=summary',
            '--sort=newest-first',
            query
        ]
        return self._run_notmuch_command(command)

    def _find_matching_messages(self, query):
        """
        Finds individual messages matching the query using `notmuch show`,
        and flattens the output.
        """
        command = [
            'notmuch',
            'show',
            '--format=json',
            '--body=false',
            '--sort=newest-first',
            query
        ]
        raw_output = self._run_notmuch_command(command)
        
        if not raw_output:
            return []

        unique_messages = {}

        # The notmuch show JSON output is a list of thread entries.
        for thread_entry in raw_output:
            # Each thread entry is a single-element list.
            # The content of that list is another list containing a message object
            # followed by an empty list.
            if thread_entry and len(thread_entry) > 0 and len(thread_entry[0]) > 0:
                message_info = thread_entry[0]
                message_obj = message_info[0]

                if message_obj["id"] not in unique_messages:
                    unique_messages[message_obj["id"]] = message_obj
                    
        return list(unique_messages.values())

    def execute_query(self):
        self.current_query = self.query_edit.text()
        logging.info(f"Executing query: '{self.current_query}' in '{self.view_mode}' mode.")
        
        self.results_table.setRowCount(0)
        self.results_table.clearContents()
        
        my_email_address = self.get_my_email_address()
        
        if self.view_mode == "threads":
            self._execute_threads_query(my_email_address)
        else: # mails mode
            self._execute_mails_query(my_email_address)
            
    def _execute_threads_query(self, my_email_address):
        """Fetches and populates the table with thread data."""
        self.results = self._find_matching_threads(self.current_query)
        self.results_table.setRowCount(len(self.results))
        for row_idx, thread in enumerate(self.results):
            self._update_row_for_thread(row_idx, thread, my_email_address)

    def _execute_mails_query(self, my_email_address):
        """Fetches and populates the table with mail data."""
        self.results = self._find_matching_messages(self.current_query)
        self.results_table.setRowCount(len(self.results))
        for row_idx, mail in enumerate(self.results):
            self._update_row_for_mail(row_idx, mail, my_email_address)

    def _update_row_for_thread(self, row_idx, thread, my_email_address):
        """Helper to populate a row for a thread item from `notmuch search --output=summary`."""
        
        date_stamp = thread.get("newest_date")
        date_item = self._create_date_item(date_stamp)
        self.results_table.setItem(row_idx, 0, date_item)
        
        subject_text = f"{thread.get('subject')} ({thread.get('total_messages')})"
        subject_item = QTableWidgetItem(subject_text)
        self.results_table.setItem(row_idx, 1, subject_item)
        
        sender_receiver_text = self._get_sender_receiver(thread.get("authors", ""), my_email_address)
        sender_receiver_item = QTableWidgetItem(sender_receiver_text)
        self.results_table.setItem(row_idx, 2, sender_receiver_item)
        
        # Store the entire thread object in the first column's user data
        self.results_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, thread)

    def _update_row_for_mail(self, row_idx, mail, my_email_address):
        """Helper to populate a row for a mail item from `notmuch show`."""
        
        date_stamp = mail.get("timestamp")
        date_item = self._create_date_item(date_stamp)
        self.results_table.setItem(row_idx, 0, date_item)
        
        subject_item = QTableWidgetItem(mail.get("headers", {}).get("Subject", "No Subject"))
        self.results_table.setItem(row_idx, 1, subject_item)
        
        sender_receiver_text = self._get_sender_receiver(mail.get("headers", {}).get("From", ""), my_email_address)
        sender_receiver_item = QTableWidgetItem(sender_receiver_text)
        self.results_table.setItem(row_idx, 2, sender_receiver_text)
        
        # Store the entire mail object in the first column's user data
        self.results_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, mail)
        
    def _create_date_item(self, timestamp):
        """Creates a sortable QTableWidgetItem for the date."""
        if not isinstance(timestamp, (int, float)):
            timestamp = 0
            
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
        date_string = dt.strftime("%Y-%m-%d %H:%M")
        
        item = QTableWidgetItem(date_string)
        item.setData(Qt.ItemDataRole.UserRole, timestamp)
        return item
        
    def _get_sender_receiver(self, authors_string, my_email):
        """Extracts the sender/receiver based on my email address."""
        addresses = getaddresses([authors_string])
        
        if len(addresses) == 1 and addresses[0][1] == my_email:
            return "To: (You)"

        for name, addr in addresses:
            if addr != my_email:
                return name if name else addr
                
        return "You"

    def open_selected_item(self, index):
        """Launches the appropriate viewer based on the selected item."""
        row = index.row()
        item_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        if self.view_mode == "threads":
            # notmuch search with --output=summary returns a "thread" key
            thread_id = item_data.get("thread")
            if thread_id:
                logging.info(f"Launching thread viewer for thread ID: {thread_id}")
                # Placeholder for the command to launch thread viewer
                QMessageBox.information(self, "Action Mocked", f"Launching thread viewer for thread ID: {thread_id}")
            else:
                logging.warning("Could not find thread ID for selected row.")
        else: # mails mode
            mail_file_path = item_data.get("filename")
            if mail_file_path:
                logging.info(f"Launching mail viewer for file: {mail_file_path}")
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-mail.py")
                    subprocess.Popen(["python3", viewer_path, mail_file_path[0]])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find mail file path for selected row.")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View notmuch query results in a list.")
    parser.add_argument("--query", help="The notmuch query to display.", default="tag:inbox and tag:unread")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    viewer = QueryResultsViewer(args.query)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
