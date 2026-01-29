from PySide6.QtWidgets import QApplication
app = QApplication([])
screen = app.primaryScreen()
phys_dpi = screen.physicalDotsPerInch()
print( phys_dpi )
