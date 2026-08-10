from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QDialogButtonBox, QLabel, QTextEdit,
    QCheckBox, QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, QSize, QPoint, QObject, QTimer, QMetaObject
from PySide6.QtGui import QFont, QKeySequence, QAction
import logging
from pathlib import Path
from datetime import datetime
import secrets
import os
import atexit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DirectoryEventHandler(QObject, FileSystemEventHandler):
    def __init__(self, callback):
        QObject.__init__(self)
        FileSystemEventHandler.__init__(self)
        self.callback = callback
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._wrapped_cb)
        self.observer = None
        self.is_busy = False
        atexit.register(self.stop)

    def _wrapped_cb (self):
        self.is_busy = True
        try:
            self.callback()
        finally:
            self.is_busy = False

    def _process_event(self, event):
        if not self.is_busy:
            QMetaObject.invokeMethod(self.timer, "start", Qt.QueuedConnection)

    def on_created(self, event):
        self._process_event( event )

    def on_deleted(self, event):
        self._process_event( event )

    def on_moved(self, event):
        self._process_event( event )

    def on_modified(self, event):
        self._process_event( event )

    def watch(self, directory: str):
        real_path = os.path.realpath(os.path.expanduser(directory))
        if not real_path or not os.path.isdir(real_path):
            raise FileNotFoundError(f"DirectoryEventHandler cannot watch invalid path: {repr(directory)}")
        self.stop()
        self.observer = Observer()
        self.observer.daemon = True
        self.observer.schedule(self, real_path, recursive=True)
        self.observer.start()

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.timer.stop()

# end of file
