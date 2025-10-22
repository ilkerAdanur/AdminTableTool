# YENİ main.py (Sadece başlatıcı)
import sys
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow  # Yeni yerinden import et
from src.core.utils import register_pdf_fonts # (utils.py'ye taşıyacağız)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # register_pdf_fonts() # Fontları (eğer utils'e taşırsak) burada yükle

    window = MainWindow()
    window.show()
    sys.exit(app.exec())