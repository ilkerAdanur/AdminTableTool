# main.py

import sys
import os
import logging
from logging.handlers import RotatingFileHandler 
from PyQt6.QtWidgets import QApplication, QDialog
from src.ui.login_dialog import LoginDialog
from src.ui.main_window import MainWindow 
from src.core.utils import register_pdf_fonts 
from src.core.user_manager import get_current_user

def setup_logging():
    log_dir = os.path.join(os.path.expanduser('~'), "AdminTableToolLogs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "admintabletool.log.txt")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Konsola da yazsın (Geliştirme aşamasında hatayı görmek için)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logging.info("--- Loglama sistemi başlatıldı ---")

if __name__ == '__main__':
    setup_logging() 
    
    try:
        app = QApplication(sys.argv)
        register_pdf_fonts()
        
        # --- GİRİŞ - ÇIKIŞ DÖNGÜSÜ ---
        while True:
            # 1. Giriş Ekranını Göster
            login_window = LoginDialog()
            result = login_window.exec()

            # 2. Eğer Giriş Başarılıysa
            if result == QDialog.DialogCode.Accepted:
                current_user = get_current_user()
                
                # 3. Ana Pencereyi Aç
                window = MainWindow()
                window.show()
                
                # Dosya ile açılma kontrolü (Sadece ilk döngüde çalışmalı mantıken ama burada da durabilir)
                if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) and sys.argv[1].endswith(".tuem"):
                     # Argümanı temizle ki döngüde tekrar açmaya çalışmasın (basit bir önlem)
                     file_path = sys.argv[1]
                     sys.argv = [sys.argv[0]] 
                     window.load_tuem_file(file_path)

                # 4. Uygulama Çalışıyor (Pencere kapanana kadar bekle)
                app.exec()
                
                # 5. Pencere Kapandı. Neden? Çıkış mı, Kapatma mı?
                if window.logout_requested:
                    logging.info("Oturum kapatıldı, giriş ekranına dönülüyor...")
                    continue # Döngü başa döner -> Login açılır
                else:
                    logging.info("Uygulama tamamen kapatıldı.")
                    break # Döngü biter -> Program kapanır
            else:
                # Kullanıcı giriş ekranını kapattı (Cancel/X)
                break
        
        sys.exit(0)
        
    except Exception as e:
        logging.critical(f"Uygulama kritik hata ile durdu: {e}", exc_info=True)
        sys.exit(1)