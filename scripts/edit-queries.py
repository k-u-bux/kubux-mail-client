#!/usr/bin/env python3

import sys
import os
import json
import subprocess
from pathlib import Path
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QStyledItemDelegate, QLineEdit
)
from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QRect, QPoint
from PySide6.QtGui import QMouseEvent, QFontMetrics
import logging

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from config import config
from query import QueryParser
from common import display_error


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
        self.setWindowTitle("Edit Named Queries")
        self.resize(QSize(800, 600))
        
        self.query_parser = QueryParser(config.config_path.parent)
        
        # Create our custom delegate
        self.text_delegate = NoSelectTextDelegate()
        
        # Track double-click detection
        self.last_click_time = 0
        self.last_click_pos = None
        self.double_click_interval = QApplication.instance().styleHints().mouseDoubleClickInterval()
        self.is_double_click_pending = False
        
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
        
        self.new_query_button = QPushButton("New Query")
        self.new_query_button.setFont(config.get_interface_font())
        self.new_query_button.clicked.connect(self.add_new_row)
        top_bar_layout.addWidget(self.new_query_button)

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
        self.query_table.verticalHeader().setVisible(False)
        self.query_table.setFont(config.get_text_font())
        
        # Configure editing triggers
        self.query_table.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked | 
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        
        # Use our custom delegate
        self.query_table.setItemDelegate(self.text_delegate)
        
        # Connect signals
        self.query_table.cellChanged.connect(self.save_queries_from_table)
        self.query_table.cellDoubleClicked.connect(self.open_query_results)
        
        # Install event filter to track mouse position
        self.query_table.viewport().installEventFilter(self)

        main_layout.addWidget(self.query_table)

    def eventFilter(self, obj, event):
        """Track mouse position and force immediate edit mode on click."""
        if obj is self.query_table.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
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
                # Handle double click - we'll let the table's built-in handler call open_query_results
                self.is_double_click_pending = False
                return False  # Let the event propagate to trigger cellDoubleClicked
                
        return super().eventFilter(obj, event)
    
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
        """Loads named queries from the parser into the table."""
        queries = self.query_parser.queries
        self.query_table.setRowCount(len(queries))
        
        # Temporarily disconnect the signal to avoid repeated saves during loading
        self.query_table.cellChanged.disconnect(self.save_queries_from_table)
        
        for row, (name, query) in enumerate(queries):
            name_item = QTableWidgetItem(name)
            name_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 0, name_item)
            
            query_item = QTableWidgetItem(query)
            query_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 1, query_item)
            
        self.query_table.cellChanged.connect(self.save_queries_from_table)

    def save_queries_from_table(self):
        queries_to_save = []
        for row in range(self.query_table.rowCount()):
            name_item = self.query_table.item(row, 0)
            query_item = self.query_table.item(row, 1)
            
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            
            if name or query:
                queries_to_save.append([name, query])
        
        try:
            with open(self.query_parser.queries_path, "w") as f:
                json.dump({"queries": queries_to_save}, f)
            logging.info("Queries saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save queries: {e}")
            display_error(self, "Save Error", f"Failed to save queries to file:\n\n{e}")
            
    def add_new_row(self):
        """Adds a new empty row to the table."""
        row_count = self.query_table.rowCount()
        self.query_table.insertRow(row_count)
        
        name_item = QTableWidgetItem("")
        name_item.setFont(config.get_text_font())
        self.query_table.setItem(row_count, 0, name_item)
        
        query_item = QTableWidgetItem("")
        query_item.setFont(config.get_text_font())
        self.query_table.setItem(row_count, 1, query_item)
        
        # Select the new row
        self.query_table.setCurrentCell(row_count, 0)

    def open_query_results(self, row, column):
        """Launches show-query-results.py with the selected query."""
        logging.info(f"Opening query results for row {row}, column {column}")
        
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


# --- Main Entry Point ---
def main():
    app = QApplication(sys.argv)
    editor = QueryEditor()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
