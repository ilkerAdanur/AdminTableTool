# src/ui/login_dialog.py

import os
import json
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt
from sqlalchemy import text
from src.core.database import create_db_engine
from src.core.config import DB_CONFIG
from src.core.user_manager import User, set_current_user
import logging

logger = logging.getLogger(__name__)

# Oturum bilgilerinin tutulacağı yerel dosya
SESSION_FILE = os.path.join(os.path.expanduser('~'), "AdminTableTool_Session.json")

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Giriş Yap - AdminTableTool")
        self.setFixedSize(300, 230) # Boyutu biraz artırdık
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Kullanıcı Adı:"))
        self.user_input = QLineEdit()
        layout.addWidget(self.user_input)

        layout.addWidget(QLabel("Şifre:"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pass_input)

        # --- YENİ: Beni Hatırla Kutucuğu ---
        self.chk_remember = QCheckBox("Beni Hatırla (Oturumu Açık Tut)")
        layout.addWidget(self.chk_remember)
        # -----------------------------------

        self.btn_login = QPushButton("Giriş Yap")
        self.btn_login.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.btn_login.clicked.connect(self.attempt_login)
        layout.addWidget(self.btn_login)
        
        # Eğer kayıtlı oturum varsa yükle
        self.load_session()

    def attempt_login(self):
        username = self.user_input.text().strip()
        password = self.pass_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen kullanıcı adı ve şifre giriniz.")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Bağlanılıyor...")
        self.repaint() # Arayüzün güncellenmesini zorla

        try:
            # 1. Veritabanına Bağlan
            engine = create_db_engine(DB_CONFIG)
            
            # 2. Kullanıcıyı Sorgula
            query = text("SELECT id, username, role, department FROM users WHERE username = :u AND password = :p")
            
            with engine.connect() as conn:
                result = conn.execute(query, {"u": username, "p": password}).fetchone()
            
            if result:
                # KULLANICI BULUNDU
                user = User(user_id=result[0], username=result[1], role=result[2], department=result[3])
                set_current_user(user)
                logger.info(f"Giriş Başarılı: {user}")
                self.save_session(username, password)
                self.accept()
            else:
                # BAĞLANTI VAR AMA KULLANICI YOK
                QMessageBox.warning(self, "Giriş Başarısız", "Kullanıcı adı veya şifre hatalı!")
        
        except Exception as e:
            error_str = str(e)
            logger.error(f"Giriş hatası: {error_str}")
            
            # Hata mesajını analiz et ve kullanıcıya anlaşılır mesaj ver
            if "2003" in error_str or "Can't connect" in error_str:
                msg = "Sunucuya bağlanılamadı.\nLütfen internet bağlantınızı ve config.py ayarlarını kontrol edin."
            elif "1045" in error_str or "Access denied" in error_str:
                msg = "Veritabanı erişimi reddedildi (Kullanıcı adı/Şifre yanlış)."
            else:
                msg = f"Beklenmedik bir hata oluştu:\n{error_str}"
                
            QMessageBox.critical(self, "Bağlantı Hatası", msg)
            
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Giriş Yap")

    def save_session(self, username, password):
        """Kullanıcı isterse bilgileri yerel dosyaya kaydeder."""
        if self.chk_remember.isChecked():
            data = {"username": username, "password": password, "remember": True}
            try:
                with open(SESSION_FILE, 'w') as f:
                    json.dump(data, f)
            except Exception as e:
                logger.warning(f"Oturum kaydedilemedi: {e}")
        else:
            # İşaretli değilse mevcut kayıt dosyasını sil
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)

    def load_session(self):
        """Kayıtlı oturum varsa alanları doldurur."""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get("remember"):
                        self.user_input.setText(data.get("username", ""))
                        self.pass_input.setText(data.get("password", ""))
                        self.chk_remember.setChecked(True)
                        # İsteğe bağlı: Otomatik giriş yapmak için:
                        # self.attempt_login() 
            except Exception as e:
                logger.warning(f"Oturum dosyası okunamadı: {e}")