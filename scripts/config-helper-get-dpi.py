from PySide6.QtWidgets import QApplication

def get_physically_scaled_font(target_mm: float, family: str = "Arial"):
    app = QApplication.instance()
    screen = app.primaryScreen()
    
    # Get the actual hardware density
    phys_dpi = screen.physicalDotsPerInch()
    
    # Calculate pixels: (mm / mm_per_inch) * dots_per_inch
    pixel_size = int((target_mm / 25.4) * phys_dpi)
    
    font = QFont(family)
    font.setPixelSize(pixel_size)
    return font

# Usage
app = QApplication([])
screen = app.primaryScreen()
phys_dpi = screen.physicalDotsPerInch()
print( phys_dpi )

