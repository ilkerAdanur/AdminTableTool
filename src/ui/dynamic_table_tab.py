# src/ui/dynamic_table_tab.py

import os
import pandas as pd
import logging 
import re
import functools
import json
from datetime import datetime # get_yeni_kayit_yolu için gerekli

from src.ui.report_header_editor import HeaderEditorView

from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
    QHeaderView, QMenu, QMessageBox, QInputDialog,
    QLabel, QLineEdit, QHBoxLayout, QDateEdit, QPushButton, QComboBox,QFileDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QUrl

from src.core.tasks import run_dynamic_report_task 
from src.core.file_exporter import task_run_excel, get_yeni_kayit_yolu 
from src.threading.workers import Worker
from PyQt6.QtGui import QColor, QFont, QPixmap,QDropEvent, QDragEnterEvent, QDesktopServices

# <-- 2. Modüle özel logger'ı tanımlayın
logger = logging.getLogger(__name__)

class DroppableHeaderView(QHeaderView):
    """
    Sadece başlık alanına sürükle-bırak yapılmasını sağlayan özel HeaderView.
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
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        target_index = self.logicalIndexAt(drop_pos.x())

        if target_index == -1:
            target_index = self.count() - 1 

        dropped_columns = drag_text.split('\n') 
        logger.info(f"Header'a bırakıldı: {dropped_columns} -> {target_index} indeksine.")
        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()

class DynamicTableWidget(QTableWidget):
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
        # Header'a yönlendir
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return
        drop_pos = event.position().toPoint()
        target_index = self.horizontalHeader().logicalIndexAt(drop_pos.x())
        dropped_columns = drag_text.split('\n') 
        logger.warning(f"Drop tablo gövdesine yapıldı, header'a yönlendiriliyor. {dropped_columns}")
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
            self.current_df = pd.DataFrame() # <-- YENİ: Mevcut veriyi saklamak için

            self.current_file_path = None  # Kayıtlı dosyanın yolu
            self.is_unsaved = False        # Değişiklik var mı?

            self.header_image_path = None
            self.last_exported_excel_path = None

            layout = QVBoxLayout(self)
            layout.setContentsMargins(5, 5, 5, 5) 
            
            # --- ÜST KONTROL PANELİ ---
            controls_layout = QHBoxLayout()

            controls_layout.addWidget(QLabel("Başlangıç:"))
            self.date_Baslangic = QDateEdit(QDate.currentDate().addMonths(-1))
            self.date_Baslangic.setCalendarPopup(True)
            controls_layout.addWidget(self.date_Baslangic)

            controls_layout.addWidget(QLabel("Bitiş:"))
            self.date_Bitis = QDateEdit(QDate.currentDate())
            self.date_Bitis.setCalendarPopup(True)
            controls_layout.addWidget(self.date_Bitis)

            self.header_editor = HeaderEditorView()
            layout.addWidget(self.header_editor)

            controls_layout.addWidget(QLabel("Tarih Sütunu:"))
            self.date_column_combo = QComboBox()
            self._populate_date_columns() 
            controls_layout.addWidget(self.date_column_combo)

            controls_layout.addWidget(QLabel("Görünüm:"))
            self.agg_type_combo = QComboBox()
            self.agg_type_combo.addItems([
                "Ham Veri (Grup Yok)",
                "Günlük Özet (Tarihe Göre Grupla)"
            ])
            controls_layout.addWidget(self.agg_type_combo)

            controls_layout.addStretch(1) 

            # BUTONLAR
            self.btn_reset_report = QPushButton("Raporu Sıfırla")
            self.btn_reset_report.setStyleSheet("background-color: #f44336; color: white; padding: 5px;") 
            controls_layout.addWidget(self.btn_reset_report)

            self.btn_run_report = QPushButton("Raporu Uygula")
            self.btn_run_report.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px;")
            controls_layout.addWidget(self.btn_run_report)
            
            # --- YENİ: EXCEL'E AKTAR BUTONU ---
            self.btn_export_excel = QPushButton("Excel'e Aktar")
            self.btn_export_excel.setStyleSheet("background-color: #2196F3; color: white; padding: 5px;")
            self.btn_export_excel.setEnabled(False) # Veri gelene kadar pasif
            controls_layout.addWidget(self.btn_export_excel)

            self.btn_open_excel = QPushButton("Exceli Aç")
            self.btn_open_excel.setStyleSheet("background-color: #8BC34A; color: white; padding: 5px; font-weight: bold;")
            self.btn_open_excel.setEnabled(False) # Başlangıçta pasif (henüz dosya yok)
            

            controls_layout.addWidget(self.btn_open_excel)


            layout.addLayout(controls_layout) 
            
            # --- TABLO ---
            self.table = DynamicTableWidget(self)
            layout.addWidget(self.table)

            # --- SİNYALLER ---
            self.table.horizontalHeader().columns_dropped.connect(self.handle_columns_dropped)
            self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.horizontalHeader().customContextMenuRequested.connect(self.open_header_menu)
            self.table.horizontalHeader().doubleClicked.connect(self.edit_column_formula)
            
            self.btn_run_report.clicked.connect(self.run_report)
            self.btn_reset_report.clicked.connect(self.reset_report)
            self.btn_export_excel.clicked.connect(self.export_to_excel) 
            self.btn_open_excel.clicked.connect(self.open_generated_excel)

            self.date_Baslangic.dateChanged.connect(self.mark_as_unsaved)
            self.date_Bitis.dateChanged.connect(self.mark_as_unsaved)
            self.date_column_combo.currentIndexChanged.connect(self.mark_as_unsaved)
            self.agg_type_combo.currentIndexChanged.connect(self.mark_as_unsaved)

            

            logger.debug("DynamicTableTab başlatıldı (Kayıt özelliği aktif).")

    def mark_as_unsaved(self):
        """Bir değişiklik yapıldığında çağrılır. Sekme adına '*' ekler."""
        if not self.is_unsaved:
            self.is_unsaved = True
            current_index = self.main_window.mainTabWidget.indexOf(self)
            if current_index != -1:
                current_title = self.main_window.mainTabWidget.tabText(current_index)
                if not current_title.endswith("*"):
                    self.main_window.mainTabWidget.setTabText(current_index, current_title + "*")

    def mark_as_saved(self):
        """Kaydetme işleminden sonra çağrılır. '*' işaretini kaldırır."""
        self.is_unsaved = False
        current_index = self.main_window.mainTabWidget.indexOf(self)
        if current_index != -1:
            # Dosya adını sekme adı yap
            file_name = os.path.basename(self.current_file_path)
            # Uzantıyı kaldırarak gösterelim (isteğe bağlı)
            display_name = os.path.splitext(file_name)[0]
            self.main_window.mainTabWidget.setTabText(current_index, display_name)

    def save_file(self):
        """Ctrl+S veya Kaydet. Eğer dosya yolu yoksa 'Farklı Kaydet'e yönlendirir."""
        if not self.current_file_path:
            self.save_file_as()
        else:
            self._write_to_file(self.current_file_path)

    def save_file_as(self):
        """Farklı Kaydet işlemi."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Rapor Ayarlarını Kaydet",
            "", # Varsayılan klasör
            "AdminTableTool Dosyası (*.att);;JSON Dosyası (*.json)" # Özel uzantımız .att olsun
        )
        
        if file_path:
            self.current_file_path = file_path
            self._write_to_file(file_path)

    def _write_to_file(self, file_path):
        """Mevcut ayarları (JSON olarak) dosyaya yazar."""
        try:
            save_data = {
                "file_type": "dynamic_table_config",
                "version": "1.1",
                "start_date": self.date_Baslangic.date().toString("yyyy-MM-dd"),
                "end_date": self.date_Bitis.date().toString("yyyy-MM-dd"),
                "date_column": self.date_column_combo.currentText(),
                "agg_type": self.agg_type_combo.currentText(),
                "defined_columns": self.defined_columns,
                "header_image": self.header_image_path,
                "last_excel_path": self.last_exported_excel_path # <-- EKLENDİ
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=4)
            
            self.mark_as_saved()
            logger.info(f"Dosya kaydedildi: {file_path}")
            self.main_window.statusbar.showMessage(f"Kaydedildi: {file_path}", 3000)
            
        except Exception as e:
            logger.error(f"Kaydetme hatası: {e}")
            QMessageBox.critical(self, "Hata", f"Dosya kaydedilemedi:\n{e}")

    def load_from_file(self, file_path):
        """Kaydedilmiş .att veya .json dosyasını yükler ve arayüzü kurar."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Versiyon kontrolü (İleride yapı değişirse diye)
            if data.get("file_type") != "dynamic_table_config":
                raise ValueError("Bu dosya geçerli bir AdminTableTool yapılandırma dosyası değil.")

            # 1. Tarihleri Yükle
            self.date_Baslangic.setDate(QDate.fromString(data["start_date"], "yyyy-MM-dd"))
            self.date_Bitis.setDate(QDate.fromString(data["end_date"], "yyyy-MM-dd"))
            
            # 2. Comboboxları Ayarla
            idx_date = self.date_column_combo.findText(data["date_column"])
            if idx_date >= 0: self.date_column_combo.setCurrentIndex(idx_date)
            
            idx_agg = self.agg_type_combo.findText(data["agg_type"])
            if idx_agg >= 0: self.agg_type_combo.setCurrentIndex(idx_agg)

            # 3. Sütunları Geri Yükle
            self.defined_columns = data["defined_columns"]
            self.refresh_table_headers()
            
            img_path = data.get("header_image")
            if img_path and os.path.exists(img_path):
                self.header_image_path = img_path
                self.image_label.set_image(img_path)
            else:
                self.header_image_path = None
                self.image_label.clear_image()

            last_excel = data.get("last_excel_path")
            if last_excel and os.path.exists(last_excel):
                self.last_exported_excel_path = last_excel
                self.btn_open_excel.setEnabled(True)
                # Butona ipucu ekle ki kullanıcı hangi dosya olduğunu görsün
                self.btn_open_excel.setToolTip(f"Bağlı Excel: {os.path.basename(last_excel)}")
            else:
                self.last_exported_excel_path = None
                self.btn_open_excel.setEnabled(False)

            # 4. Dosya yolunu sakla ve başlığı güncelle
            self.current_file_path = file_path
            self.mark_as_saved()
            
            logger.info(f"Dosya başarıyla yüklendi: {file_path}")
            # İsteğe bağlı: Dosya açılır açılmaz raporu çalıştır
            # self.run_report() 

        except Exception as e:
            logger.error(f"Dosya yükleme hatası: {e}")
            QMessageBox.critical(self, "Yükleme Hatası", f"Dosya okunamadı:\n{e}")

    def reset_report(self):
        reply = QMessageBox.question(self, "Raporu Sıfırla",
                                    "Tabloyu temizlemek istiyor musunuz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Rapor sıfırlanıyor...")
            self.defined_columns = []
            self.refresh_table_headers()
            self.table.setRowCount(0)
            self.current_df = pd.DataFrame()
            self.btn_export_excel.setEnabled(False)
            
            # EKLENDİ: Sıfırlama da bir değişikliktir
            self.mark_as_unsaved()

    def _populate_date_columns(self):
        self.date_column_combo.blockSignals(True)
        self.date_column_combo.clear()
        self.date_column_combo.addItem("Tarih Sütunu Seçin...", userData=None)
        try:
            schema = self.main_window.full_schema_data
            all_full_columns = set()
            for table, columns in schema.items():
                for col in columns:
                    all_full_columns.add(f"{table}.{col}")
            self.date_column_combo.addItems(sorted(list(all_full_columns)))
        except Exception as e:
            logger.error(f"Tarih sütunları doldurulamadı: {e}")
        self.date_column_combo.blockSignals(False)

    def handle_columns_dropped(self, dropped_column_names, target_index):
        if target_index < 0: return

        header_item = self.table.horizontalHeaderItem(target_index)
        if not header_item: return

        is_new_column_target = (header_item.text() == "[Yeni Sütun Ekle]")

        if is_new_column_target:
            if len(dropped_column_names) == 1:
                source_col = dropped_column_names[0]
                guessed_name = source_col.split('.')[-1]
                formula = f"[{source_col}]"
            else: 
                guessed_name = "Hesaplama"
                formula = " + ".join([f"[{col}]" for col in dropped_column_names])

            new_col_name, ok = QInputDialog.getText(self, "Yeni Sütun Adı", "Sütun Adı:", QLineEdit.EchoMode.Normal, guessed_name)
            if not (ok and new_col_name): return 

            default_agg_str = "Toplam (Sum)" 
            if any(id_str in new_col_name.lower() for id_str in ["kimlik", "id", "tarih", "saat"]):
                default_agg_str = "İlk Değer (First)"
            
            new_column_def = {
                'name': new_col_name, 'type': 'formula', 'formula': formula,
                'sources': dropped_column_names, 'agg': default_agg_str  
            }
            self.defined_columns.insert(target_index, new_column_def)
            self.mark_as_unsaved()

        else:
            # Mevcut sütuna ekleme mantığı (basitleştirildi)
            col_def = self.defined_columns[target_index]
            reply = QMessageBox.question(self, "Sütunu Güncelle", f"'{dropped_column_names}' verisini eklemek istiyor musunuz?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                col_def['formula'] += " + " + " + ".join([f"[{col}]" for col in dropped_column_names])
                self.mark_as_unsaved()
                for col in dropped_column_names:
                    if col not in col_def['sources']: col_def['sources'].append(col)

        self.refresh_table_headers()

    def refresh_table_headers(self):
        self.table.setColumnCount(len(self.defined_columns) + 1) 
        header_labels = [col_def['name'] for col_def in self.defined_columns]
        header_labels.append("[Yeni Sütun Ekle]") 
        self.table.setHorizontalHeaderLabels(header_labels)
        
        for i in range(len(self.defined_columns)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive) 
        self.table.horizontalHeader().setSectionResizeMode(len(self.defined_columns), QHeaderView.ResizeMode.ResizeToContents)

    def open_header_menu(self, position):
        index = self.table.horizontalHeader().logicalIndexAt(position)
        if index < 0 or index >= len(self.defined_columns): return 
        menu = QMenu(self)
        menu.addAction("Formülü Düzenle", lambda: self.edit_column_formula(index))
        menu.addAction("Sütunu Sil", lambda: self.delete_column(index))
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))

    def edit_column_formula(self, index): 
        if index < 0 or index >= len(self.defined_columns): return
        col_def = self.defined_columns[index]
        
        new_name, ok = QInputDialog.getText(self, "Düzenle", "Sütun Adı:", QLineEdit.EchoMode.Normal, col_def['name'])
        if not ok: return
        
        new_formula, ok = QInputDialog.getText(self, "Düzenle", "Formül:", QLineEdit.EchoMode.Normal, col_def['formula'])
        if not ok: return

        agg_options = ["Yok (Özette Gösterme)", "Toplam (Sum)", "Ortalama (Average)", "Fark (Maks-Min)", "Maksimum (Max)", "Minimum (Min)", "İlk Değer (First)", "Son Değer (Last)", "Sayı (Count)"]
        current_agg = col_def.get('agg', 'Toplam (Sum)')
        curr_idx = agg_options.index(current_agg) if current_agg in agg_options else 0
        new_agg, ok = QInputDialog.getItem(self, "Özet", "İşlem Türü:", agg_options, curr_idx, False)
        if not ok: return

        self.defined_columns[index].update({'name': new_name, 'formula': new_formula, 'agg': new_agg})
        self.mark_as_unsaved()

        self.refresh_table_headers()
    
    def delete_column(self, index):
        del self.defined_columns[index]
        self.mark_as_unsaved()
        self.refresh_table_headers()

    def run_report(self):
        if not self.defined_columns:
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir sütun ekleyin.")
            return

        full_date_column = self.date_column_combo.currentData() or self.date_column_combo.currentText()
        if full_date_column == "Tarih Sütunu Seçin...":
            QMessageBox.warning(self, "Uyarı", "Lütfen bir tarih sütunu seçin.")
            return

        start_date = self.date_Baslangic.date().toString("yyyy-MM-dd")
        end_date = self.date_Bitis.date().toString("yyyy-MM-dd")
        agg_type_str = self.agg_type_combo.currentText()

        self.main_window.show_loading_dialog("Rapor hazırlanıyor...")
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
        self.main_window.close_loading_dialog()
        if final_df is None: return

        logger.info(f"Rapor verisi alındı: {len(final_df)} satır.")
        self.current_df = final_df # Veriyi sakla
        self._populate_table(final_df)
        self.btn_export_excel.setEnabled(not final_df.empty)
    def _on_report_error(self, error_message):
        self.main_window.close_loading_dialog()
        logger.error(f"Rapor hatası: {error_message}")
        QMessageBox.critical(self, "Hata", f"Rapor hatası:\n{error_message}")


    def _populate_table(self, df):
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0) 

        if df.empty:
            logger.debug("DataFrame boş, tablo temizlendi.") 
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)
            return

        # Tarih index ise onu da sütun gibi düşün
        has_date_index = (df.index.name is not None)
        
        header_labels = list(df.columns)
        col_offset = 0
        
        if has_date_index:
            header_labels.insert(0, df.index.name if df.index.name else "Tarih")
            col_offset = 1 
            
        self.table.setColumnCount(len(header_labels) + 1) 
        self.table.setHorizontalHeaderLabels(header_labels + ["[Yeni Sütun Ekle]"])

        # Özet Satırları Yapılandırması
        summary_rows_config = [
            {"label": "TOPLAM",   "func": "sum",  "color": "#FFF176"}, # Sarı
            {"label": "ORTALAMA", "func": "mean", "color": "#FFF59D"}, # Açık Sarı
            {"label": "MAKSİMUM", "func": "max",  "color": "#A5D6A7"}, # Açık Yeşil
            {"label": "MİNİMUM",  "func": "min",  "color": "#EF9A9A"}  # Açık Kırmızı
        ]
        
        num_summary_rows = len(summary_rows_config)
        self.table.setRowCount(num_summary_rows + len(df))

        # --- 1. ÖZET SATIRLARINI OLUŞTUR ---
        for row_idx, config in enumerate(summary_rows_config):
            label = config["label"]
            func_name = config["func"]
            bg_color = QColor(config["color"])
            font = QFont("Arial", 10, QFont.Weight.Bold)

            # Sol Başlık
            v_header_item = QTableWidgetItem(label)
            v_header_item.setBackground(bg_color)
            self.table.setVerticalHeaderItem(row_idx, v_header_item)

            # Tarih/Index Sütunu (Boş Bırak veya Etiket Yaz)
            # İsteğinize göre burayı boş bırakıyoruz ki tarih toplanmasın
            item_label = QTableWidgetItem(label) if col_offset == 0 else QTableWidgetItem("")
            item_label.setFont(font)
            item_label.setBackground(bg_color)
            item_label.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, item_label)

            # Veri Sütunlarını Hesapla
            for j in range(len(df.columns)):
                # DÜZELTME 1: Sadece veriye odaklan (Sütun adını yok say)
                series = df.iloc[:, j]
                
                # DÜZELTME 2: Tarih kontrolü
                # Eğer veri tipi tarih ise veya obje olup tarih içeriyorsa atla
                if pd.api.types.is_datetime64_any_dtype(series):
                    display_text = "" # Tarihleri toplama, boş bırak
                else:
                    # DÜZELTME 3: .values kullanarak saf diziye çevir (Çakışmayı önler)
                    numeric_values = pd.to_numeric(series.values, errors='coerce')
                    
                    # Eğer hepsi NaN değilse (en az 1 sayı varsa)
                    if not pd.isna(numeric_values).all():
                        try:
                            # Numpy array üzerinde hesapla
                            series_temp = pd.Series(numeric_values)
                            val = series_temp.agg(func_name)
                            
                            if pd.isna(val):
                                display_text = ""
                            elif val % 1 == 0:
                                display_text = f"{int(val)}"
                            else:
                                display_text = f"{val:.2f}"
                        except:
                            display_text = ""
                    else:
                        display_text = "" # Sayısal değilse boş bırak

                # Hücreyi oluştur
                item = QTableWidgetItem(display_text)
                # Sıralama için data set et (Boşsa 0 kabul etme, en alta atması için eksi sonsuz veya benzeri mantık kurabiliriz ama şimdilik boş)
                item.setFont(font)
                item.setBackground(bg_color)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                self.table.setItem(row_idx, j + col_offset, item)

        # --- 2. ASIL VERİ SATIRLARINI EKLE ---
        for i in range(len(df)):
            table_row = i + num_summary_rows
            
            # Sol Numara (1'den başlar)
            v_header_num = QTableWidgetItem(str(i + 1))
            self.table.setVerticalHeaderItem(table_row, v_header_num)
            
            # Tarih Hücresi
            if has_date_index:
                idx = df.index[i]
                val_str = str(idx.strftime('%Y-%m-%d %H:%M:%S')) if hasattr(idx, 'strftime') else str(idx)
                self.table.setItem(table_row, 0, QTableWidgetItem(val_str))

            # Veri Hücreleri
            for j in range(len(df.columns)):
                raw_val = df.iloc[i, j]
                item = QTableWidgetItem()
                
                # Sayısal kontrol
                try:
                    float_val = float(raw_val)
                    is_numeric = True
                except (ValueError, TypeError):
                    is_numeric = False
                
                if is_numeric and not pd.isna(raw_val):
                    item.setData(Qt.ItemDataRole.EditRole, float_val)
                    if float_val % 1 == 0:
                        item.setData(Qt.ItemDataRole.DisplayRole, f"{int(float_val)}")
                    else:
                        item.setData(Qt.ItemDataRole.DisplayRole, f"{float_val:.2f}")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_val) if not pd.isna(raw_val) else "")
                
                self.table.setItem(table_row, j + col_offset, item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

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
            logger.error(f"Hata: Tarih sütunları doldurulamadı: {e}", exc_info=True)

        self.date_column_combo.blockSignals(False)
    
    def export_to_excel(self):
        if self.current_df.empty:
            QMessageBox.warning(self, "Veri Yok", "Dışa aktarılacak veri bulunamadı.")
            return

        # Tarihleri al (Klasör yapısı için)
        start_date_obj = self.date_Baslangic.date().toPyDate()
        end_date_obj = self.date_Bitis.date().toPyDate()
        
        target_name = "DinamikRapor"
        
        # Kayıt yolunu al (C:\rapor\excel\YIL\AY...)
        save_path = get_yeni_kayit_yolu(
            "excel", 
            start_date_obj, 
            end_date_obj, 
            target_name, 
            template_name="Ozel"
        )
        
        if not save_path:
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return

        temp_header_path = None
        try:
            # Editörden bitmiş halinin resmini al
            header_pixmap = self.header_editor.get_header_image()
            
            # Geçici bir dosyaya kaydet (temp klasörü daha iyi olur ama şimdilik proje dizini)
            temp_header_path = os.path.abspath("temp_header_export.png")
            header_pixmap.save(temp_header_path, "PNG")
            logger.info(f"Header tasarımı geçici olarak kaydedildi: {temp_header_path}")
        except Exception as e:
            logger.error(f"Header resmi oluşturulamadı: {e}")

        self.main_window.show_loading_dialog("Excel dosyası kaydediliyor...")

        
        logger.info(f"Excel dışa aktarılıyor: {save_path}")

        
        
        # Worker ile kaydet
        # (df index'ini de kaydetmek isteyebiliriz, özellikle özet modunda)
        df_to_save = self.current_df.copy()
        if df_to_save.index.name: # Eğer index varsa (Tarih) onu da sütun yap
            df_to_save.reset_index(inplace=True)

        worker = Worker(
            task_run_excel,
            save_path,
            df_to_save,
            header_image_path=temp_header_path)
        
        # İşlem bitince main_window'daki sekme açma fonksiyonunu çağır
        worker.signals.finished.connect(
            functools.partial(self._on_export_complete, save_path)
        )
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def _on_export_complete(self, save_path, result_path):
        """Excel kaydı bittiğinde çalışır."""
        self.main_window.close_loading_dialog()
        QMessageBox.information(self, "Başarılı", f"Dosya oluşturuldu:\n{save_path}")
        
        # --- YENİ: Dosya yolunu kaydet ve açma butonunu aktif et ---
        self.last_exported_excel_path = save_path

        self.btn_open_excel.setEnabled(True)
        
        # -----------------------------------------------------------
        
        # (Opsiyonel: Eğer otomatik sekme açma özelliğini kullanıyorsanız o kalsın)
        if hasattr(self.main_window, "open_generated_excel_tab"):
            self.main_window.open_generated_excel_tab(save_path)
    
    def open_generated_excel(self):
        """Son oluşturulan Excel dosyasını sistem varsayılan uygulamasıyla açar."""
        if self.last_exported_excel_path and os.path.exists(self.last_exported_excel_path):
            try:
                # İşletim sisteminin varsayılan programıyla aç (Windows'ta Excel)
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_exported_excel_path))
                logger.info(f"Excel dosyası açılıyor: {self.last_exported_excel_path}")
            except Exception as e:
                logger.error(f"Dosya açılırken hata: {e}")
                QMessageBox.warning(self, "Hata", f"Dosya açılamadı:\n{e}")
        else:
            QMessageBox.warning(self, "Dosya Bulunamadı", "Henüz oluşturulmuş veya kaydedilmiş bir Excel dosyası yok.")

    

    