# src/ui/dialogs.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
    QPushButton, QDialogButtonBox, QLabel, QWidget,
    QFileDialog, QHBoxLayout  
)
from PyQt6.QtCore import Qt


class ConnectionDialog(QDialog):
    """
    Kullanıcıdan farklı veritabanı türleri için bağlantı
    bilgilerini alan dinamik bir diyalog penceresi.
    """
    def __init__(self, db_type, parent=None):
        super().__init__(parent)
        self.db_type = db_type
        self.config = {'type': db_type} # Dönecek olan ayar sözlüğü

        self.setWindowTitle("Veritabanı Bağlantı Ayarları")
        
        # Ana layout
        main_layout = QVBoxLayout(self)
        
        # Form layout (Label-Input)
        self.form_layout = QFormLayout()
        
        # --- Dinamik olarak eklenecek widget'lar ---
        self.host_edit = QLineEdit("localhost")
        self.port_edit = QLineEdit() # Varsayılan portu doldurabiliriz
        self.db_name_edit = QLineEdit("database_name")
        self.user_edit = QLineEdit("username")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        
        # --- Access'e özel dosya seçme widget'ı ---
        self.access_widget = QWidget()
        access_layout = QHBoxLayout(self.access_widget)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Lütfen bir .mdb veya .accdb dosyası seçin...")
        self.path_edit.setReadOnly(True)
        browse_button = QPushButton("Gözat...")
        browse_button.clicked.connect(self.browse_access_file)
        access_layout.addWidget(self.path_edit)
        access_layout.addWidget(browse_button)
        access_layout.setContentsMargins(0,0,0,0)

        # --- Arayüzü seçilen türe göre doldur ---
        if self.db_type == "access":
            self.form_layout.addRow("Dosya Yolu:", self.access_widget)
            self.setMinimumWidth(500)
        else:
            # SQL Server, PostgreSQL vb. için ortak ayarlar
            if self.db_type == "sql":
                self.setWindowTitle("Microsoft SQL Server Bağlantısı")
                self.port_edit.setText("1433")
            elif self.db_type == "postgres":
                self.setWindowTitle("PostgreSQL Bağlantısı")
                self.port_edit.setText("5432")
            
            self.form_layout.addRow("Sunucu (Host):", self.host_edit)
            self.form_layout.addRow("Port:", self.port_edit)
            self.form_layout.addRow("Veritabanı Adı:", self.db_name_edit)
            self.form_layout.addRow("Kullanıcı Adı:", self.user_edit)
            self.form_layout.addRow("Şifre:", self.pass_edit)
            self.setMinimumWidth(400)

        main_layout.addLayout(self.form_layout)
        
        # OK ve İptal Butonları
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)

    def browse_access_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Access Veritabanı Seç", "", 
            "Access Dosyaları (*.mdb *.accdb);;Tüm Dosyalar (*.*)"
        )
        if file_path:
            self.path_edit.setText(file_path)

    def accept(self):
        """Kullanıcı 'OK'e bastığında ayarları 'self.config' sözlüğüne kaydet."""
        if self.db_type == "access":
            if not self.path_edit.text():
                # Hata yönetimi eklenebilir
                return
            self.config['path'] = self.path_edit.text()
        else:
            self.config['host'] = self.host_edit.text()
            self.config['port'] = self.port_edit.text()
            self.config['database'] = self.db_name_edit.text()
            self.config['user'] = self.user_edit.text()
            self.config['password'] = self.pass_edit.text()
        
        super().accept() # Diyaloğu kapat

    def get_config(self):
        """Ana pencerenin bağlantı ayarlarını alması için kullanılır."""
        return self.config