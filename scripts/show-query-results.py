#!/usr/bin/env python3

import sys
import argparse
import os
import subprocess
import json
import logging
import textwrap
import email
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QPushButton, QAbstractItemView, QMessageBox, QDialog, QDialogButtonBox,
    QLabel, QSplitter, QComboBox, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QAction
from config import Config, config

try:
    import notmuch
    NOTMUCH_BINDINGS_AVAILABLE = True
except ImportError:
    NOTMUCH_BINDINGS_AVAILABLE = False
    
# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CopyableErrorDialog(QDialog):
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("The following error occurred:")
        layout.addWidget(label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(message)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(config.get_font('text'))
        layout.addWidget(self.text_edit)
        
        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self.copy_message)
        layout.addWidget(self.copy_button)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
        
    def copy_message(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        QMessageBox.information(self, "Copied", "Error message copied to clipboard.")

class QueryResultsViewer(QMainWindow):
    def __init__(self, initial_query):
        super().__init__()
        self.setWindowTitle("Notmuch Mail Client")
        
        self.setCentralWidget(QWidget())
        self.layout = QVBoxLayout(self.centralWidget())
        
        # UI Elements
        self.query_edit = QLineEdit(initial_query)
        self.query_edit.setPlaceholderText("Enter a notmuch query (e.g., 'tag:inbox and tag:unread')")
        self.query_edit.returnPressed.connect(self.execute_query)
        self.query_edit.setFont(config.get_font('interface'))

        self.view_mode_selector = QComboBox()
        self.view_mode_selector.addItems(["threads", "messages"])
        self.view_mode_selector.currentTextChanged.connect(self.update_view_mode)
        self.view_mode = "threads"

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.execute_query)
        
        self.query_layout = QHBoxLayout()
        self.query_layout.addWidget(self.query_edit)
        self.query_layout.addWidget(self.view_mode_selector)
        self.query_layout.addWidget(self.search_button)
        
        self.results_table = QTableWidget()
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.cellDoubleClicked.connect(self.open_message)

        # Set up a central splitter to be able to dynamically add the mail viewer
        self.central_splitter = QSplitter(Qt.Horizontal)
        self.central_splitter.addWidget(self.results_table)
        self.layout.addLayout(self.query_layout)
        self.layout.addWidget(self.central_splitter)
        
        self.results = []
        self.execute_query()
        
    def update_view_mode(self, mode):
        self.view_mode = mode
        self.execute_query()

    def get_my_email_addresses(self):
        """Returns a set of my email addresses from the config file."""
        identities = config.get_identities()
        return {id['email'] for id in identities}

    def execute_query(self):
        if not NOTMUCH_BINDINGS_AVAILABLE:
            dialog = CopyableErrorDialog(
                "Notmuch Bindings Not Found",
                "The 'notmuch' Python bindings were not found. Please ensure they are installed."
            )
            dialog.exec()
            return
            
        self.current_query = self.query_edit.text()
        logging.info(f"Executing query: '{self.current_query}' in '{self.view_mode}' mode.")
        
        my_email_addresses = self.get_my_email_addresses()
        
        try:
            with notmuch.Database(mode=notmuch.Database.MODE.READ_ONLY) as db:
                query = db.query(self.current_query)
                self.results = []
                
                if self.view_mode == "threads":
                    for thread in query.search_threads():
                        # Get a list of messages to find oldest/newest
                        messages = list(thread.get_messages())
                        if messages:
                            oldest_message = messages[0]
                            newest_message = messages[-1]

                            thread_summary = {
                                "id": thread.get_thread_id(),
                                "subject": thread.get_subject(),
                                "authors": thread.get_authors(),
                                "oldest_date_utc": thread.get_oldest_date(),
                                "newest_date_utc": thread.get_newest_date(),
                                "total_messages": thread.get_total_messages(),
                                "thread_data": messages  # Store the full thread data
                            }
                            self.results.append(thread_summary)
                else: # messages mode
                    for message in query.search_messages():
                        self.results.append(message)
                
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
        if self.view_mode == "threads":
            columns = ["Author", "Subject", "Date (Newest)", "Date (Oldest)"]
        else: # messages
            columns = ["Author", "Subject", "Date"]

        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(self.results))
        
        for row_idx, item in enumerate(self.results):
            if self.view_mode == "threads":
                author_text = self.format_authors(item.get("authors", ""), my_email_addresses)
                self.results_table.setItem(row_idx, 0, QTableWidgetItem(author_text))
                self.results_table.setItem(row_idx, 1, QTableWidgetItem(item.get("subject", "")))
                self.results_table.setItem(row_idx, 2, QTableWidgetItem(self.format_date(item.get("newest_date_utc"))))
                self.results_table.setItem(row_idx, 3, QTableWidgetItem(self.format_date(item.get("oldest_date_utc"))))
            else: # messages
                author_text = self.format_authors(item.get("authors", ""), my_email_addresses)
                self.results_table.setItem(row_idx, 0, QTableWidgetItem(author_text))
                self.results_table.setItem(row_idx, 1, QTableWidgetItem(item.get("subject", "")))
                self.results_table.setItem(row_idx, 2, QTableWidgetItem(self.format_date(item.get("date"))))

        self.results_table.resizeColumnsToContents()
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def format_authors(self, authors_string, my_email_addresses):
        """Removes self from author list and adds a '... (+X others)' if needed."""
        addresses = email.utils.getaddresses([authors_string])
        other_authors = [
            f"{name}" if name else email
            for name, email in addresses
            if email not in my_email_addresses
        ]
        
        if not other_authors:
            return "Me"
        
        first_author = other_authors[0]
        if len(other_authors) > 1:
            return f"{first_author} (+{len(other_authors) - 1} others)"
        else:
            return first_author

    def format_date(self, timestamp):
        """Formats a Unix timestamp to a human-readable date string."""
        if timestamp is None:
            return ""
        try:
            from datetime import datetime
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError) as e:
            logging.error(f"Failed to format timestamp {timestamp}: {e}")
            return str(timestamp)
    
    def open_message(self, row, column):
        item_data = self.results[row]
        if self.view_mode == "threads":
            thread_data = item_data.get("thread_data", [])
            if not thread_data:
                QMessageBox.warning(self, "No Messages", "This thread contains no messages.")
                return
            
            # We open the first message of the thread for now.
            # In a full app, you would likely open a dedicated thread viewer.
            first_message_id = thread_data[0].get_message_id()
            if not first_message_id:
                QMessageBox.critical(self, "Error", "Could not get message ID for this thread.")
                return
            
            try:
                # The assumption is that `view-mail.py` is in the same directory.
                script_path = os.path.join(os.path.dirname(__file__), "view-mail.py")
                # Using the message ID is a better way to launch the viewer if it supports it.
                # If not, you'd have to pass a file path which requires a search.
                subprocess.Popen(['python3', script_path, '--id', first_message_id])
                
            except FileNotFoundError:
                QMessageBox.critical(self, "Error", f"Could not find view-mail.py at {script_path}")
                
        else: # messages mode
            message_id = item_data.get_message_id()
            if message_id:
                try:
                    script_path = os.path.join(os.path.dirname(__file__), "view-mail.py")
                    subprocess.Popen(['python3', script_path, '--id', message_id])
                except FileNotFoundError:
                    QMessageBox.critical(self, "Error", f"Could not find view-mail.py at {script_path}")
            else:
                QMessageBox.critical(self, "Error", "Could not get message ID for this message.")

def main():
    parser = argparse.ArgumentParser(description="View notmuch query results in a table.")
    parser.add_argument("query", nargs="?", default="tag:inbox and tag:unread",
                        help="The notmuch query to execute.")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    viewer = QueryResultsViewer(args.query)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
