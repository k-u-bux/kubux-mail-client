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
    QMessageBox, QDialog, QDialogButtonBox, QLabel, QTextEdit, QInputDialog,
    QCheckBox, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging

from notmuch import notmuch_show, flatten_message_tree, find_matching_messages, find_matching_threads, apply_tag_to_query
from config import config
from common import display_error

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ThreadViewer(QMainWindow):
    def __init__(self, thread_id, parent=None):
        super().__init__(parent)
        self.thread_id = thread_id
        self.setWindowTitle("Kubux Mail Client - Thread Viewer")
        self.resize(QSize(1024, 768))

        self.view_mode = "tree" # or "list"
        self.results = []

        self.setup_ui()
        self.setup_key_bindings()
        self.execute_query()

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setFont(config.get_text_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Top bar with buttons
        top_bar_layout = QHBoxLayout()
        main_layout.addLayout(top_bar_layout)

        self.view_mode_button = QPushButton("Tree View (toggle for list view)")
        self.view_mode_button.setFont(config.get_interface_font())
        self.view_mode_button.clicked.connect(self.toggle_view_mode)
        top_bar_layout.addWidget(self.view_mode_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setFont(config.get_interface_font())
        self.refresh_button.clicked.connect(self.execute_query)
        top_bar_layout.addWidget(self.refresh_button)

        top_bar_layout.addStretch()

        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # Table view to serve as both list and tree view
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Date", "Sender/Receiver", "Subject"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSortingEnabled(True)
        self.results_table.doubleClicked.connect(self.open_selected_item)
        # Enable context menu
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.results_table)

    def show_context_menu(self, position):
        """Show context menu with options to delete, edit, or execute a query."""
        # Get the row and column at the context menu position
        row = self.results_table.rowAt(position.y())
        column = self.results_table.columnAt(position.x())
        
        # Skip if we're outside the table or on the empty input row
        if row < 0 or column < 0:
            return
        
        # Store the row and column for later use
        self.context_menu_row = row
        self.context_menu_column = column
        
        # Create context menu
        context_menu = QMenu(self)
        context_menu.setFont(config.get_text_font())
        
        selected_items = self.results_table.selectedItems();

        # Add actions
        open_action = QAction("Open", self)
        flag_action = QAction("+spam", self)
        delete_action = QAction("Delete", self)
        modify_action = QAction("Edit Tags", self)
        if selected_items:
            open_action.triggered.connect( self.open_selected_items )
            flag_action.triggered.connect( self.flag_spam_selected_items )
            delete_action.triggered.connect( self.delete_selected_items )
            modify_action.triggered.connect( self.modify_selected_items )
        else:
            open_action.triggered.connect( lambda r=row: self.open_selected_row( r ) )
            flag_action.triggered.connect( lambda r=row: self.flag_spam_row( r ) )
            delete_action.triggered.connect( lambda r=row: self.delete_row( r ) )
            modify_action.triggered.connect( lambda r=row: self.modify_row( r ) )
        
        # Add actions to menu in the preferred order
        context_menu.addAction(open_action)
        context_menu.addAction(flag_action)
        context_menu.addAction(delete_action)
        context_menu.addAction(modify_action)
        
        # Show context menu at the right position
        context_menu.exec(self.results_table.viewport().mapToGlobal(position))

    def showEvent(self, event):
        """Called when the widget is shown."""
        super().showEvent(event)
        
        if self.results_table.rowCount() == 0:
            return

        total_width = self.results_table.viewport().width()
        date_col_width = self.results_table.columnWidth(0)
        remaining_width = total_width - date_col_width

        subject_col_width = int(remaining_width * 0.70)
        sender_col_width = int(remaining_width * 0.30)
        
        self.results_table.setColumnWidth(1, sender_col_width)
        self.results_table.setColumnWidth(2, subject_col_width)

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
        if self.view_mode == "tree":
            self.view_mode = "list"
            self.view_mode_button.setText("List View (toggle for tree view)")
        else:
            self.view_mode = "tree"
            self.view_mode_button.setText("Tree View (toggle for list view)")
        self.execute_query()

    def execute_query(self):
        logging.info(f"Executing query for thread ID: {self.thread_id}")
        self.results_table.setRowCount(0)
        self.results_table.clearContents()
        flattened_messages = find_matching_messages(f"thread:{self.thread_id}",
                                                    lambda *args: display_error(self, *args))
        if self.view_mode == "tree":
            self.results_table.setSortingEnabled(False)
            self._populate_table(flattened_messages, indent=True)
        else: # list mode
            self.results_table.setSortingEnabled(False)
            self._populate_table(flattened_messages, indent=False)
            self.results_table.setSortingEnabled(True)
        
    def _populate_table(self, messages, indent):
        """Populates the QTableWidget from a flattened list of messages."""
        self.results_table.setRowCount(len(messages))
        for row_idx, mail in enumerate(messages):
            date_item = self._create_date_item(mail.get("timestamp"))
            sender_receiver_text = self._get_sender_receiver(mail)
            sender_receiver_item = QTableWidgetItem(sender_receiver_text)
            
            subject_text = mail.get("headers", {}).get("Subject", "No Subject")
            if indent:
                indent_string = "    " * mail.get('depth', 0)
                subject_text = indent_string + subject_text
            subject_item = QTableWidgetItem(subject_text)
            
            self.results_table.setItem(row_idx, 0, date_item)
            self.results_table.setItem(row_idx, 1, sender_receiver_item)
            self.results_table.setItem(row_idx, 2, subject_item)
            
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
        
    def _get_sender_receiver(self, message):
        """Extracts the sender/receiver based on my email address."""
        from_field = message.get("headers", {}).get("From", "unknown <nobody@nowhere.net>")
        if isinstance(from_field, str):
            authors_string_list = [from_field]
        else: # assuming it's a list
            authors_string_list = from_field
        if not config.is_me(authors_string_list):
            return from_field
        else:
            return "to: " + message.get("headers", {}).get("To", "unknown <nobody@nowhere.net>")

    def open_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.open_selected_row( row )

    def open_selected_item(self, index):
        self.open_selected_row( index.row() )
        
    def open_selected_row(self, row):
        mail_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            
        if mail_data:
            mail_file_path = mail_data.get("filename")
            if mail_file_path:
                logging.info(f"Launching mail viewer for file: {mail_file_path}")
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-mail")
                    subprocess.Popen([viewer_path, mail_file_path[0]])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find mail file path for selected row.")

    # other actions
    def show_error(self, title, message):
        display_error( self, title, message )

    def row_to_query(self, row):
        item_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)        
        if self.view_mode == "threads":
            thread_id = item_data.get("thread")
            return f"thread:{thread_id}"
        else:
            message_id = item_data.get("id")
            return f"id:{message_id}"

    def apply_tag_to_row(self, pm_tag, row):
        apply_tag_to_query( pm_tag, self.row_to_query(row), self.show_error )

    def tag_dialog(self):
        text, ok = QInputDialog.getText(self, "Tags", "+/-tag(s) (separated by commas):")
        if ok and text:
            return [t.strip() for t in text.split(',')]
        return []

    # spam
    def flag_spam_row(self, row):
        self.apply_tag_to_row("+spam", row)

    def flag_spam_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.flag_spam_row( row )

    def flag_spam_selected_item(self, index):
        row = index.row()
        self.flag_spam_row( row )

    # delete
    def delete_row(self, row):
        self.apply_tag_to_row("+delete", row)

    def delete_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.delete_row( row )

    def delete_selected_item(self, index):
        row = index.row()
        self.delete_row( row )

    # modify tags
    def modify_selected_items(self):
        tags = self.tag_dialog()
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            for tag in tags:
                self.apply_tag_to_row( tag, row )

    def modify_row(self, index):
        tags = self.tag_button()
        row = index.row()
        for tag in tags:
            self.apply_tag_to_row( tag, row )

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View messages in a specific notmuch thread.")
    parser.add_argument("thread_id", help="The thread ID to display.")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    # app.setApplicationDisplayName( "Kubux Mail Client" )
    app.setApplicationName( "KubuxMailClient" )
    viewer = ThreadViewer(args.thread_id)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
