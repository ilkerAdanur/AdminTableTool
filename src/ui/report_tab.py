# src/ui/report_tab.py

import json
import os
import pandas as pd
import functools
import re
from datetime import datetime
import logging  # <-- 1. logging'i import edin

from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QInputDialog, 
    QLabel, QDialog, QHeaderView, QTableWidget, QApplication,QVBoxLayout,QDialog,QPushButton
)


from PyQt6.QtCore import Qt, QDate, QUrl  
from PyQt6.QtGui import QDesktopServices

from src.core.database import load_excel_file
from src.core.file_exporter import get_yeni_kayit_yolu, task_run_excel, task_run_pdf
from src.core.data_processor import apply_template
from src.core.template_manager import load_template, get_available_templates, TEMPLATE_DIR
from src.core.metadata_manager import save_report_comment, load_report_comments
from src.core.report_manager import get_saved_report_dates
from src.core.tasks import fetch_and_apply_task
from src.threading.workers import Worker
import json.decoder # Hata yakalama için eklendi

# <-- 2. Modüle özel logger'ı tanımlayın
logger = logging.getLogger(__name__)

def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]

class ReportTabWidget(QWidget):
    """
    'Eski' tip (Veri Gezgininden çift tıklayarak açılan)
    rapor sekmesini temsil eden widget.
    """
    def __init__(self, main_window, db_config, target_table, target_date_column, full_schema_data):
        super().__init__(main_window)
        
        logger.debug(f"ReportTabWidget '{target_table}' için başlatılıyor...") 
        self.main_window = main_window 
        self.db_config = db_config
        self.target_table = target_table
        self.target_date_column = target_date_column
        self.full_schema_data = full_schema_data
        
        self.df = pd.DataFrame() 
        self.raw_df_from_excel = None
        self.currently_viewing_excel = None 
        self.report_history_files = [] 
        self.current_report_index = 0   
        
        self.last_exported_excel_path = None
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file_path = os.path.join(current_dir, 'report_tab.ui')
            loadUi(ui_file_path, self)
            logger.info(f"ReportTabWidget UI ({ui_file_path}) başarıyla yüklendi.") 
        except Exception as e:
            
            logger.critical(f"HATA: report_tab.ui yüklenemedi: {e}", exc_info=True)
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel(f"HATA: report_tab.ui yüklenemedi: {e}"))
            return
        
        self.btn_OpenExcel = QPushButton("Exceli Aç")
        self.btn_OpenExcel.setStyleSheet("background-color: #8BC34A; color: white; padding: 5px; font-weight: bold;")
        self.btn_OpenExcel.setEnabled(False) # Başlangıçta pasif
        self.btn_OpenExcel.clicked.connect(self.open_generated_excel)
        
        idx = self.horizontalLayout_Buttons.indexOf(self.btn_Excel)
        self.horizontalLayout_Buttons.insertWidget(idx + 1, self.btn_OpenExcel)

        self._connect_signals()
        self.update_tab_label() 
        self._load_available_templates()
        self._load_saved_report_dates() 

        
        self.btn_Excel.setEnabled(False)
        self.btn_PDF.setEnabled(False)
        self.commentLabel.setVisible(False)
        self.tbl_Veri.setSortingEnabled(True)
        logger.debug(f"ReportTabWidget '{target_table}' için başlatma tamamlandı.") 

    def open_generated_excel(self):
        """Son oluşturulan Excel dosyasını sistem varsayılan uygulamasıyla açar."""
        if self.last_exported_excel_path and os.path.exists(self.last_exported_excel_path):
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_exported_excel_path))
                logger.info(f"Excel dosyası açılıyor: {self.last_exported_excel_path}")
            except Exception as e:
                logger.error(f"Dosya açılırken hata: {e}")
                QMessageBox.warning(self, "Hata", f"Dosya açılamadı:\n{e}")
        else:
            QMessageBox.warning(self, "Dosya Bulunamadı", "Henüz oluşturulmuş veya kaydedilmiş bir Excel dosyası yok.")

    def _on_export_finished(self, kayit_yolu, comment_to_save):
        self.main_window.close_loading_dialog()
        logger.info(f"Dosya başarıyla kaydedildi: {kayit_yolu}") 
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        
        # --- YENİ: Excel ise yolu kaydet ve butonu aç ---
        if kayit_yolu and kayit_yolu.endswith(".xlsx"):
            self.last_exported_excel_path = kayit_yolu
            self.btn_OpenExcel.setEnabled(True)
            
            logger.info("Excel kaydedildiği için kaydedilmiş rapor tarihleri yenileniyor.") 
            self._load_saved_report_dates() 
        # -----------------------------------------------

        if comment_to_save and comment_to_save.strip():
            logger.info(f"'{kayit_yolu}' için yorum kaydediliyor.") 
            save_report_comment(file_path=kayit_yolu, comment=comment_to_save)

    def _connect_signals(self):
        self.btn_ApplyTemplate.clicked.connect(self.apply_selected_template)
        self.btn_Excel.clicked.connect(self.export_excel)
        self.btn_PDF.clicked.connect(self.export_pdf)
        
        self.tarihSecCBox.currentIndexChanged.connect(self._on_report_history_selected)
        self.geriTarihButton.clicked.connect(self._show_previous_report)
        self.ileriTarihButton.clicked.connect(self._show_next_report)
        
        self.templateSecCBox.currentIndexChanged.connect(self._on_template_selection_changed)

    def update_tab_label(self):
        # (Bu fonksiyon çok sık çağrıldığı için loglamayı debug seviyesinde tutmak daha iyi)
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
        logger.debug(f"Sekme etiketi güncellendi: {label_text}") 

    def apply_selected_template(self):
        logger.info(f"'{self.target_table}' sekmesinde 'Taslak Uygula' tıklandı.") 
        self.currently_viewing_excel = None
        self.raw_df_from_excel = None 
        self.commentLabel.setVisible(False)
        
        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None) 

        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")

        if is_raw_data_selected:
            logger.info("Ham veri sorgusu çalıştırılıyor...") 
            self.main_window.show_loading_dialog("Ham veri getiriliyor...")
        else:
            logger.info(f"'{selected_template_name}' taslağı ile sorgu çalıştırılıyor...") 
            self.main_window.show_loading_dialog(f"'{selected_template_name}' taslağı uygulanıyor...")

        worker = Worker(fetch_and_apply_task, 
                        self.db_config, 
                        self.target_table, 
                        baslangic, 
                        bitis, 
                        None if is_raw_data_selected else selected_template_name,
                        self.target_date_column)
                        
        worker.signals.finished.connect(self._on_query_or_template_applied) 
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def _on_query_or_template_applied(self, processed_df):
        logger.info(f"Sekme [{self.target_table}]: Veri alındı. {len(processed_df)} satır. Tablo dolduruluyor...")
        
        self.df = processed_df 
        self._populate_table(self.df) 
        
        self.btn_Excel.setEnabled(not self.df.empty)
        self.btn_PDF.setEnabled(not self.df.empty)
        self.main_window.statusbar.clearMessage() 

        self.main_window.close_loading_dialog() 
        logger.info(f"Sekme [{self.target_table}]: İşlem tamamlandı.") 
    
    def export_excel(self):
        logger.info("'Excel'e Aktar' tıklandı.") 
        if self.df.empty: 
            logger.warning("Dışa aktarılacak veri bulunamadı (df.empty).") 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return
            
        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyonele):")
        if not ok:
            logger.info("Kullanıcı yorum girişini iptal etti.") 
            return 

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()
        
        kayit_yolu = get_yeni_kayit_yolu("excel", start_date, end_date, self.target_table, current_template) 
        
        if not kayit_yolu: 
            logger.error("Kayıt yolu oluşturulamadı (get_yeni_kayit_yolu None döndü).") 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return 
            
        logger.info(f"Excel dışa aktarma worker'ı başlatılıyor. Yol: {kayit_yolu}") 
        self.main_window.show_loading_dialog("Excel dosyası oluşturuluyor...")
        worker = Worker(task_run_excel, kayit_yolu, self.df.copy()) 
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def export_pdf(self):
        logger.info("'PDF'e Aktar' tıklandı.") 
        if self.df.empty: 
            logger.warning("Dışa aktarılacak veri bulunamadı (df.empty).") 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyonel):")
        if not ok:
            logger.info("Kullanıcı yorum girişini iptal etti.") 
            return 

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()
        
        kayit_yolu = get_yeni_kayit_yolu("pdf", start_date, end_date, self.target_table, current_template) 

        if not kayit_yolu: 
            logger.error("Kayıt yolu oluşturulamadı (get_yeni_kayit_yolu None döndü).") 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return

        logger.info(f"PDF dışa aktarma worker'ı başlatılıyor. Yol: {kayit_yolu}") 
        self.main_window.show_loading_dialog("PDF dosyası oluşturuluyor...")
        worker = Worker(task_run_pdf, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

    def _on_export_finished(self, kayit_yolu, comment_to_save):
        self.main_window.close_loading_dialog()
        logger.info(f"Dosya başarıyla kaydedildi: {kayit_yolu}") 
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        
        if comment_to_save and comment_to_save.strip():
            logger.info(f"'{kayit_yolu}' için yorum kaydediliyor.") 
            save_report_comment(file_path=kayit_yolu, comment=comment_to_save, user="Admin")
        
        if kayit_yolu and kayit_yolu.endswith(".xlsx"):
            logger.info("Excel kaydedildiği için kaydedilmiş rapor tarihleri yenileniyor.") 
            self._load_saved_report_dates() 

    def _load_available_templates(self):
        logger.debug("Kullanılabilir taslaklar combobox'ı dolduruluyor...") 
        self.templateSecCBox.blockSignals(True)
        self.templateSecCBox.clear()
        self.templateSecCBox.addItem("Taslak Uygulama (Varsayılan: Ham Veri)", userData=None) 
        templates = get_available_templates()
        if templates:
            for template_name in templates:
                self.templateSecCBox.addItem(template_name, userData=template_name) 
            logger.debug(f"{len(templates)} adet taslak yüklendi.") 
        self.templateSecCBox.blockSignals(False)

    def _on_template_selection_changed(self):
        if self.raw_df_from_excel is not None:
            logger.debug("Excel verisi yüklü, taslak değişikliği algılandı. _apply_template_to_loaded_data çağrılıyor.") 
            self._apply_template_to_loaded_data()

    def _apply_template_to_loaded_data(self):
        if self.raw_df_from_excel is None or self.raw_df_from_excel.empty:
            logger.warning("_apply_template_to_loaded_data çağrıldı ama 'raw_df_from_excel' boş.") 
            return 

        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None)
        processed_df = None

        logger.info(f"Yüklü Excel verisine taslak uygulanıyor: '{selected_template_name}'") 

        if is_raw_data_selected:
            processed_df = self.raw_df_from_excel.copy()
        elif selected_template_name:
            try:
                template_data = load_template(template_name=selected_template_name)
                if template_data:
                    processed_df = apply_template(self.raw_df_from_excel, template_data) 
                else:
                    logger.error("Taslak verisi 'load_template' fonksiyonundan None döndü.") 
                    QMessageBox.warning(self, "Taslak Hatası", "Taslak yüklenemedi. Ham veri gösteriliyor.")
                    processed_df = self.raw_df_from_excel.copy()
            
            except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
                 logger.error(f"Taslak yüklenirken hata (Core hatası): {e}", exc_info=True) 
                 QMessageBox.critical(self, "Taslak Uygulama Hatası", f"Taslak yüklenirken bir hata oluştu:\n{e}")
                 processed_df = self.raw_df_from_excel.copy()
            except Exception as e:
                 logger.error(f"Taslak uygulanırken (apply_template) hata: {e}", exc_info=True) 
                 QMessageBox.critical(self, "Taslak Uygulama Hatası", f"Taslak uygulanırken bir hata oluştu:\n{e}")
                 processed_df = self.raw_df_from_excel.copy()
        else:
             processed_df = self.raw_df_from_excel.copy()

        self.df = processed_df
        self._populate_table(self.df)
        self.btn_Excel.setEnabled(not self.df.empty)
        self.btn_PDF.setEnabled(not self.df.empty)
        logger.info("Yüklü Excel verisine taslak uygulama tamamlandı.") 

    def _load_saved_report_dates(self):
        """Dosya sistemini tarar ve ComboBox'ı doldurur."""
        logger.debug("Kaydedilmiş rapor tarihleri combobox'ı dolduruluyor...") 
        
        self.tarihSecCBox.blockSignals(True)
        self.tarihSecCBox.clear()
        self.tarihSecCBox.addItem("Kaydedilmiş Rapor Seç...", userData=None)
        
        # Core modülden klasörleri al
        report_folders = get_saved_report_dates()
        
        # Tarihe göre sıralama (İsteğe bağlı, string olarak sıralar)
        try:
            # "20_10_2023" formatını datetime'a çevirip sıralayalım
            sorted_keys = sorted(report_folders.keys(), key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
        except ValueError:
            sorted_keys = sorted(report_folders.keys())
        
        for key in sorted_keys:
            self.tarihSecCBox.addItem(key, userData=report_folders[key])
            
        logger.debug(f"{len(report_folders)} adet kaydedilmiş rapor tarihi bulundu.") 
        self.tarihSecCBox.blockSignals(False)
    
    def _on_report_history_selected(self, index):
        folder_path = self.tarihSecCBox.currentData()
        
        if not folder_path:
            logger.debug("Geçmiş rapor seçimi temizlendi.") 
            self.report_history_files = []
            # ... (temizleme işlemleri) ...
            return
            
        logger.info(f"Geçmiş rapor klasörü seçildi: {folder_path}") 
        
        try:
            # Klasördeki sadece .xlsx dosyalarını al
            files = [f for f in os.listdir(folder_path) if f.endswith('.xlsx')]
            
            # Sıralama (natural sort)
            self.report_history_files = sorted(files, key=natural_sort_key) 
            
            if self.report_history_files:
                # İlk dosyayı yükle
                self.current_report_index = 0
                self._load_excel_from_history()
            else:
                self.report_history_files = []
                QMessageBox.warning(self, "Boş Klasör", "Bu tarih klasöründe .xlsx dosyası bulunamadı.")
                
        except Exception as e:
            logger.error(f"Rapor klasörü okunurken hata: {e}", exc_info=True) 
            QMessageBox.critical(self, "Klasör Okuma Hatası", f"Rapor klasörü okunurken hata:\n{e}")
            self.report_history_files = []

    def _load_excel_from_history(self):
        if not self.report_history_files: return
            
        try:
            folder_path = self.tarihSecCBox.currentData()
            file_name = self.report_history_files[self.current_report_index]
            full_path = os.path.join(folder_path, file_name)

            self.currently_viewing_excel = file_name 
            
            logger.info(f"Geçmiş Excel yükleme worker'ı başlatılıyor: {full_path}") 
            self.main_window.show_loading_dialog(f"{file_name} yükleniyor...")
            
            worker = Worker(load_excel_file, full_path) 
            worker.signals.finished.connect(self._on_excel_loaded) 
            worker.signals.error.connect(self.main_window._on_task_error)
            self.main_window.threadpool.start(worker)
            
            status_text = f"Yükleniyor: {file_name} ({self.current_report_index + 1} / {len(self.report_history_files)})"
            self.main_window.statusbar.showMessage(status_text)
            self.update_tab_label()
        
        except Exception as e:
            logger.error(f"Excel yükleme worker'ı başlatılamadı: {e}", exc_info=True) 
            self.main_window._on_task_error(f"Excel yükleme başlatılamadı: {e}")
            self.currently_viewing_excel = None 
            self.raw_df_from_excel = None
            self.main_window.statusbar.clearMessage() 

    def _show_previous_report(self):
        if not self.report_history_files: return
        if self.current_report_index > 0:
            logger.debug("Önceki rapora geçiliyor.") 
            self.current_report_index -= 1
            self._load_excel_from_history()
            
    def _show_next_report(self):
        if not self.report_history_files: return
        if self.current_report_index < len(self.report_history_files) - 1:
            logger.debug("Sonraki rapora geçiliyor.")
            self.current_report_index += 1
            self._load_excel_from_history()


    def _on_excel_loaded(self, loaded_raw_df):
        self.main_window.close_loading_dialog()
        
        if loaded_raw_df is None or loaded_raw_df.empty:
             logger.warning(f"Yüklenen Excel dosyası ({self.currently_viewing_excel}) boş.") 
             QMessageBox.warning(self, "Excel Boş", "Yüklenen Excel dosyasında veri bulunamadı.")
             self.raw_df_from_excel = None
             self.df = pd.DataFrame()
             self.commentLabel.setVisible(False) 
             self.btn_OpenExcel.setEnabled(False) # <-- EKLENDİ
        else:
            logger.info(f"Excel dosyası başarıyla yüklendi: {self.currently_viewing_excel} ({len(loaded_raw_df)} satır)") 
            self.raw_df_from_excel = loaded_raw_df.copy()
            
            # --- DÜZELTME BAŞLANGICI: Dosya yolunu bul ve butonu aktif et ---
            folder_path = self.tarihSecCBox.currentData()
            file_name = self.currently_viewing_excel 
            
            full_path = ""
            # Eğer klasörden seçildiyse:
            if folder_path and file_name:
                full_path = os.path.join(folder_path, file_name)
            # Eğer dışarıdan özel yükleme yapıldıysa (load_specific_file):
            elif hasattr(self, 'special_file_path') and self.special_file_path:
                full_path = self.special_file_path
            
            # Eğer dosya varsa butonu ayarla
            if full_path and os.path.exists(full_path):
                self.last_exported_excel_path = full_path
                self.btn_OpenExcel.setEnabled(True)
            # --- DÜZELTME SONU ---

            if folder_path and file_name:
                # Yorumları yükle (Eğer klasör yapısındaysa)
                comments = load_report_comments(full_path)
                if comments:
                    logger.debug(f"{len(comments)} adet yorum bulundu, gösteriliyor.") 
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
        status_text = f"Gösterilen: {self.currently_viewing_excel}"
        if self.report_history_files:
             status_text += f" ({self.current_report_index + 1} / {len(self.report_history_files)})"
             
        self.main_window.statusbar.showMessage(status_text)
        self.update_tab_label()


    def _populate_table(self, df):
        logger.debug(f"Tabloyu {len(df)} satır ve {len(df.columns)} sütun ile doldurma işlemi başlıyor...") 
        self.tbl_Veri.setUpdatesEnabled(False)
        self.tbl_Veri.setSortingEnabled(False)
        self.tbl_Veri.setRowCount(0)
        self.tbl_Veri.setColumnCount(0)

        if df.empty:
            logger.debug("DataFrame boş, tablo temizlendi.") 
            self.tbl_Veri.setSortingEnabled(True)
            self.tbl_Veri.setUpdatesEnabled(True)
            return

        self.tbl_Veri.setRowCount(len(df))
        self.tbl_Veri.setColumnCount(len(df.columns))
        self.tbl_Veri.setHorizontalHeaderLabels(df.columns.astype(str))

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
        logger.debug("Tabloyu doldurma işlemi tamamlandı.") 
    
    def load_specific_file(self, file_path):
        """
        (YENİ) Dışarıdan verilen tam dosya yolundaki Excel'i bu sekmede açar.
        """
        if not os.path.exists(file_path):
            logger.error(f"Dosya bulunamadı: {file_path}")
            return

        self.currently_viewing_excel = os.path.basename(file_path)
        self.special_file_path = file_path # <-- EKLENDİ: Yolu sakla
        
        logger.info(f"Özel dosya yükleniyor: {file_path}")

        # Yükleme worker'ını başlat
        self.main_window.show_loading_dialog(f"{self.currently_viewing_excel} açılıyor...")
        worker = Worker(load_excel_file, file_path)
        worker.signals.finished.connect(self._on_excel_loaded)
        worker.signals.error.connect(self.main_window._on_task_error)
        self.main_window.threadpool.start(worker)

