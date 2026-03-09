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
from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QRect, QPoint, QMimeData, QByteArray, QDataStream, QIODevice
from PySide6.QtGui import QMouseEvent, QFontMetrics, QAction, QDrag, QColor
import logging

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from config import config
from query import QueryParser
from common import display_error, create_draft, create_new_mail_menu, launch_drafts_manager


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


class DragHandleDelegate(QStyledItemDelegate):
    """A delegate that paints a drag handle icon in the handle column."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.handle_column = 2
    
    def paint(self, painter, option, index):
        if index.column() == self.handle_column:
            rect = option.rect
            handle_height = 10
            handle_width = 15
            x = rect.x() + (rect.width() - handle_width) // 2
            y = rect.y() + (rect.height() - handle_height) // 2
            
            painter.setPen(QColor("gray"))
            # Drawing a simple 3-bar handle
            for i in range(3):
                offset = i * 4
                painter.drawLine(x, y + offset, x + handle_width, y + offset)
        else:
            super().paint(painter, option, index)


class QueryEditor(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kubux Mail Client")
        self.resize(QSize(800, 600))
        
        self.query_parser = QueryParser(config.config_path.parent)
        
        # Create our custom delegates
        self.text_delegate = NoSelectTextDelegate()
        self.drag_handle_delegate = DragHandleDelegate()
        
        # Drag-and-drop related variables
        self.dragging_row = -1
        self.drag_start_pos = None
        self.handle_column = 2
        
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
        main_layout.setContentsMargins(8, 8, 8, 8)

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

        self.edit_config_button = QPushButton("Edit Config")
        self.edit_config_button.setFont(config.get_interface_font())
        self.edit_config_button.clicked.connect(self.edit_config_action)
        top_bar_layout.addWidget(self.edit_config_button)
        
        top_bar_layout.addStretch()
        
        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(config.get_interface_font())
        self.quit_button.clicked.connect(self.close)
        top_bar_layout.addWidget(self.quit_button)
        
        # Set up the table with 3 columns now
        self.query_table = QTableWidget()
        self.query_table.setColumnCount(3)
        self.query_table.setHorizontalHeaderLabels(["Name", "Query Expression", "Move"])
        self.query_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.query_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.query_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.query_table.setColumnWidth(2, 40)  # Narrow handle column
        self.query_table.horizontalHeader().setVisible(False)
        self.query_table.verticalHeader().setVisible(False)
        self.query_table.setFont(config.get_text_font())
        
        # Configure editing triggers
        self.query_table.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked | 
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        
        # Enable drag and drop
        self.query_table.setAcceptDrops(True)
        self.query_table.viewport().setAcceptDrops(True)
        self.query_table.setDropIndicatorShown(True)
        self.query_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        # Enable context menu
        self.query_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.query_table.customContextMenuRequested.connect(self.show_context_menu)
        
        # Set delegates for different columns
        for col in range(2):  # Columns 0 and 1
            self.query_table.setItemDelegateForColumn(col, self.text_delegate)
        self.query_table.setItemDelegateForColumn(2, self.drag_handle_delegate)
        
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

    def dragEnterEvent(self, event):
        """Accept drag enter events."""
        if event.mimeData().hasFormat("application/x-query-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move with real-time preview."""
        if not event.mimeData().hasFormat("application/x-query-row"):
            event.ignore()
            return
        
        pos = event.position().toPoint()
        viewport_pos = self.query_table.viewport().mapFrom(self, pos)
        target_row = self.query_table.rowAt(viewport_pos.y())
        
        # Don't allow dropping on row 0
        if target_row > 0:
            event.acceptProposedAction()
            self.previewRowMove(target_row)
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle drop event."""
        if not event.mimeData().hasFormat("application/x-query-row"):
            event.ignore()
            return
        
        pos = event.position().toPoint()
        viewport_pos = self.query_table.viewport().mapFrom(self, pos)
        target_row = self.query_table.rowAt(viewport_pos.y())
        
        # Protect row 0
        if target_row <= 0:
            event.ignore()
            return
        
        # Row already moved by preview, just finalize
        event.acceptProposedAction()
        self.dragging_row = -1
        self.save_queries_from_table()

    def previewRowMove(self, target_row):
        """Show real-time preview of row movement (adapted for QTableWidget)."""
        if self.dragging_row <= 0 or target_row <= 0 or self.dragging_row == target_row:
            return
        
        # Set flag to prevent save during preview
        self.is_moving_row = True
        
        try:
            # Save row data using takeItem()
            row_data = []
            for col in range(3):  # Now 3 columns
                item = self.query_table.takeItem(self.dragging_row, col)
                row_data.append(item)
            
            # Also save any cell widgets
            widgets = []
            for col in range(3):
                widget = self.query_table.cellWidget(self.dragging_row, col)
                if widget:
                    self.query_table.removeCellWidget(self.dragging_row, col)
                    widgets.append(widget)
                else:
                    widgets.append(None)
            
            # Remove old row
            self.query_table.removeRow(self.dragging_row)
            
            # Adjust target if needed
            if target_row > self.dragging_row:
                target_row -= 1
            
            # Insert at new position
            self.query_table.insertRow(target_row)
            for col, item in enumerate(row_data):
                if item:
                    self.query_table.setItem(target_row, col, item)
                else:
                    # Create empty item for handle column
                    self.query_table.setItem(target_row, col, QTableWidgetItem(""))
            
            for col, widget in enumerate(widgets):
                if widget:
                    self.query_table.setCellWidget(target_row, col, widget)
            
            # Update tracking
            self.dragging_row = target_row
            self.query_table.selectRow(target_row)
        
        finally:
            self.is_moving_row = False

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
                    
                    # Handle drag column clicks - initiate drag
                    if column == self.handle_column and row > 0:
                        self.drag_start_pos = pos
                        self.dragging_row = row
                        self.query_table.selectRow(row)
                        return True  # Consume the event
                    
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
                    
            elif event.type() == QEvent.Type.MouseMove:
                # Handle mouse move for dragging
                if self.drag_start_pos is not None and self.dragging_row > 0:
                    pos = event.position().toPoint()
                    
                    # Check if we've moved far enough to start dragging
                    if (pos - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                        # Create and execute drag
                        drag = QDrag(self.query_table)
                        mime_data = QMimeData()
                        
                        # Encode row index
                        byte_array = QByteArray()
                        stream = QDataStream(byte_array, QIODevice.OpenModeFlag.WriteOnly)
                        stream.writeInt32(self.dragging_row)
                        
                        mime_data.setData("application/x-query-row", byte_array)
                        drag.setMimeData(mime_data)
                        
                        # Execute drag
                        drag.exec(Qt.DropAction.MoveAction)
                        
                        # Reset drag state
                        self.dragging_row = -1
                        self.drag_start_pos = None
                        return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease:
                # Reset drag state if mouse released without dragging
                if event.button() == Qt.MouseButton.LeftButton:
                    self.dragging_row = -1
                    self.drag_start_pos = None
            
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
        context_menu.setFont(config.get_menu_font())
        
        # Add actions (removed move actions)
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
            self.open_query_results(self.context_menu_row, self.context_menu_column)
    
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
            
            # Add empty item for handle column
            handle_item = QTableWidgetItem("")
            self.query_table.setItem(row, 2, handle_item)
            
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
        # Add empty item for handle column
        handle_item = QTableWidgetItem("")
        self.query_table.setItem(1, 2, handle_item)

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
        
        # Handle column: empty (will show drag handle via delegate for other rows)
        self.query_table.setItem(0, 2, QTableWidgetItem(""))

    def handle_cell_changed(self, row, column):
        """Handles cell changes and creates a new row if needed."""
        # Check if we're already processing a change to avoid recursion
        if self.is_processing_cell_change or self.is_moving_row:
            return
            
        self.is_processing_cell_change = True
        
        try:
            # Get the items from the changed row (only first two columns matter)
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
            
            # Save all queries
            self.save_queries_from_table()
        finally:
            self.is_processing_cell_change = False

    def handle_cell_double_clicked(self, row, column):
        """Handles double click event - opens query results."""
        # Skip the top empty row and handle column
        if row == 0 or column == self.handle_column:
            return
        
        # Open the query results
        self.open_query_results(row, column)

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
            viewer_path = os.path.join(os.path.dirname(__file__), "show-query-results")
            subprocess.Popen([viewer_path, "--query", final_query])
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
        menu.setFont(config.get_menu_font())
        for identity in identities:
            action_text = f"From: {identity.get('name', '')} <{identity.get('email', '')}>"
            action = menu.addAction(action_text)
            action.triggered.connect(lambda checked, i=identity: launch_drafts_manager(self,i))

        # Get the position of the Edit Drafts button and show the menu
        button_pos = self.edit_drafts_button.mapToGlobal(self.edit_drafts_button.rect().bottomLeft())
        menu.exec(button_pos)

    def edit_config_action(self):
        try:
            subprocess.Popen(["xdg-open", config.config_path])
            logging.info(f"Launched xdg-open {config.config_path}")
        except Exception as e:
            logging.error(f"Failed to launch config editor: {e}")
            display_error(self, "Launch Error", f"Could not launch config editor:\n\n{e}")



# --- Main Entry Point ---
def main():
    app = QApplication(sys.argv)
    # app.setApplicationDisplayName( "Kubux Mail Client" )
    app.setApplicationName( "KubuxMailClient" )
    editor = QueryEditor()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
