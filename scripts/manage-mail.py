#!/usr/bin/env python3

import sys
import os
import json
import subprocess
import shutil
from pathlib import Path
import time
import secrets
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QStyledItemDelegate, QLineEdit, QInputDialog
)
from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QRect, QPoint
from PySide6.QtGui import QMouseEvent, QFontMetrics, QAction
import logging

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from config import config
from query import QueryParser
from common import display_error, create_draft, create_new_mail_menu


class CustomLineEdit(QLineEdit):
    """A custom line edit that prevents text selection and handles clicks properly."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Prevent selection on focus in
        self.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, False)
        
    def mousePressEvent(self, event):
        # Process the mouse press without selecting text
        cursor_pos = self.cursorPositionAt(event.position().toPoint())
        super().mousePressEvent(event)
        self.deselect()
        self.setCursorPosition(cursor_pos)
        
    def focusInEvent(self, event):
        # Get cursor position before focus event
        cursor_pos = self.cursorPosition()
        
        # Call parent implementation
        super().focusInEvent(event)
        
        # Clear any selection and restore cursor position
        self.deselect()
        self.setCursorPosition(cursor_pos)


class NoSelectTextDelegate(QStyledItemDelegate):
    """A delegate that creates a custom line edit that doesn't select text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.click_pos = None
        
    def createEditor(self, parent, option, index):
        editor = CustomLineEdit(parent)
        editor.setFont(config.get_text_font())
        return editor
    
    def setEditorData(self, editor, index):
        # Get the text from the model
        text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        
        # Set the text in the editor
        editor.setText(text)
        
        # Ensure no text is selected
        editor.deselect()
        
        # If we have a click position, use it to position the cursor
        if self.click_pos and isinstance(editor, QLineEdit):
            cursor_pos = editor.cursorPositionAt(self.click_pos)
            editor.setCursorPosition(cursor_pos)
            
        # Set cursor position based on click position
        QTimer.singleShot(0, lambda: self.position_cursor_at_click(editor))
    
    def position_cursor_at_click(self, editor):
        """Position cursor at click position and ensure no text is selected."""
        if isinstance(editor, QLineEdit) and self.click_pos:
            cursor_pos = editor.cursorPositionAt(self.click_pos)
            editor.deselect()
            editor.setCursorPosition(cursor_pos)
    
    def setClickPosition(self, pos):
        """Store the click position for use in positioning the cursor."""
        self.click_pos = pos


class QueryEditor(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Mail Client")
        self.resize(QSize(800, 600))
        
        self.query_parser = QueryParser(config.config_path.parent)
        
        # Create our custom delegate
        self.text_delegate = NoSelectTextDelegate()
        
        # Track double-click detection
        self.last_click_time = 0
        self.last_click_pos = None
        self.double_click_interval = QApplication.instance().styleHints().mouseDoubleClickInterval()
        self.is_double_click_pending = False
        
        # Flag to track if we're currently processing a cell change
        self.is_processing_cell_change = False
        # Flag to track if we're moving a row
        self.is_moving_row = False
        
        # Store context menu position for later use
        self.context_menu_row = -1
        self.context_menu_column = -1
        
        self.setup_ui()
        self.load_queries_into_table()
        
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
        
        self.edit_drafts_button = QPushButton("Edit Draft")
        self.edit_drafts_button.setFont(config.get_interface_font())
        self.edit_drafts_button.clicked.connect(self.edit_drafts_action)
        top_bar_layout.addWidget(self.edit_drafts_button)
        
        top_bar_layout.addStretch()
        
        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # Set up the table
        self.query_table = QTableWidget()
        self.query_table.setColumnCount(2)
        self.query_table.setHorizontalHeaderLabels(["Name", "Query Expression"])
        self.query_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.query_table.horizontalHeader().setVisible(False)
        self.query_table.verticalHeader().setVisible(False)
        self.query_table.setFont(config.get_text_font())
        
        # Configure editing triggers
        self.query_table.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked | 
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        
        # Enable context menu
        self.query_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.query_table.customContextMenuRequested.connect(self.show_context_menu)
        
        # Use our custom delegate
        self.query_table.setItemDelegate(self.text_delegate)
        
        # Connect signals
        self.query_table.cellChanged.connect(self.handle_cell_changed)
        self.query_table.cellDoubleClicked.connect(self.handle_cell_double_clicked)
        
        # Install event filter to track mouse position
        self.query_table.viewport().installEventFilter(self)
        
        # Remove the blue selection highlight with stylesheet
        self.query_table.setStyleSheet("""
            QTableWidget {
                selection-background-color: transparent;
                outline: none; /* Remove focus outline */
            }
            QTableWidget::item:selected {
                background-color: transparent;
                color: black; /* Keep text color normal */
                border: 1px solid #888; /* Subtle border to show selection */
            }
            QTableWidget::item:focus {
                background-color: transparent;
                border: 1px solid #888;
            }
        """)

        main_layout.addWidget(self.query_table)

    def eventFilter(self, obj, event):
        """Track mouse position and force immediate edit mode on click."""
        if obj is self.query_table.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                # Only handle left mouse button presses here
                if event.button() == Qt.MouseButton.LeftButton:
                    # Get the position and determine which cell was clicked
                    pos = event.position().toPoint()
                    row = self.query_table.rowAt(pos.y())
                    column = self.query_table.columnAt(pos.x())
                    
                    if row >= 0 and column >= 0:
                        # Check for potential double click by looking at time since last click
                        current_time = int(time.time() * 1000)  # Current time in milliseconds
                        
                        # If this is within double-click interval, don't start edit mode yet
                        if (current_time - self.last_click_time < self.double_click_interval and 
                            self.last_click_pos and 
                            (pos - self.last_click_pos).manhattanLength() < 5):
                            
                            # This is likely part of a double-click, don't do anything yet
                            self.is_double_click_pending = True
                            return False
                        
                        # Reset click tracking
                        self.last_click_time = current_time
                        self.last_click_pos = pos
                        self.is_double_click_pending = False
                        
                        # Calculate position relative to the cell
                        item_rect = self.query_table.visualRect(self.query_table.model().index(row, column))
                        cell_pos = pos - item_rect.topLeft()
                        
                        # Store the click position in the delegate
                        self.text_delegate.setClickPosition(cell_pos)
                        
                        # Schedule editing to start after double-click interval has passed
                        QTimer.singleShot(self.double_click_interval + 10, 
                                         lambda: self.delayed_start_editing(row, column))
                    
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                # Handle double click - we'll let the table's built-in handler call the double-click handler
                self.is_double_click_pending = False
                return False  # Let the event propagate to trigger cellDoubleClicked
                
        return super().eventFilter(obj, event)
    
    def show_context_menu(self, position):
        """Show context menu with options to delete, edit, or execute a query."""
        # Get the row and column at the context menu position
        row = self.query_table.rowAt(position.y())
        column = self.query_table.columnAt(position.x())
        
        # Skip if we're outside the table or on the empty input row
        if row < 0 or column < 0 or row == 0:
            return
        
        # Store the row and column for later use
        self.context_menu_row = row
        self.context_menu_column = column
        
        # Create context menu
        context_menu = QMenu(self)
        context_menu.setFont(config.get_text_font())
        
        # Add actions
        execute_action = QAction("Execute", self)
        execute_action.triggered.connect(self.execute_row)
        
        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(self.edit_row)
        
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_row)
        
        # Add actions to menu in the preferred order
        context_menu.addAction(execute_action)
        context_menu.addAction(edit_action)
        context_menu.addAction(delete_action)
        
        # Show context menu at the right position
        context_menu.exec(self.query_table.viewport().mapToGlobal(position))

    def delete_row(self):
        """Delete the row that was right-clicked without confirmation."""
        if self.context_menu_row > 0:  # Ensure we're not deleting the empty input row
            # Remove the row directly without confirmation
            self.query_table.removeRow(self.context_menu_row)
            
            # Save the changes
            self.save_queries_from_table()
            
            # Reset context menu position
            self.context_menu_row = -1
            self.context_menu_column = -1

    def edit_row(self):
        """Start editing the cell that was right-clicked."""
        if self.context_menu_row > 0 and self.context_menu_column >= 0:
            # Get the item
            item = self.query_table.item(self.context_menu_row, self.context_menu_column)
            if item:
                # Edit the item
                self.query_table.editItem(item)

    def execute_row(self):
        """Execute the query in the row that was right-clicked (same as double-click)."""
        if self.context_menu_row > 0:
            # Move the row to top and open it, just like double-click
            self.move_row_to_top(self.context_menu_row)
            self.open_query_results(1, self.context_menu_column)
    
    def delayed_start_editing(self, row, column):
        """Start editing after a delay to allow for double-click detection."""
        # Check if we're in a double-click sequence
        if self.is_double_click_pending:
            # Reset and don't start editing
            self.is_double_click_pending = False
            return
            
        # Make sure the item exists
        item = self.query_table.item(row, column)
        if item:
            # Start editing the item
            self.query_table.editItem(item)
            
            # Get the editor and ensure no text is selected
            editor = self.query_table.indexWidget(self.query_table.model().index(row, column))
            if isinstance(editor, QLineEdit):
                editor.deselect()
                
                # If the delegate has a click position, use it
                if self.text_delegate.click_pos:
                    cursor_pos = editor.cursorPositionAt(self.text_delegate.click_pos)
                    editor.setCursorPosition(cursor_pos)

    def load_queries_into_table(self):
        """Loads named queries from the parser into the table and adds an empty row at the top."""
        queries = self.query_parser.queries
        
        # Set row count to include queries plus one empty row at the top
        row_count = len(queries) + 1
        self.query_table.setRowCount(row_count)
        
        # Temporarily disconnect the signal to avoid repeated saves during loading
        self.query_table.cellChanged.disconnect(self.handle_cell_changed)
        
        # Add the empty row at the top (index 0)
        self.add_empty_row_at_top()
        
        # Load the rest of the queries starting from index 1
        for i, (name, query) in enumerate(queries):
            row = i + 1  # Start at row 1, after the empty row
            
            name_item = QTableWidgetItem(name)
            name_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 0, name_item)
            
            query_item = QTableWidgetItem(query)
            query_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 1, query_item)
            
        # Reconnect the signal
        self.query_table.cellChanged.connect(self.handle_cell_changed)


    def add_new_rule(self, label, query):
        self.query_table.insertRow(1)
        label_item = QTableWidgetItem(label)
        label_item.setFont(config.get_text_font())
        self.query_table.setItem(1, 0, label_item)
        query_item = QTableWidgetItem(query)
        query_item.setFont(config.get_text_font())
        self.query_table.setItem(1, 1, query_item)

    def handle_new_label(self,editor):
        new_label = editor.text().strip()
        new_query =""
        self.add_new_rule(new_label, new_query)
        editor.clear()

    def handle_new_query(self,editor):
        new_label = ""
        new_query = editor.text().strip()
        self.add_new_rule(new_label, new_query)
        editor.clear()

    def add_empty_row_at_top(self):
        """Adds an empty row at the top of the table."""
        label_editor = QLineEdit()
        label_editor.setPlaceholderText("label")
        self.query_table.setCellWidget(0, 0, label_editor)
        label_editor.returnPressed.connect(lambda: self.handle_new_label(label_editor))

        # Right column: Query
        query_editor = QLineEdit()
        query_editor.setPlaceholderText("new search expression")
        self.query_table.setCellWidget(0, 1, query_editor)
        query_editor.returnPressed.connect(lambda: self.handle_new_query(query_editor))

    def handle_cell_changed(self, row, column):
        """Handles cell changes and creates a new row if needed."""
        # Check if we're already processing a change to avoid recursion
        if self.is_processing_cell_change or self.is_moving_row:
            return
            
        self.is_processing_cell_change = True
        
        try:
            # Get the items from the changed row
            name_item = self.query_table.item(row, 0)
            query_item = self.query_table.item(row, 1)
            
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            
            # If the top row (row 0) was changed and has content, add a new empty row
            if row == 0 and (name or query):
                # Insert a new empty row at the top
                self.query_table.insertRow(0)
                
                # Add empty items to the new top row
                self.add_empty_row_at_top()
                
                # Update the UI to reflect the change
                self.query_table.update()
            elif row > 0 and (name or query):
                # If this is not the empty input row and has content, move it to the top position (row 1)
                self.move_row_to_top(row)
            
            # Save all queries
            self.save_queries_from_table()
        finally:
            self.is_processing_cell_change = False

    def handle_cell_double_clicked(self, row, column):
        """Handles double click event - opens query results and moves row to top."""
        # Skip the top empty row
        if row == 0:
            return
            
        # Move the row to the top of the list (just below the empty input row)
        self.move_row_to_top(row)
        
        # Now open the query results
        self.open_query_results(1, column)  # Use row 1 since the item is now there

    def move_row_to_top(self, row):
        """Moves a row to the top of the list (just below the empty input row at row 0)."""
        # Don't move if it's already at the top or it's the empty input row
        if row <= 1:
            return
            
        # Set the flag to prevent triggering cell change events
        self.is_moving_row = True
        
        try:
            # Extract the data from the row to be moved
            name_item = self.query_table.item(row, 0)
            query_item = self.query_table.item(row, 1)
            
            name = name_item.text() if name_item else ""
            query = query_item.text() if query_item else ""
            
            # Remove the row
            self.query_table.removeRow(row)
            
            # Insert a new row at position 1 (just below the empty input row)
            self.query_table.insertRow(1)
            
            # Add the items to the new row
            new_name_item = QTableWidgetItem(name)
            new_name_item.setFont(config.get_text_font())
            self.query_table.setItem(1, 0, new_name_item)
            
            new_query_item = QTableWidgetItem(query)
            new_query_item.setFont(config.get_text_font())
            self.query_table.setItem(1, 1, new_query_item)
            
            # Save the changes
            self.save_queries_from_table()
            
            # Select the moved row
            self.query_table.setCurrentCell(1, 0)
        finally:
            self.is_moving_row = False

    def save_queries_from_table(self):
        """Saves the contents of the table back to the queries file, skipping the empty top row."""
        queries_to_save = []
        
        # Start from row 1 to skip the empty top row
        for row in range(1, self.query_table.rowCount()):
            name_item = self.query_table.item(row, 0)
            query_item = self.query_table.item(row, 1)
            
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            
            # Only save non-empty rows
            if name or query:
                queries_to_save.append([name, query])
        
        try:
            with open(self.query_parser.queries_path, "w") as f:
                json.dump({"queries": queries_to_save}, f)
            logging.info("Queries saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save queries: {e}")
            display_error(self, "Save Error", f"Failed to save queries to file:\n\n{e}")

    def open_query_results(self, row, column):
        """Launches show-query-results.py with the selected query."""
        logging.info(f"Opening query results for row {row}, column {column}")
        
        # Skip the top empty row
        if row == 0:
            return
            
        name_item = self.query_table.item(row, 0)
        query_item = self.query_table.item(row, 1)

        name = name_item.text().strip() if name_item else ""
        query_expression = query_item.text().strip() if query_item else ""
        
        if not query_expression:
            return # Don't open an empty query

        final_query = ""
        if name:
            final_query = f"${name}"
        else:
            final_query = query_expression
        
        try:
            viewer_path = os.path.join(os.path.dirname(__file__), "show-query-results.py")
            subprocess.Popen(["python3", viewer_path, "--query", final_query])
            logging.info(f"Launched query viewer with query: {final_query}")
        except Exception as e:
            logging.error(f"Failed to launch query viewer: {e}")
            display_error(self, "Launch Error", f"Could not launch show-query-results.py:\n\n{e}")
            
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
        menu.setFont(config.get_text_font())
        for identity in identities:
            action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
            action = menu.addAction(action_text)
            action.triggered.connect(lambda checked, i=identity: self._launch_drafts_manager(i))

        # Get the position of the Edit Drafts button and show the menu
        button_pos = self.edit_drafts_button.mapToGlobal(self.edit_drafts_button.rect().bottomLeft())
        menu.exec(button_pos)

    def _launch_drafts_manager(self, identity_dict):
        """Launches the drafts manager script for a given identity's drafts folder."""
        try:
            drafts_path_str = identity_dict.get('drafts', "~/.local/share/kubux-mail-client/mail/drafts")
            drafts_path = Path(drafts_path_str).expanduser()

            viewer_path = os.path.join(os.path.dirname(__file__), "open-drafts.py")
            subprocess.Popen(["python3", viewer_path, "--drafts-dir", str(drafts_path)])
            logging.info(f"Launched drafts manager for directory: {drafts_path}")
        except Exception as e:
            logging.error(f"Failed to launch drafts manager: {e}")
            display_error(self, "Launch Error", f"Could not launch open-drafts.py:\n\n{e}")

# --- Main Entry Point ---
def main():
    app = QApplication(sys.argv)
    editor = QueryEditor()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
