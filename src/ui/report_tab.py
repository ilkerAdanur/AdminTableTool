# src/ui/report_tab.py

import os
import pandas as pd
import functools
from datetime import datetime

from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QInputDialog, 
    QLabel, QDialog, QHeaderView
)
from PyQt6.QtCore import Qt

# Çekirdek (Core) ve Görev (Task) importları
from src.core.database import load_excel_file
from src.core.file_exporter import get_yeni_kayit_yolu, task_run_excel, task_run_pdf
from src.core.data_processor import apply_template
from src.core.template_manager import load_template, get_available_templates
from src.core.report_manager import get_saved_report_dates
from src.core.tasks import fetch_and_apply_task
from src.threading.workers import Worker

def natural_sort_key(s):
    # Bu dosyada da sıralama gerektiği için ekliyoruz
    import re
    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]

class ReportTabWidget(QWidget):
    """
    Bir rapor sekmesini temsil eden ana widget.
    Kendi veritabanı yapılandırmasını, taslaklarını ve tablosunu yönetir.
    """
    def __init__(self, main_window, target_table, target_date_column):
        super().__init__(main_window) # Ebeveyn olarak main_window
        
        # Ana pencereden gelen bilgileri sakla
        self.main_window = main_window # Ana threadpool'a ve progress bar'a erişim için
        self.db_config = main_window.db_config
        self.target_table = target_table
        self.target_date_column = target_date_column
        
        # Bu sekmeye özel durum değişkenleri
        self.df = pd.DataFrame() 
        self.raw_df_from_excel = None
        self.currently_viewing_excel = None 
        self.report_history_files = [] 
        self.current_report_index = 0   
        
        # --- UI Dosyasını Yükle ---
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file_path = os.path.join(current_dir, 'report_tab.ui')
            loadUi(ui_file_path, self)
        except Exception as e:
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel(f"HATA: report_tab.ui yüklenemedi: {e}"))
            return
        
        # --- Başlangıç Ayarları ---
        self._connect_signals()
        self.update_tab_label() 
        self._load_available_templates()
        self._load_saved_report_dates() 
        
        self.btn_Excel.setEnabled(False)
        self.btn_PDF.setEnabled(False)
        self.commentLabel.setVisible(False)
        self.tbl_Veri.setSortingEnabled(True)

    def _connect_signals(self):
        """Bu sekmenin içindeki butonları fonksiyonlara bağlar."""
        self.btn_ApplyTemplate.clicked.connect(self.apply_selected_template)
        self.btn_Excel.clicked.connect(self.export_excel)
        self.btn_PDF.clicked.connect(self.export_pdf)
        
        self.tarihSecCBox.currentIndexChanged.connect(self._on_report_history_selected)
        self.geriTarihButton.clicked.connect(self._show_previous_report)
        self.ileriTarihButton.clicked.connect(self._show_next_report)
        
        self.templateSecCBox.currentIndexChanged.connect(self._on_template_selection_changed)

    def update_tab_label(self):
        """Bu sekmenin üst etiketini (veritabaniLabel) günceller."""
        db_type = self.db_config.get('type', 'Bilinmiyor')
        label_parts = [f"Sistem: {db_type.capitalize()}"]

        if db_type == 'access':
            db_name = os.path.basename(self.db_config.get('path', 'Bilinmiyor'))
            label_parts.append(f"Dosya: {db_name}")
        else:
            db_name = self.db_config.get('database', 'Bilinmiyor')
            host_name = self.db_config.get('host', 'Bilinmiyor')
            label_parts.append(f"DB: {db_name} ({host_name})")
            
        label_parts.append(f"Tablo: {self.target_table}")
        label_parts.append(f"Tarih Sütunu: {self.target_date_column}")
        
        if self.currently_viewing_excel:
             label_parts.append(f"Görüntülenen Excel: {self.currently_viewing_excel}")
             
        label_text = "  |  ".join(label_parts)
        self.veritabaniLabel.setText(label_text)
        self.veritabaniLabel.setToolTip(label_text)

    # --- Ana İş Akışı (MainWindow'dan Taşındı) ---
    
    def apply_selected_template(self):
        self.currently_viewing_excel = None
        self.raw_df_from_excel = None 
        self.commentLabel.setVisible(False)
        
        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None) 

        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")

        if is_raw_data_selected:
            self.main_window.show_loading_dialog("Ham veri getiriliyor...")
        else:
            self.main_window.show_loading_dialog(f"'{selected_template_name}' taslağı uygulanıyor...")

        worker = Worker(fetch_and_apply_task, 
                        self.db_config, 
                        self.target_table, 
                        baslangic, 
                        bitis, 
                        None if is_raw_data_selected else selected_template_name,
                        self.target_date_column)
                        
        worker.signals.finished.connect(self._on_query_or_template_applied) 
        worker.signals.error.connect(self.main_window._on_task_error) # Ana pencerenin hata işleyicisini kullan
        self.main_window.threadpool.start(worker)

    def _on_query_or_template_applied(self, processed_df):
        print(f"Sekme [{self.target_table}]: Veri alındı. Tablo dolduruluyor...")
        
        self.df = processed_df 
        self._populate_table(self.df) 
        
        # Butonları ayarla
        self.btn_Excel.setEnabled(not self.df.empty)
        self.btn_PDF.setEnabled(not self.df.empty)
        self.main_window.statusbar.clearMessage() 

        self.main_window.close_loading_dialog() 
        print(f"Sekme [{self.target_table}]: İşlem tamamlandı.")

    # --- Dışa Aktarma (MainWindow'dan Taşındı) ---
    
    def export_excel(self):
        if self.df.empty: 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return
            
        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyone l):")
        if not ok:
            return 

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()
        
        kayit_yolu = get_yeni_kayit_yolu("excel", start_date, end_date, self.target_table, current_template) 
        
        if not kayit_yolu: 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return 
            
        self.main_window.show_loading_dialog("Excel dosyası oluşturuluyor...")
        worker = Worker(task_run_excel, kayit_yolu, self.df.copy()) 
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def export_pdf(self):
        if self.df.empty: 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyonel):")
        if not ok:
            return 

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()
        
        kayit_yolu = get_yeni_kayit_yolu("pdf", start_date, end_date, self.target_table, current_template) 

        if not kayit_yolu: 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return

        self.main_window.show_loading_dialog("PDF dosyası oluşturuluyor...")
        worker = Worker(task_run_pdf, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def _on_export_finished(self, kayit_yolu, comment_to_save):
        self.main_window.close_loading_dialog()
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        
        if comment_to_save and comment_to_save.strip():
            print(f"'{kayit_yolu}' için yorum kaydediliyor...")
            save_report_comment(file_path=kayit_yolu, 
                                comment=comment_to_save, 
                                user="Admin")
        
        if kayit_yolu and kayit_yolu.endswith(".xlsx"):
            self._load_saved_report_dates() # Bu sekmenin kendi listesini yenile

    # --- Taslak Yönetimi (MainWindow'dan Taşındı) ---

    def _load_available_templates(self):
        self.templateSecCBox.blockSignals(True)
        self.templateSecCBox.clear()
        self.templateSecCBox.addItem("Taslak Uygulama (Varsayılan: Ham Veri)", userData=None) 
        templates = get_available_templates()
        if templates:
            for template_name in templates:
                self.templateSecCBox.addItem(template_name, userData=template_name) 
        self.templateSecCBox.blockSignals(False)

    def _on_template_selection_changed(self):
        if self.raw_df_from_excel is not None:
            self._apply_template_to_loaded_data()

    def _apply_template_to_loaded_data(self):
        if self.raw_df_from_excel is None or self.raw_df_from_excel.empty:
            return 

        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None)

        processed_df = None

        if is_raw_data_selected:
            processed_df = self.raw_df_from_excel.copy()
        elif selected_template_name:
            try:
                template_data = load_template(template_name=selected_template_name, parent_widget=self)
                if template_data:
                    processed_df = apply_template(self.raw_df_from_excel, template_data) 
                else:
                    QMessageBox.warning(self, "Taslak Hatası", "Taslak yüklenemedi. Ham veri gösteriliyor.")
                    processed_df = self.raw_df_from_excel.copy()
            except Exception as e:
                 QMessageBox.critical(self, "Taslak Uygulama Hatası", f"Taslak uygulanırken bir hata oluştu:\n{e}")
                 processed_df = self.raw_df_from_excel.copy()
        else:
             processed_df = self.raw_df_from_excel.copy()

        self.df = processed_df
        self._populate_table(self.df)
        self.btn_Excel.setEnabled(not self.df.empty)
        self.btn_PDF.setEnabled(not self.df.empty)

    # --- Rapor Geçmişi (MainWindow'dan Taşındı) ---

    def _load_saved_report_dates(self):
        self.tarihSecCBox.blockSignals(True)
        self.tarihSecCBox.clear()
        self.tarihSecCBox.addItem("Kaydedilmiş Rapor Seç...", userData=None)
        
        report_folders = get_saved_report_dates()
        try:
            sorted_keys = sorted(report_folders.keys(), key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
        except ValueError:
            sorted_keys = sorted(report_folders.keys())
        
        for key in sorted_keys:
            self.tarihSecCBox.addItem(key, userData=report_folders[key])
            
        self.tarihSecCBox.blockSignals(False)

    def _on_report_history_selected(self, index):
        folder_path = self.tarihSecCBox.currentData()
        if not folder_path:
            self.report_history_files = []
            self.df = pd.DataFrame() 
            self._populate_table(self.df)
            self.commentLabel.setVisible(False)
            self.currently_viewing_excel = None
            self.raw_df_from_excel = None
            self.main_window.statusbar.clearMessage()
            self.update_tab_label()
            self.btn_Excel.setEnabled(False)
            self.btn_PDF.setEnabled(False)
            return
            
        try:
            files = [f for f in os.listdir(folder_path) if f.endswith('.xlsx')]
            self.report_history_files = sorted(files, key=natural_sort_key) 
            
            if self.report_history_files:
                self.current_report_index = 0
                self._load_excel_from_history()
            else:
                self.report_history_files = []
                QMessageBox.warning(self, "Boş Klasör", "Bu tarih klasöründe .xlsx dosyası bulunamadı.")
                
        except Exception as e:
            QMessageBox.critical(self, "Klasör Okuma Hatası", f"Rapor klasörü okunurken hata:\n{e}")
            self.report_history_files = []

    def _load_excel_from_history(self):
        if not self.report_history_files: return
            
        try:
            folder_path = self.tarihSecCBox.currentData()
            file_name = self.report_history_files[self.current_report_index]
            full_path = os.path.join(folder_path, file_name)

            self.currently_viewing_excel = file_name 
            
            self.main_window.show_loading_dialog(f"{file_name} yükleniyor...")
            
            worker = Worker(load_excel_file, full_path) 
            worker.signals.finished.connect(self._on_excel_loaded) 
            worker.signals.error.connect(self.main_window._on_task_error)
            self.main_window.threadpool.start(worker)
            
            status_text = f"Yükleniyor: {file_name} ({self.current_report_index + 1} / {len(self.report_history_files)})"
            self.main_window.statusbar.showMessage(status_text)
            self.update_tab_label()
        
        except Exception as e:
            self.main_window._on_task_error(f"Excel yükleme başlatılamadı: {e}")
            self.currently_viewing_excel = None 
            self.raw_df_from_excel = None
            self.main_window.statusbar.clearMessage() 

    def _show_previous_report(self):
        if not self.report_history_files: return
        if self.current_report_index > 0:
            self.current_report_index -= 1
            self._load_excel_from_history()
            
    def _show_next_report(self):
        if not self.report_history_files: return
        if self.current_report_index < len(self.report_history_files) - 1:
            self.current_report_index += 1
            self._load_excel_from_history()

    def _on_excel_loaded(self, loaded_raw_df):
        self.main_window.close_loading_dialog()
        
        if loaded_raw_df is None or loaded_raw_df.empty:
             QMessageBox.warning(self, "Excel Boş", "Yüklenen Excel dosyasında veri bulunamadı.")
             self.raw_df_from_excel = None
             self.df = pd.DataFrame()
             self.commentLabel.setVisible(False) 
        else:
            self.raw_df_from_excel = loaded_raw_df.copy()
            folder_path = self.tarihSecCBox.currentData()
            file_name = self.currently_viewing_excel 
            
            if folder_path and file_name:
                full_path = os.path.join(folder_path, file_name)
                comments = load_report_comments(full_path)
                
                if comments:
                    formatted_comments = "Rapor Yorumları:\n"
                    for comment_data in comments[-3:]:
                        user = comment_data.get('user', 'Bilinmeyen')
                        timestamp = comment_data.get('timestamp', '')
                        comment_text = comment_data.get('comment', '...')
                        try:
                            ts_obj = datetime.fromisoformat(timestamp)
                            timestamp_str = ts_obj.strftime('%d.%m.%Y %H:%M')
                        except:
                            timestamp_str = "Bilinmeyen Tarih"
                        formatted_comments += f"- [{timestamp_str} - {user}]: {comment_text}\n"
                    self.commentLabel.setText(formatted_comments.strip())
                    self.commentLabel.setVisible(True)
                else:
                    self.commentLabel.setVisible(False)
            else:
                self.commentLabel.setVisible(False)

        self._apply_template_to_loaded_data()
        status_text = f"Gösterilen: {self.currently_viewing_excel} ({self.current_report_index + 1} / {len(self.report_history_files)})"
        self.main_window.statusbar.showMessage(status_text)
        self.update_tab_label()

    def _populate_table(self, df):
        self.tbl_Veri.setUpdatesEnabled(False)
        self.tbl_Veri.setSortingEnabled(False)
        self.tbl_Veri.setRowCount(0)
        self.tbl_Veri.setColumnCount(0)

        if df.empty:
            self.tbl_Veri.setSortingEnabled(True)
            self.tbl_Veri.setUpdatesEnabled(True)
            return

        self.tbl_Veri.setRowCount(len(df))
        self.tbl_Veri.setColumnCount(len(df.columns))
        self.tbl_Veri.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j in range(len(df.columns)):
                raw_value = df.iloc[i, j]
                item = QTableWidgetItem()
                is_numeric = isinstance(raw_value, (int, float))

                if is_numeric:
                    item.setData(Qt.ItemDataRole.EditRole, float(raw_value))
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(raw_value))

                self.tbl_Veri.setItem(i, j, item)
        
        self.tbl_Veri.setSortingEnabled(True)
        self.tbl_Veri.setUpdatesEnabled(True)