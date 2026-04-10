import logging
from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QDrag, QGuiApplication, QCursor

class GlobalDragFilter(QObject):
    def eventFilter(self, watched, event):
        # Intercepts events to manage drag-and-drop state.
        
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                logging.info("Mouse release detected. Cancel active drag.")
                self._terminate_drag( watched )

        if event.type() == QEvent.Type.DragMove:
            if not ( event.buttons() & Qt.MouseButton.LeftButton ):
                logging.info("Detected button release during DragMove. Force cancelling.")
                self._terminate_drag( watched )
   
        # Return False to let the event propagate to the widget
        return False

    def _terminate_drag(self, watched):
        """Cancels the drag and forces the cursor to reset."""
        QDrag.cancel()
        
        # Remove the global override cursor if one was set by the drag system
        while QGuiApplication.overrideCursor() is not None:
            QGuiApplication.restoreOverrideCursor()
            
        # Explicitly reset the cursor for the widget currently being hovered
        if hasattr(watched, 'setCursor'):
            watched.setCursor( QCursor( Qt.CursorShape.ArrowCursor ) )
        
        # Optional: update the application-wide cursor state
        QGuiApplication.setOverrideCursor( QCursor( Qt.CursorShape.ArrowCursor ) )
        QGuiApplication.restoreOverrideCursor()
