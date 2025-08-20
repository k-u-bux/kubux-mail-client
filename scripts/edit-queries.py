#!/usr/bin/env python3

import sys
import os
import toml
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QStyledItemDelegate, QLineEdit
)
from PySide6.QtCore import Qt, QSize, QEvent, QTimer
from PySide6.QtGui import QMouseEvent
import logging

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from config import config
from query import QueryParser
from common import display_error


class CustomLineEdit(QLineEdit):
    """A custom line edit that doesn't select text on focus or click."""
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def mousePressEvent(self, event):
        # Get cursor position at click point
        cursor_pos = self.cursorPositionAt(event.pos())
        
        # Call parent implementation which handles selection
        super().mousePressEvent(event)
        
        # Immediately clear any selection and position cursor where clicked
        self.deselect()
        self.setCursorPosition(cursor_pos)
        
    def focusInEvent(self, event):
        # Call parent implementation
        super().focusInEvent(event)
        
        # Immediately clear any selection that was made
        cursor_pos = self.cursorPosition()
        self.deselect()
        self.setCursorPosition(cursor_pos)


class NoSelectTextDelegate(QStyledItemDelegate):
    """
    A delegate that creates a custom QLineEdit for editing table cells,
    ensuring text is never auto-selected.
    """
    def createEditor(self, parent, option, index):
        editor = CustomLineEdit(parent)
        editor.setFont(config.get_text_font())
        return editor
    
    def setEditorData(self, editor, index):
        # Get the text from the model
        text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        # Set the text in the editor without selecting it
        editor.setText(text)
        
        # Important: This deselects any text and moves cursor to end
        editor.deselect()
        
        # Schedule a second deselection after a tiny delay to handle any 
        # platform-specific focus behaviors
        QTimer.singleShot(0, editor.deselect)


class QueryEditor(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Named Queries")
        self.setMinimumSize(QSize(800, 600))
        
        self.query_parser = QueryParser(config.config_path.parent)
        
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
        
        # Editable table
        self.query_table = QTableWidget()
        self.query_table.setColumnCount(2)
        self.query_table.setHorizontalHeaderLabels(["Name", "Query Expression"])
        self.query_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.query_table.verticalHeader().setVisible(False)
        self.query_table.setFont(config.get_text_font())
        
        # Configure editing behavior
        self.query_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | 
            QAbstractItemView.EditTrigger.SelectedClicked | 
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        
        # Use our improved delegate for editing
        self.query_table.setItemDelegate(NoSelectTextDelegate())
        
        # Connect signals for saving and opening queries
        self.query_table.cellChanged.connect(self.save_queries_from_table)
        self.query_table.cellDoubleClicked.connect(self.open_query_results)

        main_layout.addWidget(self.query_table)

    def load_queries_into_table(self):
        """Loads named queries from the parser into the table."""
        queries = self.query_parser.named_queries
        self.query_table.setRowCount(len(queries))
        
        # Temporarily disconnect the signal to avoid repeated saves during loading
        self.query_table.cellChanged.disconnect(self.save_queries_from_table)
        
        for row, (name, query) in enumerate(queries.items()):
            name_item = QTableWidgetItem(name)
            name_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 0, name_item)
            
            query_item = QTableWidgetItem(query)
            query_item.setFont(config.get_text_font())
            self.query_table.setItem(row, 1, query_item)
            
        self.query_table.cellChanged.connect(self.save_queries_from_table)

    def save_queries_from_table(self):
        """Saves the contents of the table back to the queries.toml file."""
        queries_to_save = []
        for row in range(self.query_table.rowCount()):
            name_item = self.query_table.item(row, 0)
            query_item = self.query_table.item(row, 1)
            
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            
            if name or query:
                queries_to_save.append({"name": name, "query": query})
        
        try:
            with open(self.query_parser.queries_path, "w") as f:
                toml.dump({"queries": queries_to_save}, f)
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

    def open_query_results(self, row, column):
        """Launches show-query-results.py with the selected query."""
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
        except Exception as e:
            display_error(self, "Launch Error", f"Could not launch show-query-results.py:\n\n{e}")


# --- Main Entry Point ---
def main():
    app = QApplication(sys.argv)
    editor = QueryEditor()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
