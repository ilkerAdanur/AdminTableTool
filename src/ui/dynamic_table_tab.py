# src/ui/dynamic_table_tab.py

import os
import pandas as pd
import logging  # <-- 1. logging'i import edin
import re
import functools

# (Diğer importlar)
from src.core.tasks import run_dynamic_report_task 
from src.threading.workers import Worker
from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
    QHeaderView, QMenu, QAbstractItemView, QMessageBox, QInputDialog,
    QLabel, QLineEdit, QHBoxLayout, QDateEdit, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QDate
from PyQt6.QtGui import QAction

from src.core.tasks import fetch_preview_data_task
from src.threading.workers import Worker

# <-- 2. Modüle özel logger'ı tanımlayın
logger = logging.getLogger(__name__)

class DroppableHeaderView(QHeaderView):
    """
    Sadece başlık alanına sürükle-bırak yapılmasını sağlayan
    özel HeaderView sınıfı.
    """
    columns_dropped = pyqtSignal(list, int) 

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setAcceptDrops(True) 
        self.setSectionsMovable(True) 

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

        if target_index == -1:
            target_index = self.count() - 1 

        dropped_columns = drag_text.split('\n') 

        # --- DEĞİŞİKLİK (print -> logger.info) ---
        logger.info(f"Header'a bırakıldı: {dropped_columns} -> {target_index} indeksine.")

        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()


class DynamicTableWidget(QTableWidget):
    """
    Artık sadece veriyi GÖSTEREN, sürükleme-bırak işlemini
    özel header'ına devreden QTableWidget.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        new_header = DroppableHeaderView(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(new_header)

        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(["[Yeni Sütun Ekle]"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """
        NOT: Bu fonksiyon artık DroppableHeaderView tarafından ele alındığı için
        buraya yapılan drop işlemi (eğer header'a değil de tablo gövdesine yapılırsa)
        hatalı olabilir. Ancak orijinal kodda olduğu gibi bırakıyorum.
        Eğer sadece header'a drop yapılacaksa bu fonksiyon gereksizdir.
        """
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        target_index = self.horizontalHeader().logicalIndexAt(drop_pos.x())
        dropped_columns = drag_text.split('\n') 
        
        # --- DEĞİŞİKLİK (print -> logger.warning) ---
        logger.warning(f"Drop işlemi (muhtemelen yanlışlıkla) tablo gövdesine yapıldı. Header'a yönlendiriliyor. {dropped_columns} -> {target_index}")
        
        # Sinyali header'dan geliyormuş gibi tetikle
        self.horizontalHeader().columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()



class DynamicTableTab(QWidget):
    """
    Yeni 'Veri Tablosu (Dönüştürme)' sekmesi.
    """
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window 
        self.defined_columns = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5) 

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
        self._populate_date_columns() 
        controls_layout.addWidget(self.date_column_combo)

        controls_layout.addWidget(QLabel("Görünüm:"))
        self.agg_type_combo = QComboBox()
        self.agg_type_combo.setToolTip("Raporun ham veriyi mi, yoksa tarih bazlı özeti mi göstereceğini seçin.")
        self.agg_type_combo.clear() 
        self.agg_type_combo.addItems([
            "Ham Veri (Grup Yok)",
            "Günlük Özet (Tarihe Göre Grupla)"
        ])
        controls_layout.addWidget(self.agg_type_combo)

        controls_layout.addStretch(1) 

        self.btn_reset_report = QPushButton("Raporu Sıfırla")
        self.btn_reset_report.setStyleSheet("background-color: #f44336; color: white; padding: 5px;") 
        self.btn_reset_report.setToolTip("Tablodaki tüm verileri temizler ve sütun tanımlarını sıfırlar.")
        controls_layout.addWidget(self.btn_reset_report)

        self.btn_run_report = QPushButton("Raporu Uygula")
        self.btn_run_report.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px;")
        controls_layout.addWidget(self.btn_run_report)

        layout.addLayout(controls_layout) 

        self.table = DynamicTableWidget(self)
        layout.addWidget(self.table)

        # --- Sinyalleri Bağla ---
        self.table.horizontalHeader().columns_dropped.connect(self.handle_columns_dropped)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_header_menu)
        self.table.horizontalHeader().doubleClicked.connect(self.edit_column_formula)
        self.btn_run_report.clicked.connect(self.run_report)
        self.btn_reset_report.clicked.connect(self.reset_report) # <-- Reset butonu sinyali
        
        logger.debug("DynamicTableTab başlatıldı ve sinyaller bağlandı.") # <-- LOG

    def reset_report(self):
        """'Raporu Sıfırla' butonuna tıklandığında çalışır."""
        logger.debug("'Raporu Sıfırla' tıklandı, kullanıcı onayı bekleniyor.") # <-- LOG
        reply = QMessageBox.question(self, "Raporu Sıfırla",
                                    "Tüm sütun tanımlamalarını sıfırlamak ve tabloyu temizlemek istediğinizden emin misiniz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # --- DEĞİŞİKLİK (print -> logger.info) ---
            logger.info("Rapor sıfırlanıyor...")
            self.defined_columns = []
            self.refresh_table_headers()
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
            schema = self.main_window.full_schema_data
            for table, columns in schema.items():
                for col in columns:
                    all_full_columns.add(f"{table}.{col}")

            self.date_column_combo.addItems(sorted(list(all_full_columns)))
            logger.debug(f"Tarih sütunu combobox'ı {len(all_full_columns)} sütun ile dolduruldu.") # <-- LOG
        except Exception as e:
            # --- DEĞİŞİKLİK (print -> logger.error) ---
            logger.error(f"Hata: Tarih sütunları doldurulamadı: {e}", exc_info=True)

        self.date_column_combo.blockSignals(False)
    
    def handle_columns_dropped(self, dropped_column_names, target_index):
        if target_index < 0:
            # --- DEĞİŞİKLİK (print -> logger.warning) ---
            logger.warning(f"Hata: Geçersiz hedef index ({target_index}). Bırakma işlemi iptal edildi.")
            return

        header_item = self.table.horizontalHeaderItem(target_index)
        if not header_item:
            # --- DEĞİŞİKLİK (print -> logger.error) ---
            logger.error(f"Hata: {target_index} indeksinde başlık öğesi bulunamadı (None).")
            return

        is_new_column_target = (header_item.text() == "[Yeni Sütun Ekle]")

        if is_new_column_target:
            logger.debug("Yeni sütun hedefine bırakıldı.") # <-- LOG
            if len(dropped_column_names) == 1:
                source_col = dropped_column_names[0]
                guessed_name = source_col.split('.')[-1]
                formula = f"[{source_col}]"
            else: 
                guessed_name = "Hesaplama"
                formula = " + ".join([f"[{col}]" for col in dropped_column_names])

            new_col_name, ok = QInputDialog.getText(self, "Yeni Sütun Adı",
                                                    "Yeni hesaplanmış sütun için bir ad girin:",
                                                    QLineEdit.EchoMode.Normal,
                                                    guessed_name)
            if not (ok and new_col_name):
                logger.debug("Yeni sütun adı girişi iptal edildi.") # <-- LOG
                return 

            default_agg_str = "Toplam (Sum)" 
            if any(id_str in new_col_name.lower() for id_str in ["kimlik", "id", "tarih", "saat"]):
                default_agg_str = "İlk Değer (First)"
            
            # --- DEĞİŞİKLİK (print -> logger.info) ---
            logger.info(f"Yeni sütun eklendi: '{new_col_name}'. Formül: {formula}. Varsayılan özet: {default_agg_str}")

            new_column_def = {
                'name': new_col_name,
                'type': 'formula',
                'formula': formula,
                'sources': dropped_column_names,
                'agg': default_agg_str  
            }
            self.defined_columns.insert(target_index, new_column_def)

        else:
            logger.debug("Mevcut sütun hedefine bırakıldı.") # <-- LOG
            col_def = self.defined_columns[target_index]
            current_name = col_def['name']
            current_formula = col_def.get('formula', "")

            new_formula_part = " + ".join([f"[{col}]" for col in dropped_column_names])

            reply = QMessageBox.question(self, "Sütunu Güncelle",
                                    f"'{new_formula_part}' verisini mevcut '{current_name}' sütununa eklemek istiyor musunuz?\n\n"
                                    f"Mevcut Formül: {current_formula}\n"
                                    f"Yeni Formül: {current_formula} + {new_formula_part}",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                col_def['formula'] = f"{current_formula} + {new_formula_part}"
                if 'sources' not in col_def:
                    col_def['sources'] = []
                for col in dropped_column_names:
                    if col not in col_def['sources']:
                        col_def['sources'].append(col)
                # --- DEĞİŞİKLİK (print -> logger.info) ---
                logger.info(f"'{current_name}' sütunu güncellendi. Yeni formül: {col_def['formula']}")
            else:
                logger.debug("Sütun güncelleme işlemi iptal edildi.") # <-- LOG
                return 

        self.refresh_table_headers()

    def refresh_table_headers(self):
        logger.debug("Tablo başlıkları 'defined_columns' listesine göre yenileniyor.") # <-- LOG
        self.table.setColumnCount(len(self.defined_columns) + 1) 
        
        header_labels = [col_def['name'] for col_def in self.defined_columns]
        header_labels.append("[Yeni Sütun Ekle]") 
        
        self.table.setHorizontalHeaderLabels(header_labels)
        for i in range(len(self.defined_columns)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive) 

        self.table.horizontalHeader().setSectionResizeMode(len(self.defined_columns), QHeaderView.ResizeMode.ResizeToContents)

    def open_header_menu(self, position):
        """Sütun başlığına sağ tıklandığında menü açar."""
        index = self.table.horizontalHeader().logicalIndexAt(position)
        if index < 0 or index >= len(self.defined_columns): 
            return 
            
        logger.debug(f"{index} numaralı sütun başlığına sağ tıklandı, menü açılıyor.") # <-- LOG
        menu = QMenu(self)
        
        edit_action = QAction("Formülü Düzenle", self)
        edit_action.triggered.connect(lambda: self.edit_column_formula(index))
        menu.addAction(edit_action)
        
        delete_action = QAction("Sütunu Sil", self)
        delete_action.triggered.connect(lambda: self.delete_column(index))
        menu.addAction(delete_action)
        
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))

    def edit_column_formula(self, index): 
        """Bir sütunun formülünü düzenler (Başlığa çift tıklandığında)."""
        if index < 0 or index >= len(self.defined_columns): 
            return

        col_def = self.defined_columns[index]
        logger.debug(f"'{col_def['name']}' ({index}) sütunu düzenleniyor.") # <-- LOG
        col_type = col_def.get('type', 'formula') 

        if col_type != 'formula':
            logger.warning(f"'{col_def['name']}' sütunu düzenlenemez tipte ({col_type}).") # <-- LOG
            QMessageBox.information(self, "Düzenlenemez", "Bu sütun tipi (örn: ham veri) formül düzenlemeyi desteklemiyor.")
            return

        current_name = col_def['name']
        current_formula = col_def.get('formula', f"[{col_def.get('sources', ['HATA'])[0]}]")

        new_name, ok = QInputDialog.getText(self, "Sütun Adını Düzenle",
                                            "Sütun adını girin:",
                                            QLineEdit.EchoMode.Normal,
                                            current_name)
        if not (ok and new_name):
            logger.debug("Sütun adı düzenleme iptal edildi.") # <-- LOG
            return 

        new_formula, ok = QInputDialog.getText(self, "Formülü Düzenle",
                                            f"'{new_name}' için formülü girin:\n(Ham sütun adlarını [ ] içinde kullanın)",
                                            QLineEdit.EchoMode.Normal,
                                            current_formula)
        if not (ok and new_formula):
            logger.debug("Formül düzenleme iptal edildi.") # <-- LOG
            return 

        new_sources = re.findall(r"\[(.*?)\]", new_formula)
        if not new_sources:
            logger.warning(f"Geçersiz formül girildi (kaynak sütun yok): {new_formula}") # <-- LOG
            QMessageBox.warning(self, "Formül Hatası",
                                "Formülde [KaynakSutun] formatında en az bir kaynak sütun bulunamadı.")
            return

        agg_options = [
            "Yok (Özette Gösterme)", "Toplam (Sum)", "Ortalama (Average)", 
            "Fark (Maks-Min)", "Maksimum (Max)", "Minimum (Min)", 
            "İlk Değer (First)", "Son Değer (Last)", "Sayı (Count)"
        ]
        
        current_agg = col_def.get('agg', 'Toplam (Sum)') 
        try:
            current_agg_index = agg_options.index(current_agg)
        except ValueError:
            current_agg_index = 0 
        
        new_agg_str, ok = QInputDialog.getItem(self, "Özet İşlemi Seç",
                                               f"'{new_name}' sütunu 'Günlük Özet' modunda nasıl gösterilsin?",
                                               agg_options, current_agg_index, False)
        if not ok:
            logger.debug("Özet işlemi seçimi iptal edildi.") # <-- LOG
            return 

        logger.info(f"Sütun güncellendi: Ad: {new_name}, Formül: {new_formula}, Özet: {new_agg_str}") # <-- LOG
        self.defined_columns[index]['name'] = new_name
        self.defined_columns[index]['formula'] = new_formula
        self.defined_columns[index]['agg'] = new_agg_str 

        self.refresh_table_headers()
    
    def delete_column(self, index):
        """Bir sütunu taslaktan kaldırır."""
        if index < 0 or index >= len(self.defined_columns):
            return
        
        col_def = self.defined_columns[index]
        reply = QMessageBox.question(self, "Sütunu Sil",
                                     f"'{col_def['name']}' sütununu taslaktan kaldırmak istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"'{col_def['name']}' sütunu siliniyor.") # <-- LOG
            del self.defined_columns[index]
            self.refresh_table_headers()
            # TODO: Tablodaki veriyi de yenile
        else:
            logger.debug("Sütun silme iptal edildi.") # <-- LOG

    def run_report(self):
        """'Raporu Uygula' butonuna tıklandığında çalışır."""
        logger.info("'Raporu Uygula' tıklandı.") # <-- LOG

        if not self.defined_columns:
            logger.warning("Rapor çalıştırılmak istendi ancak tanımlı sütun yok.") # <-- LOG
            QMessageBox.warning(self, "Sütun Yok", "Lütfen rapora en az bir sütun ekleyin.")
            return

        full_date_column = self.date_column_combo.currentData()
        if not full_date_column:
            full_date_column = self.date_column_combo.currentText() 
            if full_date_column == "Tarih Sütunu Seçin...":
                logger.warning("Rapor çalıştırılmak istendi ancak tarih sütunu seçilmemiş.") # <-- LOG
                QMessageBox.warning(self, "Tarih Sütunu Eksik", "Lütfen verileri filtrelemek için bir tarih sütunu seçin.")
                return

        start_date = self.date_Baslangic.date().toString("yyyy-MM-dd")
        end_date = self.date_Bitis.date().toString("yyyy-MM-dd")
        agg_type_str = self.agg_type_combo.currentText()

        logger.info(f"Dinamik rapor worker'ı başlatılıyor. Ayarlar: DateCol={full_date_column}, "
                    f"Range={start_date} -> {end_date}, Agg={agg_type_str}") # <-- LOG
        self.main_window.show_loading_dialog(f"'{self.windowTitle()}' raporu çalıştırılıyor...")

        worker = Worker(
            run_dynamic_report_task,
            self.main_window.db_config,
            self.defined_columns,
            full_date_column,
            start_date,
            end_date,
            agg_type_str
        )

        worker.signals.finished.connect(self._on_report_finished) 
        worker.signals.error.connect(self._on_report_error)
        self.main_window.threadpool.start(worker)

    def _on_report_finished(self, final_df):
        """(Callback) Rapor verisi (final_df) geldiğinde çalışır."""
        self.main_window.close_loading_dialog()

        if final_df is None:
            logger.error("Rapor verisi 'None' olarak döndü.") # <-- LOG
            QMessageBox.warning(self, "Hata", "Rapor verisi oluşturulamadı (None döndü).")
            return

        # --- DEĞİŞİKLİK (print -> logger.info) ---
        logger.info(f"Sekme [{self.windowTitle()}]: Veri alındı ({len(final_df)} satır). Tablo dolduruluyor...")
        self._populate_table(final_df)

    def _on_report_error(self, error_message):
        """(Callback) Rapor çalıştırılırken bir hata oluşursa çalışır. (SADECE BU SEKME İÇİN)"""
        # Hata zaten worker'da loglandı, biz sadece UI'ı güncelliyoruz.
        logger.warning(f"Dinamik Rapor Hatası (kullanıcıya gösteriliyor): {error_message}")
        self.main_window.close_loading_dialog()
        QMessageBox.critical(self, "Rapor Hatası", 
                             f"Rapor çalıştırılırken bir hata oluştu:\n\n{error_message}")

    def _populate_table(self, df):
        """
        Tabloyu gelen DataFrame ile doldurur.
        """
        logger.debug(f"Dinamik tablo {len(df)} satır ile dolduruluyor...") # <-- LOG
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0) 

        has_date_index = (df.index.name is not None)
        df_columns = list(df.columns)
        header_labels = list(df.columns) 
        col_offset = 0

        if has_date_index:
            header_labels.insert(0, df.index.name) 
            col_offset = 1
            self.table.setColumnCount(len(df_columns) + 1 + 1) # Tarih + Veri + [Yeni Ekle]
            self.table.setHorizontalHeaderLabels(header_labels + ["[Yeni Sütun Ekle]"])
        else:
            self.refresh_table_headers()
        
        if df.empty:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)
            logger.info("Rapor sonucu boş geldi (veri yok).") # <-- LOG
            if hasattr(self, 'btn_run_report'): 
                QMessageBox.information(self, "Veri Yok", "Seçilen tarih aralığında veri bulunamadı.")
            return

        self.table.setRowCount(len(df))

        for i in range(len(df)):
            if has_date_index:
                index_val = df.index[i]
                date_str = str(index_val.strftime('%Y-%m-%d')) if hasattr(index_val, 'strftime') else str(index_val)
                item = QTableWidgetItem(date_str)
                item.setData(Qt.ItemDataRole.EditRole, date_str) 
                self.table.setItem(i, 0, item)

            for j in range(len(df.columns)): 
                raw_value = df.iloc[i, j]
                item = QTableWidgetItem()

                is_numeric = isinstance(raw_value, (int, float))
                if is_numeric:
                    item.setData(Qt.ItemDataRole.EditRole, float(raw_value))
                    try:
                        item.setData(Qt.ItemDataRole.DisplayRole, f"{raw_value:.2f}")
                    except (TypeError, ValueError):
                         item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))

                self.table.setItem(i, j + col_offset, item) 

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

        col_offset = 0
        if has_date_index:
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) 
            col_offset = 1
        
        for i in range(len(df.columns)): 
            self.table.horizontalHeader().setSectionResizeMode(i + col_offset, QHeaderView.ResizeMode.Interactive)
        
        last_col_index = self.table.columnCount() - 1
        self.table.horizontalHeader().setSectionResizeMode(last_col_index, QHeaderView.ResizeMode.ResizeToContents)
        logger.debug("Dinamik tablo başarıyla dolduruldu.") # <-- LOG

    def _populate_date_columns(self): # (Bu fonksiyonun kopyası sonda kalmış, yukarıdaki ile aynı)
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
                self.date_column_combo.addItem(full_name, userData=full_name)

        except Exception as e:
            # --- DEĞİŞİKLİK (print -> logger.error) ---
            logger.error(f"Hata: Tarih sütunları doldurulamadı: {e}", exc_info=True)

        self.date_column_combo.blockSignals(False)