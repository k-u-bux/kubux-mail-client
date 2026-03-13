#!/usr/bin/env python3

"""
Custom table widget for mail client views with 3 columns (Date|Column2|Subject).
Provides shared functionality for column management and hover effects.
"""

from PySide6.QtWidgets import (
    QTableWidget, QHeaderView, QAbstractItemView, QProxyStyle, QApplication, QStyle
)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor

from config import config


class MailTableWidget(QTableWidget):
    """
    A QTableWidget configured for mail clients with column width management
    and hover highlighting.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Column width management
        self._width_ratio = 0.3
        self._is_window_resize = True
        
        # Hover highlighting
        self._hovered_row = -1
        
        # Set up the table
        self._setup_table()
    
    def _setup_table(self):
        """Configure the table with common settings."""
        # Create tooltip style that disables delay
        style = QProxyStyle()
        style.styleHint = lambda hint, opt, widget, data: \
            0 if hint == QStyle.SH_ToolTip_WakeUpDelay else \
            QApplication.style().styleHint(hint, opt, widget, data)
        
        self.setStyle(style)
        self.setColumnCount(3)
        self.setFont(config.get_text_font())
        
        # Configure column resizing
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().sectionResized.connect(self._on_column_width_changed)
        
        # Hide vertical header
        self.verticalHeader().setVisible(False)
        
        # Selection behavior
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Sorting
        self.setSortingEnabled(True)
        
        # Styling
        self.horizontalHeader().setHighlightSections(False)
        self.setStyleSheet("""
            QTableWidget { selection-background-color: rgb(100, 149, 237); color: palette(text); outline: none; }
            QTableWidget::item { padding-left: 4px; padding-right: 4px; }
        """)
        
        # Enable hover tracking
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
    
    # ========== Column Width Management ==========
    
    def _flag_resize(self, flag):
        """Mark whether we're in a window resize operation."""
        self._is_window_resize = flag
    
    def _on_column_width_changed(self, logical_index, old_size, new_size):
        """User drags column divider → update stored ratios."""
        if logical_index in [1, 2]:  # Column 1 or 2
            if not self._is_window_resize:
                self._update_ratio_from_widths()
                self._fix_column_widths(self._width_ratio)
    
    def _update_ratio_from_widths(self):
        """Calculate and store current Column1/Column2 ratio."""
        col1_width = self.columnWidth(1)
        col2_width = self.columnWidth(2)
        total_width = col1_width + col2_width
        
        if total_width > 0:
            self._width_ratio = col1_width / total_width
    
    def _fix_column_widths(self, ratio):
        """Distribute available width between columns 1 and 2 based on ratio."""
        if self.rowCount() == 0:
            return
        
        total_width = self.viewport().width()
        date_col_width = self.columnWidth(0)
        remaining_width = total_width - date_col_width
        
        col1_width = int(remaining_width * ratio)
        col2_width = int(remaining_width * (1.0 - ratio))
        
        self.setColumnWidth(1, col1_width)
        self.setColumnWidth(2, col2_width)
    
    def showEvent(self, event):
        """Called when the widget is shown."""
        super().showEvent(event)
        self._fix_column_widths(self._width_ratio)
    
    def resizeEvent(self, event):
        """Called when the widget is resized."""
        super().resizeEvent(event)
        self._flag_resize(True)
        self._fix_column_widths(self._width_ratio)
        QTimer.singleShot(250, lambda: self._flag_resize(False))
    
    # ========== Hover Highlighting ==========
    
    def eventFilter(self, obj, event):
        """Event filter to track mouse hover over table rows."""
        if obj == self.viewport():
            if event.type() == QEvent.Type.MouseMove:
                pos = event.pos()
                row = self.rowAt(pos.y())
                
                if row != self._hovered_row:
                    self._clear_hover_highlight(self._hovered_row)
                    self._hovered_row = row
                    self._apply_hover_highlight(row)
                    
            elif event.type() == QEvent.Type.Leave:
                self._clear_hover_highlight(self._hovered_row)
                self._hovered_row = -1
                
        return super().eventFilter(obj, event)
    
    def _apply_hover_highlight(self, row):
        """Apply light blue background to all cells in the row."""
        if row < 0 or row >= self.rowCount():
            return
        
        hover_color = QColor(100, 149, 237, 50)
        
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                item.setBackground(hover_color)
    
    def _clear_hover_highlight(self, row):
        """Clear background color from all cells in the row."""
        if row < 0 or row >= self.rowCount():
            return
        
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                item.setBackground(QColor(0, 0, 0, 0))
    
    # ========== Helper Methods ==========
    
    def clear_and_reset_hover(self):
        """Clear the table and reset hover state."""
        self._hovered_row = -1
        self.setRowCount(0)
        self.clearContents()
