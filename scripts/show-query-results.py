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
    QCheckBox, QAbstractItemView, QMenu, QWidgetAction
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging

from notmuch import find_matching_messages, find_matching_threads, apply_tag_to_query, get_tags_from_query, update_unseen_from_query
from config import config
from common import display_error, create_draft, create_new_mail_menu, launch_drafts_manager
from query import QueryParser

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class QueryResultsViewer(QMainWindow):
    def __init__(self, query_string=config.get_search(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Mail Client - Search Results")
        self.resize(QSize(1024, 768))

        self.view_mode = "mails" # either "threads" or "mails"
        self.current_query = query_string
        self.results = []
        self._width_ratio = 0.3
        self._is_window_resize = True

        self.setup_ui()
        self.setup_key_bindings()
        self.execute_query()

    def _flag_resize(self, flag):
        self._is_window_resize = flag

    def setup_ui(self):
        query_parser = QueryParser(config_dir=config.config_dir)
        central_widget = QWidget()
        central_widget.setFont(config.get_text_font())
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # a) Top row: quit button right, on the left two buttons "refresh" and a button that changes
        top_bar_layout = QHBoxLayout()
        main_layout.addLayout(top_bar_layout)
        
        # View mode toggle button
        if self.view_mode == "threads":
            self.view_mode_button = QPushButton("Thread View (toggle for mail view)")
        else:
            self.view_mode_button = QPushButton("Mail View (toggle for thread view)")
            
        self.view_mode_button.setFont(config.get_interface_font())
        self.view_mode_button.clicked.connect(self.toggle_view_mode)
        top_bar_layout.addWidget(self.view_mode_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setFont(config.get_interface_font())
        self.refresh_button.clicked.connect(self.execute_query)
        top_bar_layout.addWidget(self.refresh_button)

        top_bar_layout.addStretch()

        self.new_mail_button = QPushButton("New Mail")
        self.new_mail_button.setFont(config.get_interface_font())
        top_bar_layout.addWidget(self.new_mail_button)
        self.new_mail_button.clicked.connect(self.new_mail_action)
        
        self.edit_drafts_button = QPushButton("Edit Draft")
        self.edit_drafts_button.setFont(config.get_interface_font())
        self.edit_drafts_button.clicked.connect(self.edit_drafts_action)
        top_bar_layout.addWidget(self.edit_drafts_button)

        # self.edit_config_button = QPushButton("Edit Config")
        # self.edit_config_button.setFont(config.get_interface_font())
        # self.edit_config_button.clicked.connect(self.edit_config_action)
        # top_bar_layout.addWidget(self.edit_config_button)
        # 
        # self.manager_button = QPushButton("Searches")
        # self.manager_button.setFont(config.get_interface_font())
        # self.manager_button.clicked.connect(self.launch__manager)
        # top_bar_layout.addWidget(self.manager_button)

        top_bar_layout.addStretch()

        self.more_button = QPushButton("More")
        self.more_button.setFont(config.get_interface_font())
        self.more_menu = QMenu(self)
        self.more_menu.setFont(config.get_menu_font())
        self.more_menu.addAction("Edit Config").triggered.connect(self.edit_config_action)
        self.more_menu.addAction("Edit Queries").triggered.connect(self.launch__manager)
        self.more_menu.addSeparator()
        for named_query in query_parser.names:
            logging.info(f"add menu entry for query {named_query}.")
            self.more_menu.addAction(f"${named_query}").triggered.connect( lambda _, dummy=named_query: self.launch_query(dummy))
        self.more_button.setMenu(self.more_menu)
        top_bar_layout.addWidget(self.more_button)
        # top_bar_layout.addStretch()
        
        # Quit button
        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # b) below the top row: an edit box for the query.
        self.query_edit = QLineEdit(self.current_query)
        self.query_edit.setFont(config.get_interface_font())
        self.query_edit.returnPressed.connect(self.execute_query)
        main_layout.addWidget(self.query_edit)

        # c) I like the table below.
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        # self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setStretchLastSection(False)
        self.results_table.horizontalHeader().sectionResized.connect(self._on_column_width_changed)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSortingEnabled(True)
        # Enable context menu
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_context_menu)
        # self.results_table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        # self.results_table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        # self.results_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)

        main_layout.addWidget(self.results_table)
        
        # Connect click to action
        self.results_table.doubleClicked.connect(self.open_selected_item)

    def show_context_menu(self, position):
        """Show context menu with options to delete, edit, or execute a query."""
        # Get the row and column at the context menu position
        row = self.results_table.rowAt(position.y())
        column = self.results_table.columnAt(position.x())
        
        # Skip if we're outside the table or on the empty input row
        if row < 0 or column < 0:
            return
        
        # Create context menu
        context_menu = QMenu(self)
        context_menu.setFont(config.get_menu_font())
        
        selected_items = self.results_table.selectedItems();

        # Add actions
        open_action = QAction("Open", self)
        open_thread_action = QAction("Open Thread", self)
        mark_read_action = QAction("-unread", self)
        flag_action = QAction("+spam", self)
        delete_action = QAction("Delete", self)
        modify_action = QAction("Edit Tags", self)
        if selected_items:
            open_action.triggered.connect( self.open_selected_items )
            open_thread_action.triggered.connect( self.open_thread_selected_items )
            mark_read_action.triggered.connect( self.mark_read_selected_items )
            flag_action.triggered.connect( self.flag_spam_selected_items )
            delete_action.triggered.connect( self.delete_selected_items )
            modify_action.triggered.connect( self.modify_selected_items )
        else:
            open_action.triggered.connect( lambda r=row: self.open_selected_row( row ) )
            open_thread_action.triggered.connect( lambda r=row: self.open_thread_selected_row( row ) )
            mark_read_action.triggered.connect( lambda r=row: self.mark_read_row( row ) )
            flag_action.triggered.connect( lambda r=row: self.flag_spam_row( row ) )
            delete_action.triggered.connect( lambda r=row: self.delete_row( row ) )
            modify_action.triggered.connect( lambda r=row: self.modify_row( row ) )
        
        # Add actions to menu in the preferred order
        context_menu.addAction(open_action)
        if not self.view_mode == "thread":
            context_menu.addAction(open_thread_action)
        context_menu.addAction(mark_read_action)
        context_menu.addAction(flag_action)
        context_menu.addAction(delete_action)
        context_menu.addAction(modify_action)
        if not selected_items:
            context_menu.addSeparator()
            info_widget_action = QWidgetAction(context_menu)           
            info_string = " ".join( [ s for s in self.get_tags( row ) if not s.startswith("$") ] )
            info_label = QLabel( info_string )
            info_label.setFont(config.get_text_font())
            info_label.setStyleSheet("QLabel { padding-top: 3px; padding-bottom: 5px;  padding-left: 10px; padding-right: 10px; }")
            info_widget_action.setDefaultWidget(info_label)
            context_menu.addAction( info_widget_action )
        
        # Show context menu at the right position
        context_menu.exec(self.results_table.viewport().mapToGlobal(position))

    def _on_column_width_changed(self, logical_index, old_size, new_size):
        """User drags column divider → update stored ratios."""
        if logical_index in [1, 2]:  # Subject or Sender
            if not self._is_window_resize:
                self._update_ratio_from_widths()
                self._fix_column_widths(self._width_ratio)

    def _update_ratio_from_widths(self):
        """Calculate and store current Subject/Sender ratio."""
        sender_width = self.results_table.columnWidth(1)
        subject_width = self.results_table.columnWidth(2)
        total_width = subject_width + sender_width
        
        if total_width > 0:
            self._width_ratio = sender_width / total_width
            # print(f"new ratio = {self._width_ratio} from col1 = {sender_width} and col2 = {subject_width}")

    def _fix_column_widths(self,ratio):
        # Ensure the table is not empty to avoid errors
        if self.results_table.rowCount() == 0:
            return

        # Get the total available width of the table
        total_width = self.results_table.viewport().width()

        # Get the width of the Date column after it has been sized to its contents
        date_col_width = self.results_table.columnWidth(0)

        # Calculate the remaining space
        remaining_width = total_width - date_col_width

        # Calculate the target widths for Subject and Sender based on ratio
        subject_col_width = int(remaining_width * ratio)
        sender_col_width = int(remaining_width * (1.0 - ratio))

        # Apply the new widths
        self.results_table.setColumnWidth(1, subject_col_width)
        self.results_table.setColumnWidth(2, sender_col_width)

    def showEvent(self, event):
        """Called when the widget is shown."""
        super().showEvent(event)
        self._fix_column_widths(self._width_ratio)

    def resizeEvent(self, event):
        """Called when the widget is resized."""
        super().resizeEvent(event)
        self._flag_resize( True )
        self._fix_column_widths(self._width_ratio)
        QTimer.singleShot( 250, lambda: self._flag_resize( False ) )

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
            self.view_mode_button.setText("Mail View (toggle for thread view)")
        else:
            self.view_mode = "threads"
            self.view_mode_button.setText("Thread View (toggle for mail view)")
        self.execute_query()

    def execute_query(self):
        parser = QueryParser(config_dir=config.config_dir)
        self.current_query = parser.parse( self.query_edit.text() )
        logging.info(f"Executing query: '{self.current_query}' in '{self.view_mode}' mode.")
        
        self.results_table.setRowCount(0)
        self.results_table.clearContents()
        
        if self.view_mode == "threads":
            self._execute_threads_query()
        else: # mails mode
            self._execute_mails_query()
            
    def _execute_threads_query(self):
        """Fetches and populates the table with thread data."""
        self.results = find_matching_threads(self.current_query, display_error)
        self.results_table.setHorizontalHeaderLabels(["Date", "Authors", "Subject"])
        self.results_table.setRowCount(len(self.results))
        self.results_table.setSortingEnabled(False)
        for row_idx, thread in enumerate(self.results):
            self._update_row_for_thread(row_idx, thread)
        self.results_table.setSortingEnabled(True)

    def _execute_mails_query(self):
        """Fetches and populates the table with mail data."""
        self.results = find_matching_messages(self.current_query, display_error)
        self.results_table.setHorizontalHeaderLabels(["Date", "Sender/Receiver", "Subject"])
        self.results_table.setRowCount(len(self.results))
        self.results_table.setSortingEnabled(False)
        for row_idx, mail in enumerate(self.results):
            self._update_row_for_mail(row_idx, mail)
        self.results_table.setSortingEnabled(True)
        
    def _update_row_for_thread(self, row_idx, thread):
        """Helper to populate a row for a thread item from `notmuch search --output=summary`."""
        
        date_stamp = thread.get("timestamp")
        subject_text = f"<{thread.get('total')}> {thread.get('subject')}"
        authors_text = thread.get("authors", "unknown")
        summary_text = f"{authors_text}: {subject_text}"

        date_item = self._create_date_item(date_stamp)
        subject_item = QTableWidgetItem(subject_text)
        authors_item = QTableWidgetItem(authors_text)

        date_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)
        subject_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)
        authors_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)

        self.results_table.setItem(row_idx, 0, date_item)        
        self.results_table.setItem(row_idx, 2, subject_item)
        self.results_table.setItem(row_idx, 1, authors_item)
        
        self.results_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, thread)

    def _update_row_for_mail(self, row_idx, mail):
        """Helper to populate a row for a mail item from `notmuch show`."""
        date_stamp = mail.get("timestamp")
        subject_text = mail.get("headers", {}).get("Subject", "No Subject")
        sender_receiver_text = self._get_sender_receiver(mail)
        summary_text = f"{sender_receiver_text}: {subject_text}"

        date_item = self._create_date_item(date_stamp)
        subject_item = QTableWidgetItem(subject_text)
        sender_receiver_item = QTableWidgetItem(sender_receiver_text)

        date_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)
        subject_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)
        sender_receiver_item.setData(Qt.ItemDataRole.ToolTipRole, summary_text)

        self.results_table.setItem(row_idx, 0, date_item)
        self.results_table.setItem(row_idx, 2, subject_item)
        self.results_table.setItem(row_idx, 1, sender_receiver_item)
        
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

    def new_mail_action(self):
        """Creates and displays a menu for selecting an email identity."""
        create_new_mail_menu(self)
                    
    def edit_drafts_action(self):
        """
        Displays a menu of identities and launches open-drafts.py
        for the selected identity's drafts folder.
        """
        identities = config.get_identities()
        if not identities:
            display_error(self, "Identities not found", "No email identities are configured. Please check your config file.")
            return

        menu = QMenu(self)
        menu.setFont(config.get_menu_font())
        for identity in identities:
            action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
            action = menu.addAction(action_text)
            action.triggered.connect(lambda checked, i=identity: launch_drafts_manager(self,i))

        # Get the position of the Edit Drafts button and show the menu
        button_pos = self.edit_drafts_button.mapToGlobal(self.edit_drafts_button.rect().bottomLeft())
        menu.exec(button_pos)


    def new_search_action(self):
        try:
            viewer_path = os.path.join(os.path.dirname(__file__), "show-query-results")
            # subprocess.Popen([viewer_path, "--query", " "])
            subprocess.Popen([viewer_path])
            logging.info(f"Launched query viewer without query.")
        except Exception as e:
            logging.error(f"Failed to launch query viewer: {e}")
            display_error(self, "Launch Error", f"Could not launch show-query-results.py:\n\n{e}")

            
    def launch__manager(self):
        try:
            manager_path = os.path.join(os.path.dirname(__file__), "manage-mail")
            subprocess.Popen([ manager_path ])
            logging.info(f"Launched manage-mail")
        except Exception as e:
            logging.error(f"Failed to launch mail manager: {e}")
            display_error(self, "Launch Error", f"Could not launch manage-mail.py:\n\n{e}")

    def launch_query(self, name):
        logging.info(f"name = {name}")
        try:
            viewer_path = os.path.join(os.path.dirname(__file__), "show-query-results")
            subprocess.Popen([viewer_path, "--query", f"${name}"])
            logging.info(f"Launched query viewer with query: ${name}")
        except Exception as e:
            logging.error(f"Failed to launch query viewer: {e}")
            display_error(self, "Launch Error", f"Could not launch show-query-results.py:\n\n{e}")


    # get_tags
    def get_tags( self, row ):
        item_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        tags = item_data.get("tags")
        return tags


    # open
    def open_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.open_selected_row( row )

    def open_selected_item(self, index):
        """Launches the appropriate viewer based on the selected item."""
        row = index.row()
        self.open_selected_row( row )

    def open_selected_row(self, row):
        item_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        if self.view_mode == "threads":
            # notmuch search with --output=summary returns a "thread" key
            thread_id = item_data.get("thread")
            if thread_id:
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-thread")
                    subprocess.Popen([viewer_path, thread_id])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find thread ID for selected row.")
        else: # mails mode
            mail_file_path = item_data.get("filename")
            if mail_file_path:
                logging.info(f"Launching mail viewer for file: {mail_file_path}")
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-mail")
                    subprocess.Popen([viewer_path, mail_file_path[0]])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find mail file path for selected row.")


    # open thread
    def open_thread_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.open_thread_selected_row( row )

    def open_thread_selected_item(self, index):
        """Launches the appropriate viewer based on the selected item."""
        row = index.row()
        self.open_thread_selected_row( row )

    def open_thread_selected_row(self, row):
        item_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        if self.view_mode == "threads":
            # notmuch search with --output=summary returns a "thread" key
            thread_id = item_data.get("thread")
            if thread_id:
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-thread")
                    subprocess.Popen([viewer_path, thread_id])
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not launch mail viewer: {e}")
            else:
                logging.warning("Could not find thread ID for selected row.")
        else: # mails mode
            message_id = item_data.get("id");
            command = ['notmuch', 'search', '--output=threads', '--format=text', f'id:{message_id} and (tag:spam or not tag:spam)']
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            threads = result.stdout.strip().split('\n')
            for thread_id in threads:
                try:
                    viewer_path = os.path.join(os.path.dirname(__file__), "view-thread")
                    subprocess.Popen([viewer_path, thread_id.replace("thread:","")])
                except Exception as e:
                    display_error(self, "Error", f"Could not launch mail viewer: {e}")


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
        update_unseen_from_query( self.row_to_query(row), self.show_error )

    def tag_dialog(self):
        text, ok = QInputDialog.getText(self, "Tags", "+/-tag(s) (separated by commas):")
        if ok and text:
            return [t.strip() for t in text.split(',')]
        return []

    # mark read
    def mark_read_row(self, row):
        self.apply_tag_to_row("-unread", row)

    def mark_read_selected_items(self):
        for row in list( set( [ item.row() for item in self.results_table.selectedItems() ] ) ):
            self.mark_read_row( row )

    def mark_read_selected_item(self, index):
        row = index.row()
        self.mark_read_row( row )


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
        self.apply_tag_to_row("+deleted", row)

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
        tags = self.tag_dialog()
        row = index.row()
        for tag in tags:
            self.apply_tag_to_row( tag, row )

    def edit_config_action(self):
        try:
            subprocess.Popen(["xdg-open", config.config_path])
            logging.info(f"Launched xdg-open {config.config_path}")
        except Exception as e:
            logging.error(f"Failed to launch config editor: {e}")
            display_error(self, "Launch Error", f"Could not launch config editor:\n\n{e}")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="View notmuch query results in a list.")
    parser.add_argument("--query", help="The notmuch query to display.", default=config.get_search())
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    # app.setApplicationDisplayName( "Kubux Mail Client" )
    app.setApplicationName( "KubuxMailClient" )
    viewer = QueryResultsViewer(args.query)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
