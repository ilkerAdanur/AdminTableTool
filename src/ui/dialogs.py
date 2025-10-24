# src/ui/dialogs.py
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
    QPushButton, QDialogButtonBox, QLabel, QWidget,
    QFileDialog, 
    # --- YENİ İMPORTLAR (TemplateEditorDialog için) ---
    QGroupBox, QListWidget, QTableWidget, QAbstractItemView,
    QTableWidgetItem, QTextEdit, QSizePolicy, QSpacerItem,QMessageBox 
)
from PyQt6.QtCore import Qt

from src.core.template_manager import save_template, load_template, get_available_templates



class ConnectionDialog(QDialog):
    # ... (Bu sınıfın kodu olduğu gibi kalacak) ...
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
                QMessageBox.warning(self,"Eksik Bilgi", "Lütfen bir Access dosyası seçin.")
                return 
            self.config['path'] = self.path_edit.text()
        else:
            # Diğer DB türleri için temel kontroller (boş olmamalı)
            required_fields = ['host', 'database', 'user'] # Port ve şifre boş olabilir
            missing = [f for f in required_fields if not self.config.get(f)]
            if missing:
                 QMessageBox.warning(self,"Eksik Bilgi", f"Lütfen şu alanları doldurun: {', '.join(missing)}")
                 return 

            self.config['host'] = self.host_edit.text()
            self.config['port'] = self.port_edit.text()
            self.config['database'] = self.db_name_edit.text()
            self.config['user'] = self.user_edit.text()
            self.config['password'] = self.pass_edit.text()
        
        super().accept() 

    def get_config(self):
        """Ana pencerenin bağlantı ayarlarını alması için kullanılır."""
        return self.config


class TemplateEditorDialog(QDialog):
    """
    Kullanıcının veritabanı sütunlarından rapor taslakları
    oluşturmasını sağlayan diyalog penceresi.
    """
    def __init__(self, source_columns=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rapor Taslağı Düzenleyici")
        self.setMinimumSize(800, 600) 

        # --- Ana Dikey Layout ---
        main_layout = QVBoxLayout(self)

        # --- 1. Bölüm: Taslak Adı, Kaydet/Yükle ---
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Taslak Adı:"))
        self.template_name_edit = QLineEdit()
        self.template_name_edit.setPlaceholderText("Kaydedilecek taslak adı...")
        top_layout.addWidget(self.template_name_edit)
        
        self.load_button = QPushButton("Yükle...")
        self.save_button = QPushButton("Kaydet")
        self.load_button.clicked.connect(self._load_template) 
        self.save_button.clicked.connect(self._save_template) 
        
        top_layout.addWidget(self.load_button)
        top_layout.addWidget(self.save_button)
        main_layout.addLayout(top_layout)

        # --- 2. Bölüm: Sütun Seçimi (Sol/Sağ) ---
        columns_layout = QHBoxLayout()

        # Sol Taraf: Kaynak Sütunlar
        source_group = QGroupBox("Kaynak Sütunlar (Ham Veri)")
        source_v_layout = QVBoxLayout(source_group)
        self.source_columns_list = QListWidget()
        self.source_columns_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Çoklu seçim
        if source_columns:
            self.source_columns_list.addItems(source_columns)
            
        source_v_layout.addWidget(self.source_columns_list)
        columns_layout.addWidget(source_group)

        # Orta Bölüm: Taşıma Butonları
        move_buttons_layout = QVBoxLayout()
        move_buttons_layout.addStretch() 
        self.add_column_button = QPushButton(">") 
        self.remove_column_button = QPushButton("<") 
        self.move_up_button = QPushButton("↑ Yukarı") # Metinleri güncelledim
        self.move_down_button = QPushButton("↓ Aşağı") # Metinleri güncelledim
        # --- BUTON BAĞLANTILARI ---
        self.add_column_button.clicked.connect(self._add_column_to_report)
        self.remove_column_button.clicked.connect(self._remove_column_from_report)
        self.move_up_button.clicked.connect(self._move_column_up)
        self.move_down_button.clicked.connect(self._move_column_down)
        # --- Tooltip'ler ---
        self.add_column_button.setToolTip("Seçili kaynak sütun(lar)ı rapora ekle")
        self.remove_column_button.setToolTip("Seçili rapor sütununu çıkar")
        self.move_up_button.setToolTip("Seçili rapor sütununu yukarı taşı")
        self.move_down_button.setToolTip("Seçili rapor sütununu aşağı taşı")

        move_buttons_layout.addWidget(self.add_column_button)
        move_buttons_layout.addWidget(self.remove_column_button)
        move_buttons_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)) 
        move_buttons_layout.addWidget(self.move_up_button)
        move_buttons_layout.addWidget(self.move_down_button)
        move_buttons_layout.addStretch() 
        columns_layout.addLayout(move_buttons_layout)

        # Sağ Taraf: Rapor Sütunları
        report_group = QGroupBox("Rapor Sütunları (Sıralı)")
        report_v_layout = QVBoxLayout(report_group)
        self.report_columns_table = QTableWidget()
        self.report_columns_table.setColumnCount(3) # YENİ: Gizli Kaynak/Formül sütunu
        self.report_columns_table.setHorizontalHeaderLabels(["Görünecek Ad", "Tür", "Kaynak/Formül"])
        self.report_columns_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows) 
        self.report_columns_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) 
        # Son sütunu (Kaynak/Formül) gizle
        self.report_columns_table.setColumnHidden(2, True) 
        # İlk iki sütun genişlesin
        self.report_columns_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.report_columns_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents) # Tür sütunu içeriğe göre
        
        report_v_layout.addWidget(self.report_columns_table)
        
        self.add_calc_button = QPushButton("Yeni Hesaplama Ekle/Düzenle...")
        self.add_calc_button.clicked.connect(self._show_formula_editor) # Bağlantı eklendi
        report_v_layout.addWidget(self.add_calc_button)
        
        columns_layout.addWidget(report_group)
        main_layout.addLayout(columns_layout)

        # --- 3. Bölüm: Formül Düzenleyici ---
        self.formula_group = QGroupBox("Formül Düzenleyici")
        formula_layout = QFormLayout(self.formula_group)
        self.new_column_name_edit = QLineEdit()
        self.formula_edit = QTextEdit() 
        self.formula_edit.setPlaceholderText('Örn: "[Sutun_A]" * 0.6 + "[Sutun_B]" * 0.7\n(Kaynak sütun adlarını köşeli parantez [ ] içine yazın)')
        
        # Formül ekleme/güncelleme butonu
        self.add_update_formula_button = QPushButton("Hesaplamayı Ekle/Güncelle")
        self.add_update_formula_button.clicked.connect(self._add_or_update_calculation) # Bağlantı eklendi
        
        formula_layout.addRow("Yeni Sütun Adı:", self.new_column_name_edit)
        formula_layout.addRow("Formül:", self.formula_edit)
        formula_layout.addRow(self.add_update_formula_button) # Test butonu yerine ekleme butonu
        
        main_layout.addWidget(self.formula_group)
        self.formula_group.setVisible(False) # Başlangıçta gizli

        # --- 4. Bölüm: Ana Butonlar ---
        self.button_box = QDialogButtonBox()
        self.preview_button = self.button_box.addButton("Önizle", QDialogButtonBox.ButtonRole.ActionRole)
        self.button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        self.button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        # TODO: self.preview_button.clicked.connect(self._preview_template) # Önizleme sonra
        self.button_box.accepted.connect(self.accept) 
        self.button_box.rejected.connect(self.reject) 

        main_layout.addWidget(self.button_box)

        self._editing_formula_row = -1 


    # --- Buton Fonksiyonları ---

    def _add_column_to_report(self):
        """Seçili kaynak sütunları rapor tablosuna 'Ham' olarak ekler."""
        selected_items = self.source_columns_list.selectedItems()
        if not selected_items:
            return

        current_report_columns = [self.report_columns_table.item(row, 0).text() 
                                   for row in range(self.report_columns_table.rowCount())]

        for item in selected_items:
            source_col_name = item.text()
            if source_col_name not in current_report_columns:
                row = self.report_columns_table.rowCount()
                self.report_columns_table.insertRow(row)
                self.report_columns_table.setItem(row, 0, QTableWidgetItem(source_col_name)) # Görünecek Ad
                self.report_columns_table.setItem(row, 1, QTableWidgetItem("Ham"))           # Tür
                self.report_columns_table.setItem(row, 2, QTableWidgetItem(source_col_name)) # Kaynak (Gizli)
        
        # Seçimi temizle (isteğe bağlı)
        # self.source_columns_list.clearSelection()

    def _remove_column_from_report(self):
        """Seçili rapor sütununu tablodan kaldırır."""
        selected_rows = self.report_columns_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        for index in sorted([r.row() for r in selected_rows], reverse=True):
            self.report_columns_table.removeRow(index)
            
        self.formula_group.setVisible(False)
        self._editing_formula_row = -1

    def _move_column_up(self):
        """Seçili rapor sütununu bir yukarı taşır."""
        current_row = self.report_columns_table.currentRow()
        if current_row > 0: 
            self.report_columns_table.insertRow(current_row - 1)
            for col in range(self.report_columns_table.columnCount()):
                self.report_columns_table.setItem(current_row - 1, col, 
                    self.report_columns_table.takeItem(current_row + 1, col)) 
            self.report_columns_table.removeRow(current_row + 1)
            self.report_columns_table.selectRow(current_row - 1)

    def _move_column_down(self):
        """Seçili rapor sütununu bir aşağı taşır."""
        current_row = self.report_columns_table.currentRow()
        if current_row < self.report_columns_table.rowCount() - 1 and current_row != -1: 
            self.report_columns_table.insertRow(current_row + 2)
            for col in range(self.report_columns_table.columnCount()):
                 self.report_columns_table.setItem(current_row + 2, col,
                     self.report_columns_table.takeItem(current_row, col))
            self.report_columns_table.removeRow(current_row)
            self.report_columns_table.selectRow(current_row + 1)
            
    def _show_formula_editor(self):
        """'Yeni Hesaplama Ekle/Düzenle' butonuna basıldığında formül grubunu gösterir."""
        self.formula_group.setVisible(True)
        
        # Eğer rapor tablosunda seçili bir 'Hesaplanmış' sütun varsa, onun bilgilerini yükle
        current_row = self.report_columns_table.currentRow()
        if current_row != -1:
            item_type = self.report_columns_table.item(current_row, 1)
            if item_type and item_type.text() == "Hesaplanmış":
                self._editing_formula_row = current_row # Hangi satırı düzenlediğimizi hatırla
                self.new_column_name_edit.setText(self.report_columns_table.item(current_row, 0).text())
                self.formula_edit.setText(self.report_columns_table.item(current_row, 2).text())
                self.formula_group.setTitle("Formül Düzenleyici (Mevcut Hesaplamayı Güncelle)")
                return # Yeni ekleme moduna geçme

        # Yeni ekleme modu
        self._editing_formula_row = -1 # Yeni ekliyoruz, mevcut satır yok
        self.new_column_name_edit.clear()
        self.formula_edit.clear()
        self.formula_group.setTitle("Formül Düzenleyici (Yeni Hesaplama Ekle)")


    def _add_or_update_calculation(self):
        """Formül düzenleyicideki bilgileri rapor tablosuna ekler veya günceller."""
        new_name = self.new_column_name_edit.text().strip()
        formula = self.formula_edit.toPlainText().strip() 

        if not new_name or not formula:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen Yeni Sütun Adı ve Formül alanlarını doldurun.")
            return

        # TODO: Formülün geçerliliğini burada daha detaylı kontrol edebiliriz.

        if self._editing_formula_row != -1:
            self.report_columns_table.item(self._editing_formula_row, 0).setText(new_name)
            self.report_columns_table.item(self._editing_formula_row, 2).setText(formula)
        else:
            row = self.report_columns_table.rowCount()
            self.report_columns_table.insertRow(row)
            self.report_columns_table.setItem(row, 0, QTableWidgetItem(new_name))      
            self.report_columns_table.setItem(row, 1, QTableWidgetItem("Hesaplanmış")) 
            self.report_columns_table.setItem(row, 2, QTableWidgetItem(formula))       

        self.formula_group.setVisible(False)
        self.new_column_name_edit.clear()
        self.formula_edit.clear()
        self._editing_formula_row = -1



    def _save_template(self):
        """'Kaydet' butonuna basıldığında çalışır."""
        template_name = self.template_name_edit.text().strip()
        if not template_name:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen kaydetmek için bir taslak adı girin.")
            return

        template_data = self._collect_template_data() 
        if not template_data:
             QMessageBox.warning(self, "Hata", "Taslak verisi toplanamadı.")
             return

        if save_template(template_name, template_data, parent_widget=self):
            QMessageBox.information(self, "Başarılı", f"'{template_name}' taslağı başarıyla kaydedildi.")

    def _load_template(self):
        """'Yükle...' butonuna basıldığında çalışır."""
        template_data = load_template(template_name=None, parent_widget=self)
        
        if template_data:
            self._populate_ui_from_template(template_data) 
            loaded_name = template_data.get("_template_name", "")
            self.template_name_edit.setText(loaded_name)
            QMessageBox.information(self, "Başarılı", f"'{loaded_name}' taslağı yüklendi.")



    def _collect_template_data(self):
        """Arayüzdeki (Rapor Sütunları tablosu) veriyi bir sözlük olarak toplar."""
        data = {
            "columns": [], 
            "formulas": {} 
        }
        for row in range(self.report_columns_table.rowCount()):
            display_name_item = self.report_columns_table.item(row, 0)
            type_item = self.report_columns_table.item(row, 1)
            source_formula_item = self.report_columns_table.item(row, 2)

            if not display_name_item or not type_item or not source_formula_item:
                 print(f"UYARI: Satır {row} verisi eksik, atlanıyor.")
                 continue 

            display_name = display_name_item.text()
            col_type = type_item.text()
            source_or_formula = source_formula_item.text()
            
            data["columns"].append({
                "display_name": display_name, 
                "type": col_type, 
                "source_or_formula": source_or_formula
            })

            if col_type == "Hesaplanmış":
                data["formulas"][display_name] = source_or_formula
                
        data["template_name"] = self.template_name_edit.text().strip()
        
        return data

    def _populate_ui_from_template(self, template_data):
        """Verilen taslak verisi (sözlük) ile arayüzü doldurur."""
        
        self.template_name_edit.setText(template_data.get("template_name", template_data.get("_template_name", "")))
        
        self.report_columns_table.setRowCount(0) 
        
        columns = template_data.get("columns", [])
        if not columns:
             print("UYARI: Yüklenen taslakta 'columns' listesi bulunamadı veya boş.")
             return

        for col_data in columns:
            row = self.report_columns_table.rowCount()
            self.report_columns_table.insertRow(row)
            
            display_name = col_data.get("display_name", "İsimsiz")
            col_type = col_data.get("type", "Bilinmiyor")
            source_or_formula = col_data.get("source_or_formula", "")
            
            self.report_columns_table.setItem(row, 0, QTableWidgetItem(display_name))
            self.report_columns_table.setItem(row, 1, QTableWidgetItem(col_type))
            self.report_columns_table.setItem(row, 2, QTableWidgetItem(source_or_formula))
        
        self.formula_group.setVisible(False)
        self._editing_formula_row = -1


    # --- OK Butonu ---
    def accept(self):
        # Kullanıcı 'OK'e bastığında taslak verilerini topla ve sakla
        print("Taslak Düzenleyici - OK tıklandı")
        self.template_data = self._collect_template_data() 
        if not self.template_data or not self.template_data.get("columns"):
             reply = QMessageBox.question(self, "Boş Taslak", 
                                        "Hiç rapor sütunu tanımlanmadı. Bu şekilde devam etmek istediğinize emin misiniz?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                        QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.No:
                  return 
                  
        super().accept()

    # --- Ana Pencerenin Kullanması İçin ---
    def get_template_data(self):
        """'accept' içinde toplanan veriyi döndürür."""
        return getattr(self, "template_data", None)
