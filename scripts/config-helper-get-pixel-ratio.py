from PySide6.QtWidgets import QApplication
app = QApplication([])
screen = app.primaryScreen()
pixel_ratio = screen.physicalDotsPerInch() / screen.logicalDotsPerInch()
print( pixel_ratio )
