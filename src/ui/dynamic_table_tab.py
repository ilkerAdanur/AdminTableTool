# src/ui/dynamic_table_tab.py

import os
import pandas as pd
from src.core.tasks import run_dynamic_report_task 
from src.threading.workers import Worker
from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
    QHeaderView, QMenu, QAbstractItemView, QMessageBox, QInputDialog,
    QLabel, QLineEdit
)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QAction

# Gerekli modüller (senin proje yapına göre)
from src.core.tasks import fetch_preview_data_task
from src.threading.workers import Worker

from PyQt6.QtWidgets import QHeaderView, QAbstractItemView, QTableWidget
from PyQt6.QtCore import pyqtSignal, Qt

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
    QHeaderView, QMenu, QAbstractItemView, QMessageBox, QInputDialog,
    QLabel, QHBoxLayout, QDateEdit, QPushButton, QComboBox # <-- YENİ KONTROLLER EKLENDİ
)
from PyQt6.QtCore import Qt, QMimeData, QDate # <-- QDate EKLENDİ
from PyQt6.QtGui import QAction

from src.core.tasks import fetch_preview_data_task # <-- BU fetch_preview_data_task'ı DEĞİŞTİRECEĞİZ
from src.threading.workers import Worker


class DroppableHeaderView(QHeaderView):
    """
    Sadece başlık alanına sürükle-bırak yapılmasını sağlayan
    özel HeaderView sınıfı.
    """
    # [sütun_adları], hedef_index
    columns_dropped = pyqtSignal(list, int) 

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setAcceptDrops(True) # Sadece bu widget bırakmayı kabul eder
        self.setSectionsMovable(True) # Sütunları taşıyabil

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """Bir öğe başlığın üzerine bırakıldığında."""
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        target_index = self.logicalIndexAt(drop_pos.x())

        # Eğer boş bir alana (son sütunun sağı) bırakıldıysa,
        # onu 'Yeni Sütun Ekle' (son sütun) olarak kabul et
        if target_index == -1:
            target_index = self.count() - 1 

        dropped_columns = drag_text.split('\n') 

        print(f"Header'a bırakıldı: {dropped_columns} -> {target_index} indeksine.")

        # Ana sekmeye (DynamicTableTab) sinyali gönder
        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()


class DynamicTableWidget(QTableWidget):
    """
    Artık sadece veriyi GÖSTEREN, sürükleme-bırak işlemini
    özel header'ına devreden QTableWidget.
    """

    # Sinyal artık Header'dan geliyor, bu sınıftan değil
    # columns_dropped = pyqtSignal(list, int) # <-- BU SATIRI SİLİN

    def __init__(self, parent=None):
        super().__init__(parent)

        new_header = DroppableHeaderView(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(new_header)

        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(["[Yeni Sütun Ekle]"])

        # --- DEĞİŞİKLİK BURADA ---
        # 'Stretch' (Sığdır) yerine 'Interactive' (Etkileşimli) kullan.
        # Bu, sütunların sıkışmasını engeller ve kaydırma çubuğu çıkarır.
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


    def dragEnterEvent(self, event):
        # Sadece metin (sütun adı) içeren sürüklemeleri kabul et
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """
        Sütun başlığına bir öğe bırakıldığında tetiklenir.
        """
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        # Bırakılan yerin hangi sütun başlığına denk geldiğini bul
        drop_pos = event.position().toPoint()
        target_index = self.horizontalHeader().logicalIndexAt(drop_pos.x())

        # Gelen veri birden fazla sütun içerebilir (örn: \n ile ayrılmış)
        dropped_columns = drag_text.split('\n') 
        
        print(f"{dropped_columns} sütun(ları) {target_index} indeksine bırakıldı.")
        
        # Ana widget'a (DynamicTableTab) sinyali gönder
        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()



class DynamicTableTab(QWidget):
    """
    Yeni 'Veri Tablosu (Dönüştürme)' sekmesi.
    İçinde sürükle-bırak özellikli bir DynamicTableWidget barındırır.
    """
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window 
        self.defined_columns = []

        # --- 1. Arayüzü Oluştur ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5) 

        # --- YENİ KONTROL ALANI ---
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("Başlangıç:"))
        self.date_Baslangic = QDateEdit(QDate.currentDate().addMonths(-1))
        self.date_Baslangic.setCalendarPopup(True)
        controls_layout.addWidget(self.date_Baslangic)

        controls_layout.addWidget(QLabel("Bitiş:"))
        self.date_Bitis = QDateEdit(QDate.currentDate())
        self.date_Bitis.setCalendarPopup(True)
        controls_layout.addWidget(self.date_Bitis)

        controls_layout.addWidget(QLabel("Tarih Sütunu:"))
        self.date_column_combo = QComboBox()
        self.date_column_combo.setToolTip("Raporu filtrelemek için kullanılacak ana tarih sütunu")
        self._populate_date_columns() # Yardımcı fonksiyonu çağır
        controls_layout.addWidget(self.date_column_combo)

        controls_layout.addStretch(1) # Butonu sağa it

        self.btn_reset_report = QPushButton("Raporu Sıfırla")
        self.btn_reset_report.setStyleSheet("background-color: #f44336; color: white; padding: 5px;") # Kırmızı
        self.btn_reset_report.setToolTip("Tablodaki tüm verileri temizler ve sütun tanımlarını sıfırlar.")
        controls_layout.addWidget(self.btn_reset_report)

        self.btn_run_report = QPushButton("Raporu Uygula")
        self.btn_run_report.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px;")
        controls_layout.addWidget(self.btn_run_report)

        layout.addLayout(controls_layout) # Kontrol alanını ana layout'a ekle
        # --- KONTROL ALANI SONU ---

        # Sürükle-bırak özellikli özel tablomuz
        self.table = DynamicTableWidget(self)
        layout.addWidget(self.table)

        # (Arayüz hatasını düzelten addStretch artık gerekli değil,
        # tablo zaten kontrollerin altında kalacak)

        # --- Sinyalleri Bağla ---
        self.table.horizontalHeader().columns_dropped.connect(self.handle_columns_dropped)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_header_menu)
        self.table.horizontalHeader().doubleClicked.connect(self.edit_column_formula)

        # Yeni butonun sinyali
        self.btn_run_report.clicked.connect(self.run_report)

    def reset_report(self):
        """'Raporu Sıfırla' butonuna tıklandığında çalışır."""
        reply = QMessageBox.question(self, "Raporu Sıfırla",
                                    "Tüm sütun tanımlamalarını sıfırlamak ve tabloyu temizlemek istediğinizden emin misiniz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            print("Rapor sıfırlanıyor...")
            # 1. Sütun tanımlarını temizle
            self.defined_columns = []
            # 2. Tablo başlıklarını yenile (sadece '[Yeni Sütun Ekle]' kalacak)
            self.refresh_table_headers()
            # 3. Tablodaki verileri temizle
            self.table.setRowCount(0)

    def _populate_date_columns(self):
        """
        Ana penceredeki şemadan TÜM sütunları ('Tablo.Sütun' formatında)
        ComboBox'a ekler.
        """
        self.date_column_combo.blockSignals(True)
        self.date_column_combo.clear()
        self.date_column_combo.addItem("Tarih Sütunu Seçin...", userData=None)

        all_full_columns = set()
        try:
            # Ana penceredeki tam şema verisini al
            schema = self.main_window.full_schema_data
            for table, columns in schema.items():
                for col in columns:
                    # TODO: Sadece tarih/datetime olanları filtreleyebiliriz
                    all_full_columns.add(f"{table}.{col}")

            self.date_column_combo.addItems(sorted(list(all_full_columns)))
        except Exception as e:
            print(f"Hata: Tarih sütunları doldurulamadı: {e}")

        self.date_column_combo.blockSignals(False)
    def handle_columns_dropped(self, dropped_column_names, target_index):
        """
        Sütun(lar) başlığa bırakıldığında çalışır.
        Yeni sütuna bırakılırsa yeni sütun oluşturur.
        Mevcut sütuna bırakılırsa formülü birleştirmeyi teklif eder.
        """

        if target_index < 0:
            print(f"Hata: Geçersiz hedef index ({target_index}). Bırakma işlemi iptal edildi.")
            return

        header_item = self.table.horizontalHeaderItem(target_index)
        if not header_item:
            # Bu durum, -1 index hatasını (AttributeError) çözer
            print(f"Hata: {target_index} indeksinde başlık öğesi bulunamadı (None).")
            return

        is_new_column_target = (header_item.text() == "[Yeni Sütun Ekle]")

        if is_new_column_target:
            # --- 1. YENİ BİR SÜTUN OLUŞTURULUYOR ---

            # Formülü ve adı tahmin et
            if len(dropped_column_names) == 1:
                source_col = dropped_column_names[0]
                guessed_name = source_col.split('.')[-1]
                formula = f"[{source_col}]"
            else: # Birden fazla sütun bırakıldıysa
                guessed_name = "Hesaplama"
                formula = " + ".join([f"[{col}]" for col in dropped_column_names])

            # Yeni sütun için bir ad iste
            new_col_name, ok = QInputDialog.getText(self, "Yeni Sütun Adı",
                                                    "Yeni hesaplanmış sütun için bir ad girin:",
                                                    QLineEdit.EchoMode.Normal,
                                                    guessed_name)
            if not (ok and new_col_name):
                return # İptal edildi

            # Yeni sütun tanımını hafızaya ekle
            new_column_def = {
                'name': new_col_name,
                'type': 'formula',
                'formula': formula,
                'sources': dropped_column_names
            }
            # [Yeni Sütun Ekle]'den ÖNCE ekle
            self.defined_columns.insert(target_index, new_column_def)

        else:
            # --- 2. MEVCUT BİR SÜTUNUN ÜZERİNE BIRAKILIYOR (GÜNCELLEME) ---

            col_def = self.defined_columns[target_index]
            current_name = col_def['name']
            current_formula = col_def.get('formula', "")

            # Bırakılan yeni sütun(lar) için formül parçası oluştur
            new_formula_part = " + ".join([f"[{col}]" for col in dropped_column_names])

            reply = QMessageBox.question(self, "Sütunu Güncelle",
                                    f"'{new_formula_part}' verisini mevcut '{current_name}' sütununa eklemek istiyor musunuz?\n\n"
                                    f"Mevcut Formül: {current_formula}\n"
                                    f"Yeni Formül: {current_formula} + {new_formula_part}",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                # Tanımı güncelle
                col_def['formula'] = f"{current_formula} + {new_formula_part}"
                # Yeni kaynakları da ekle (tekrarları önleyerek)
                if 'sources' not in col_def:
                    col_def['sources'] = []
                for col in dropped_column_names:
                    if col not in col_def['sources']:
                        col_def['sources'].append(col)

                print(f"'{current_name}' sütunu güncellendi. Yeni formül: {col_def['formula']}")
            else:
                return # Güncelleme iptal edildi

        self.refresh_table_headers()

        # TODO: Worker'ı tetikleyip tabloyu ilk 10 satır veriyle doldur (Önizleme)


    def refresh_table_headers(self):
        """
        Hafızadaki 'self.defined_columns' listesine göre
        tablonun başlıklarını (headers) yeniden oluşturur.
        """
        self.table.setColumnCount(len(self.defined_columns) + 1) # Tanımlananlar + [Yeni Sütun Ekle]
        
        header_labels = []
        for i, col_def in enumerate(self.defined_columns):
            header_labels.append(col_def['name'])
            # TODO: Belki başlığın tooltip'ine formülü ekleyebiliriz
            
        header_labels.append("[Yeni Sütun Ekle]") # En sona 'Yeni' sütununu ekle
        
        self.table.setHorizontalHeaderLabels(header_labels)
        for i in range(len(self.defined_columns)):
            # --- DEĞİŞİKLİK BURADA ---
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive) # 'Stretch' değil

        # Son sütunu ([Yeni Sütun Ekle]) içeriğe sığdır
        self.table.horizontalHeader().setSectionResizeMode(len(self.defined_columns), QHeaderView.ResizeMode.ResizeToContents)

    def open_header_menu(self, position):
        """Sütun başlığına sağ tıklandığında menü açar."""
        index = self.table.horizontalHeader().logicalIndexAt(position)
        if index < 0 or index >= len(self.defined_columns): # [Yeni Sütun Ekle]'ye veya boşa tıklandıysa
            return 
            
        menu = QMenu(self)
        
        # TODO: 'Formülü Düzenle' eylemi
        edit_action = QAction("Formülü Düzenle", self)
        edit_action.triggered.connect(lambda: self.edit_column_formula(index))
        menu.addAction(edit_action)
        
        # 'Sütunu Sil' eylemi
        delete_action = QAction("Sütunu Sil", self)
        delete_action.triggered.connect(lambda: self.delete_column(index))
        menu.addAction(delete_action)
        
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))

    def edit_column_formula(self, index): # <-- 'index' parametresi eklendi
        """Bir sütunun formülünü düzenler (Başlığa çift tıklandığında)."""

        if index < 0 or index >= len(self.defined_columns): # [Yeni Sütun Ekle]'ye tıklandıysa
            return

        col_def = self.defined_columns[index]

        col_type = col_def.get('type', 'formula') 

        if col_type != 'formula':
            QMessageBox.information(self, "Düzenlenemez", "Bu sütun tipi (örn: ham veri) formül düzenlemeyi desteklemiyor.")
            return

        current_name = col_def['name']
        current_formula = col_def.get('formula', f"[{col_def.get('sources', ['HATA'])[0]}]")

        new_name, ok = QInputDialog.getText(self, "Sütun Adını Düzenle",
                                            "Sütun adını girin:",
                                            QLineEdit.EchoMode.Normal,
                                            current_name)
        if not (ok and new_name):
            return 

        new_formula, ok = QInputDialog.getText(self, "Formülü Düzenle",
                                            f"'{new_name}' için formülü girin:\n(Ham sütun adlarını [ ] içinde kullanın)",
                                            QLineEdit.EchoMode.Normal,
                                            current_formula)
        if not (ok and new_formula):
            return 

        self.defined_columns[index]['name'] = new_name
        self.defined_columns[index]['formula'] = new_formula

        self.refresh_table_headers()
        # TODO: Tablodaki veriyi de yenile
    
    def delete_column(self, index):
        """Bir sütunu taslaktan kaldırır."""
        if index < 0 or index >= len(self.defined_columns):
            return
        
        col_def = self.defined_columns[index]
        reply = QMessageBox.question(self, "Sütunu Sil",
                                     f"'{col_def['name']}' sütununu taslaktan kaldırmak istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.defined_columns[index]
            self.refresh_table_headers()
            # TODO: Tablodaki veriyi de yenile

    def run_report(self):
        """'Raporu Uygula' butonuna tıklandığında çalışır."""

        if not self.defined_columns:
            QMessageBox.warning(self, "Sütun Yok", "Lütfen rapora en az bir sütun ekleyin.")
            return

        full_date_column = self.date_column_combo.currentData()
        if not full_date_column:
            full_date_column = self.date_column_combo.currentText() # Fallback
            if full_date_column == "Tarih Sütunu Seçin...":
                QMessageBox.warning(self, "Tarih Sütunu Eksik", "Lütfen verileri filtrelemek için bir tarih sütunu seçin.")
                return

        start_date = self.date_Baslangic.date().toString("yyyy-MM-dd")
        end_date = self.date_Bitis.date().toString("yyyy-MM-dd")

        self.main_window.show_loading_dialog(f"'{self.windowTitle()}' raporu çalıştırılıyor...")

        # Yeni görevimizi (run_dynamic_report_task) çağır
        worker = Worker(
            run_dynamic_report_task,
            self.main_window.db_config,
            self.defined_columns,
            full_date_column,
            start_date,
            end_date
        )

        worker.signals.finished.connect(self._on_report_finished) 
        worker.signals.error.connect(self.main_window._on_task_error) # Ana pencerenin hata işleyicisini kullan
        self.main_window.threadpool.start(worker)

    def _on_report_finished(self, final_df):
        """(Callback) Rapor verisi (final_df) geldiğinde çalışır."""
        self.main_window.close_loading_dialog()

        if final_df is None:
            QMessageBox.warning(self, "Hata", "Rapor verisi oluşturulamadı (None döndü).")
            return

        print(f"Sekme [{self.windowTitle()}]: Veri alındı. Tablo dolduruluyor...")
        self._populate_table(final_df)

    def _populate_table(self, df):
        """
        Tabloyu gelen DataFrame ile doldurur.
        '[Yeni Sütun Ekle]' sütununu korur.
        """
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0) 

        # --- DÜZELTME: Sütun sayısını tanımlara göre ayarla ---
        # Sütunları temizlemek yerine, 'defined_columns'a göre yeniden ayarla
        self.refresh_table_headers()
        # ----------------------------------------------------

        if df.empty:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)
            if hasattr(self, 'btn_run_report'): # Sadece 'run_report' sonrası için
                QMessageBox.information(self, "Veri Yok", "Seçilen tarih aralığında veri bulunamadı.")
            return

        # Sütun adları DF ile uyuşuyor mu kontrol et
        if list(df.columns) != [col['name'] for col in self.defined_columns]:
            print("HATA: Doldurulacak veri ile sütun tanımları eşleşmiyor.")
            # Başlıkları DF'e göre ayarla (fallback)
            self.table.setColumnCount(len(df.columns) + 1)
            self.table.setHorizontalHeaderLabels(list(df.columns) + ["[Yeni Sütun Ekle]"])

        self.table.setRowCount(len(df))

        # Veriyi doldur
        for i in range(len(df)):
            for j in range(len(df.columns)): # Sadece DF'in sütun sayısı kadar
                raw_value = df.iloc[i, j]
                item = QTableWidgetItem()

                # Sayısal sıralama için
                is_numeric = isinstance(raw_value, (int, float))
                if is_numeric:
                    item.setData(Qt.ItemDataRole.EditRole, float(raw_value))
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))

                self.table.setItem(i, j, item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

        # Sütun genişliklerini ayarla (refresh_table_headers'da yapılmıştı ama tekrar edelim)
        for i in range(len(self.defined_columns)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(len(self.defined_columns), QHeaderView.ResizeMode.ResizeToContents)

    def _populate_date_columns(self):
        self.date_column_combo.blockSignals(True)
        self.date_column_combo.clear()
        self.date_column_combo.addItem("Tarih Sütunu Seçin...", userData=None)

        all_full_columns = set()
        try:
            schema = self.main_window.full_schema_data
            for table, columns in schema.items():
                for col in columns:
                    full_name = f"{table}.{col}"
                    all_full_columns.add(full_name)

            for full_name in sorted(list(all_full_columns)):
                # Hem görünen metin (Text) hem de userData (Data) aynı olsun
                self.date_column_combo.addItem(full_name, userData=full_name)

        except Exception as e:
            print(f"Hata: Tarih sütunları doldurulamadı: {e}")

        self.date_column_combo.blockSignals(False)

