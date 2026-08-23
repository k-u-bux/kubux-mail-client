#!/usr/bin/env python3

"""
Custom table widget for mail client views with 3 columns (Date|Column2|Subject).
Provides shared functionality for column management and hover effects.
"""

from PySide6.QtWidgets import (
    QTableWidget, QHeaderView, QAbstractItemView, QProxyStyle, QApplication, QStyle,
    QStyledItemDelegate,
)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QFontMetrics, QPalette

from config import config


class ClipTextDelegate(QStyledItemDelegate):
    """Paint text cells clipped at the cell edge instead of elided with '...'.

    Qt's item views draw over-long cell text with Qt's Ellipsis (``ElideRight``
    via ``QStyle::drawItemText``, which hardcodes ``ElideRight`` whenever the
    ``Qt::TextDontClip`` flag is not set), yielding entries like "to: ...".
    Setting ``option.textElideMode = ElideNone`` is NOT enough, because the
    style ignores it.  So we render the background/selection via the base
    class while suppressing its text pass, and then draw the text ourselves,
    clipped to the column width: it is cut off exactly where the right padding
    begins, with no ellipsis.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # While True, initStyleOption blanks the cell text so the base class
        # paints only background/selection and adds no ellipsis of its own.
        self._suppress_text = False

    def initStyleOption(self, option, widget=None):
        super().initStyleOption(option, widget)
        if self._suppress_text:
            option.text = ""

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        alignment = index.data(Qt.ItemDataRole.TextAlignmentRole) or \
            (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._suppress_text = True
        try:
            super().paint(painter, option, index)  # background/selection/focus
        finally:
            self._suppress_text = False

        if not text:
            return

        # Draw the real text, single line, honoring per-item alignment,
        # clipped at the content rect (= cell minus the left/right padding).
        padding = config.get_padding()
        rect = option.rect.adjusted(padding, 0, -padding, 0)
        painter.save()
        painter.setClipRect(rect)
        painter.setFont(option.font)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText))
        else:
            painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, alignment | Qt.TextFlag.TextSingleLine, text)
        painter.restore()


class ElideTextDelegate(QStyledItemDelegate):
    """The classic Qt behavior: over-long cell text is elided with Qt's
    Ellipsis ('...'), e.g. 'to: ...'. Installing this (globally or per column)
    restores the previous rendering.

    Note: ``QStyle::drawItemText`` hardcodes ``ElideRight`` whenever the
    ``Qt::TextDontClip`` flag is absent, so the default item view elides
    regardless of ``textElideMode``; this delegate just makes that explicit.
    """
    def initStyleOption(self, option, widget=None):
        super().initStyleOption(option, widget)
        option.textElideMode = Qt.TextElideMode.ElideRight


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

        # Per-column cell-text behavior: clip (no '...') by default; columns
        # listed in self._elide_columns keep the classic Qt ellipsis.
        self._elide_columns = set()
        self._apply_delegates()
        
        # Configure column resizing
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
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
        self.setStyleSheet(f"""
            QTableWidget {{ selection-background-color: rgb(100, 149, 237); color: palette(text); outline: none; }}
            QTableWidget::item {{ padding-left: {config.get_padding()}px; padding-right: {config.get_padding()}px; }}
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
    
    def _date_column_width(self):
        fm = QFontMetrics(config.get_text_font())
        # Date format used by create_date_item: "%Y-%m-%d %H:%M".
        return fm.horizontalAdvance("2026-08-21 09:30") + 2*config.get_padding() + config.get_buffer()

    def _fix_column_widths(self, ratio):
        """Distribute available width between columns 1 and 2 based on ratio.
        """
        total_width = self.viewport().width()
        header = self.horizontalHeader()

        date_col_width = self._date_column_width()
        self.setColumnWidth(0, date_col_width)

        remaining_width = total_width - date_col_width
        if remaining_width <= 0:
            return

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

    def _apply_delegates(self):
        """(Re)install per-column delegates.

        Columns in ``self._elide_columns`` render over-long text with Qt's
        classic '...' ellipsis (ElideTextDelegate); every other column clips
        the text at the cell edge (ClipTextDelegate).  The table-wide delegate
        is also set to clip so any column not explicitly configured behaves
        like the rest.
        """
        for col in range(self.columnCount()):
            if col in self._elide_columns:
                self.setItemDelegateForColumn(col, ElideTextDelegate(self))
            else:
                self.setItemDelegateForColumn(col, ClipTextDelegate(self))
        self.setItemDelegate(ClipTextDelegate(self))

    def set_elide_columns(self, columns):
        """Choose which columns render over-long text with Qt's '...' ellipsis
        instead of clipping at the cell edge.

        ``columns`` is a column index or an iterable of column indices.  Call
        with ``()`` (or ``set()``) to switch every column back to clipped.
        """
        if isinstance(columns, int):
            columns = [columns]
        self._elide_columns = set(columns)
        self._apply_delegates()
        if self.viewport() is not None:
            self.viewport().update()

    def update_font(self):
        """Reapply font from config (called on config changes)."""
        self.setFont(config.get_text_font())
        self.horizontalHeader().setHighlightSections(False)
        self._fix_column_widths(self._width_ratio)
        fm = QFontMetrics(config.get_text_font())
        row_height = fm.height() + 4
        for row in range(self.rowCount()):
            self.setRowHeight(row, row_height)

    def clear_and_reset_hover(self):
        """Clear the table and reset hover state."""
        self._hovered_row = -1
        self.setRowCount(0)
        self.clearContents()

# end of file
