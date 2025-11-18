# main.py (Sadece başlatıcı)
import sys
import os
import logging
from logging.handlers import RotatingFileHandler  # <-- Bu sınıfı import edin
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow 
from src.core.utils import register_pdf_fonts 

def setup_logging():
    """Uygulama geneli için loglamayı ayarlar."""
    
    # --- Önceki tavsiyemize uygun olarak: Log dosyasını sabit yola değil,
    # --- kullanıcının ev dizinine (örn: C:\Users\ilker) kaydedelim.
    log_dir = os.path.join(os.path.expanduser('~'), "AdminTableToolLogs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "admintabletool.log.txt") # Log dosyamız

    # Ana loglayıcıyı (root logger) al
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Minimum log seviyesini ayarla (DEBUG, INFO, ERROR)

    # --- Log Rotasyonu Ayarları ---
    # maxBytes: Dosya maksimum 5MB olsun (5 * 1024 * 1024)
    # backupCount: 3 adet yedek dosya (log.txt.1, log.txt.2, log.txt.3) tut.
    # 5MB dolduğunda, 'log.txt' -> 'log.txt.1' olur, 'log.txt.3' silinir (FIFO).
    handler = RotatingFileHandler(
        log_file_path, 
        maxBytes=5 * 1024 * 1024, 
        backupCount=3,
        encoding='utf-8'
    )
    
    # Log formatını belirle: [Tarih/Saat] - SEVİYE - Mesaj
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Ayarladığımız handler'ı ana loglayıcıya ekle
    logger.addHandler(handler)

    # (Opsiyonel) Konsola da yazdırmaya devam etmek isterseniz:
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setFormatter(formatter)
    # logger.addHandler(console_handler)

    logging.info("--- Loglama sistemi başlatıldı ---")

if __name__ == '__main__':
    setup_logging() 
    
    try:
        app = QApplication(sys.argv)
        register_pdf_fonts()
        window = MainWindow()
        window.show()
        
        # --- YENİ: Başlangıçta dosya ile açılma kontrolü ---
        # sys.argv[0] programın kendisidir.
        # Eğer sys.argv[1] varsa, bu bir dosya yoludur (birlikte aç/çift tıklama).
        if len(sys.argv) > 1:
            file_to_open = sys.argv[1]
            if os.path.exists(file_to_open) and file_to_open.endswith(".att"):
                logging.info(f"Uygulama dosya ile başlatıldı: {file_to_open}")
                # MainWindow'daki yükleme fonksiyonunu çağır
                window.load_att_file(file_to_open)
        # ---------------------------------------------------

        sys.exit(app.exec())
        
    except Exception as e:
        # Uygulamanın çökmesine neden olan en kritik hataları yakala
        logging.critical(f"Uygulama kritik bir hata nedeniyle başlatılamadı veya çöktü: {e}", exc_info=True)
        sys.exit(1) # Hata koduyla çık