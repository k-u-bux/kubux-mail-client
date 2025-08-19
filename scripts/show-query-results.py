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

try:
    import notmuch
    NOTMUCH_BINDINGS_AVAILABLE = True
except ImportError:
    NOTMUCH_BINDINGS_AVAILABLE = False

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import the shared config component
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

class QueryResultsViewer(QMainWindow):
    def __init__(self, query_string="tag:inbox or tag:unread", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Notmuch Mail Client - Queries")
        self.setMinimumSize(QSize(1024, 768))

        self.notmuch_enabled = self.check_notmuch()

        self.view_mode = "threads" # or "mails"
        self.current_query = query_string
        self.results = []

        self.setup_ui()
        self.setup_key_bindings()
        self.execute_query()

    def check_notmuch(self):
        """Checks if the notmuch Python bindings are available."""
        if not NOTMUCH_BINDINGS_AVAILABLE:
            dialog = CopyableErrorDialog(
                "Notmuch Bindings Not Found",
                "The 'notmuch' Python bindings were not found. Query-related functionality will be disabled."
            )
            dialog.exec()
            return False
            
        return True

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

        # c) The table
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
        
        # Apply visual settings from config
        self.query_edit.setFont(config.text_font)
        self.results_table.setFont(config.text_font)
        self.refresh_button.setFont(config.interface_font)
        self.view_mode_button.setFont(config.interface_font)
        self.quit_button.setFont(config.interface_font)
        self.results_table.horizontalHeader().setFont(config.interface_font)

    def setup_key_bindings(self):
        """Sets up key bindings based on the config file."""
        actions = {
            "quit_action": self.close,
            "refresh_action": self.execute_query
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
        """
        Retrieves the user's email addresses from the shared config.
        We now use the config file as the source of truth for identities.
        """
        identities = config.get_identities()
        return [i['email'] for i in identities]

    def execute_query(self):
        if not self.notmuch_enabled:
            return

        self.current_query = self.query_edit.text()
        logging.info(f"Executing query: '{self.current_query}' in '{self.view_mode}' mode.")
        
        my_email_addresses = self.get_my_email_address()
        
        try:
            db = notmuch.Database(mode=notmuch.Database.MODE.READ_ONLY)
            query = db.query(self.current_query)
            self.results = []
            
            if self.view_mode == "threads":
                for thread in query.search_threads():
                    # The notmuch bindings' thread object already has the summary info
                    thread_summary = {
                        "id": thread.get_thread_id(),
                        "subject": thread.get_subject(),
                        "authors": thread.get_authors(),
                        "oldest_date": thread.get_oldest_date(),
                        "newest_date": thread.get_newest_date(),
                        "total_messages": thread.get_total_messages(),
                        "thread_obj": thread # Store the actual object for later use
                    }
                    self.results.append(thread_summary)
            else: # mails mode
                for message in query.search_messages():
                    # The notmuch bindings' message object already has the info
                    self.results.append(message)
                    
            db.close()
            self.update_results_table(my_email_addresses)

        except notmuch.NotmuchError as e:
            dialog = CopyableErrorDialog(
                "Notmuch Query Failed",
                f"An error occurred with the notmuch bindings:\n\n{e}"
            )
            dialog.exec()
            self.results = []
            self.results_table.setRowCount(0)

    def update_results_table(self, my_email_addresses):
        """Populates the table with the new query results."""
        if self.view_mode == "threads":
            columns = ["Date (Newest)", "Subject", "Author"]
        else:
            columns = ["Date", "Subject", "Sender/Receiver"]
            
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(self.results))
        
        for row_idx, item in enumerate(self.results):
            if self.view_mode == "threads":
                self._update_row_for_thread(row_idx, item, my_email_addresses)
            else: # mails mode
                self._update_row_for_mail(row_idx, item, my_email_addresses)

        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _update_row_for_thread(self, row_idx, thread_summary, my_email_addresses):
        """Helper to populate a row for a thread item."""
        
        date_stamp = thread_summary.get("newest_date")
        date_item = self._create_date_item(date_stamp)
        self.results_table.setItem(row_idx, 0, date_item)
        
        subject_text = f"{thread_summary.get('subject')} ({thread_summary.get('total_messages')})"
        subject_item = QTableWidgetItem(subject_text)
        self.results_table.setItem(row_idx, 1, subject_item)
        
        sender_receiver_text = self._get_sender_receiver(thread_summary.get("authors", ""), my_email_addresses)
        sender_receiver_item = QTableWidgetItem(sender_receiver_text)
        self.results_table.setItem(row_idx, 2, sender_receiver_item)
        
        # Store the thread ID for lookup
        self.results_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, thread_summary["id"])

    def _update_row_for_mail(self, row_idx, mail, my_email_addresses):
        """Helper to populate a row for a mail item."""
        
        date_stamp = mail.get_date()
        date_item = self._create_date_item(date_stamp)
        self.results_table.setItem(row_idx, 0, date_item)
        
        subject_item = QTableWidgetItem(mail.get_subject())
        self.results_table.setItem(row_idx, 1, subject_item)
        
        sender_receiver_text = self._get_sender_receiver(mail.get_authors(), my_email_addresses)
        sender_receiver_item = QTableWidgetItem(sender_receiver_text)
        self.results_table.setItem(row_idx, 2, sender_receiver_item)
        
        # Store the message ID for lookup
        self.results_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, mail.get_message_id())
        
    def _create_date_item(self, timestamp):
        """Creates a sortable QTableWidgetItem for the date."""
        if not isinstance(timestamp, (int, float)):
            timestamp = 0
            
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
        date_string = dt.strftime("%Y-%m-%d %H:%M")
        
        item = QTableWidgetItem(date_string)
        item.setData(Qt.ItemDataRole.UserRole, timestamp)
        return item
        
    def _get_sender_receiver(self, authors_string, my_email_addresses):
        """Extracts the sender/receiver based on my email addresses."""
        addresses = getaddresses([authors_string])
        
        # If all addresses are mine, it's a message I sent.
        if all(addr in my_email_addresses for _, addr in addresses):
            return "You"

        # Find the first address that is not mine.
        for name, addr in addresses:
            if addr not in my_email_addresses:
                return name if name else addr
                
        # Fallback if no external address is found (e.g., self-sent email not in my_email_addresses)
        return "Unknown"

    def open_selected_item(self, index):
        """Launches the appropriate viewer based on the selected item."""
        if not self.notmuch_enabled:
            return
            
        row = index.row()
        item_id = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        if self.view_mode == "threads":
            if item_id:
                logging.info(f"Launching thread viewer for thread ID: {item_id}")
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-mail.py")
                    subprocess.Popen(["python3", viewer_path, "--thread", item_id])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch thread viewer: {e}")
            else:
                logging.warning("Could not find thread ID for selected row.")
        else: # mails mode
            if item_id:
                logging.info(f"Launching mail viewer for message ID: {item_id}")
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-mail.py")
                    subprocess.Popen(["python3", viewer_path, "--id", item_id])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find mail ID for selected row.")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View notmuch query results in a list.")
    parser.add_argument("--query", help="The notmuch query to display.", default="tag:inbox or tag:unread")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    viewer = QueryResultsViewer(args.query)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
