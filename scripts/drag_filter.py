import logging
from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QDrag

class GlobalDragFilter(QObject):
    def eventFilter(self, watched, event):
        # Intercepts events to manage drag-and-drop state.
        
        # if event.type() == QEvent.Type.MouseButtonRelease:
        #     if event.button() == Qt.MouseButton.LeftButton:
        #         logging.info("Mouse release detected. Cancel active drag.")
        #         QDrag.cancel()

        if event.type() == QEvent.Type.DragMove:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                logging.info("Detected button release during DragMove. Force cancelling.")
                QDrag.cancel()
   
        # Return False to let the event propagate to the widget
        return False
