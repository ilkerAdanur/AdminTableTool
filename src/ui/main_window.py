# src/ui/main_window.py

import sys
import os
import re
import traceback 
import functools
from datetime import datetime
import pandas as pd

from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal, Qt, QDate
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTableWidgetItem, 
    QMessageBox, QProgressDialog,QInputDialog, QDialog,
    QFileDialog, QInputDialog, QLabel
)
from PyQt6.QtGui import QCloseEvent
from PyQt6.uic import loadUi 
from .db_explorer_window import DbExplorerWindow

# Göreli UI importları
from .dialogs import ConnectionDialog, TemplateEditorDialog
from .daily_summary_dialog import DailySummaryDialog

# Çekirdek (Core) ve Görev (Task) importları
from src.core.database import load_excel_file # Sadece excel yükleme burada lazım
from src.core.file_exporter import get_yeni_kayit_yolu, task_run_excel, task_run_pdf
from src.core.data_processor import apply_template
from src.core.template_manager import load_template, get_available_templates
from src.core.report_manager import get_saved_report_dates # Yeni report manager
from src.core.metadata_manager import save_report_comment,load_report_comments
from src.core.tasks import (
    fetch_and_apply_task, get_column_names_task, run_summary_task
    ,get_tables_task
)

from src.core.utils import register_pdf_fonts
from src.threading.workers import Worker, WorkerSignals

# Doğal sıralama fonksiyonu (burada veya utils'te olabilir)
def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file_path = os.path.join(current_dir, 'arayuz.ui')
            loadUi(ui_file_path, self) 
        except Exception as e:
             QMessageBox.critical(self, "UI Yükleme Hatası", f"'arayuz.ui' yüklenemedi: {e}")
             sys.exit() # UI olmadan program çalışamaz

        # --- Sınıf Değişkenleri ---
        self.df = pd.DataFrame() 
        self.raw_df_from_excel = None
        
        self.db_config = {}
        self.db_engine = None     
        self.target_table = None  
        self.target_date_column = None 
        self.currently_viewing_excel = None 

        self.db_explorer = DbExplorerWindow()

        self.report_history_files = [] # Rapor geçmişi dosyalarını tutar
        self.current_report_index = 0   
        
        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")

        self.tbl_Veri.setSortingEnabled(True)
        self.progress_dialog = None

        self.status_light = QLabel()
        self.statusbar.addPermanentWidget(self.status_light)
        self.commentLabel.setVisible(False)
        
        self.df = pd.DataFrame()
        # --- Sinyal-Slot Bağlantıları ---
        self._connect_signals()

        # --- Başlangıç Ayarları ---
        self.update_connection_status() 
        self._load_saved_report_dates() # Eski 'kayitli_raporlari_tara'
        self._load_available_templates()

    def _connect_signals(self):
        """Tüm UI sinyallerini slotlara (fonksiyonlara) bağlar."""
        
        # Menü Eylemleri (Veritabanı)
        try:
            self.actionVeritaban_n_Se.triggered.connect(self.open_connection_settings)
            self.actionAccess_Database.triggered.connect(
                functools.partial(self.set_database_type, "access")
            )
            self.actionMicrosoft_SQL.triggered.connect(
                functools.partial(self.set_database_type, "sql")
            )
            self.actionPostgreSQL.triggered.connect(
                functools.partial(self.set_database_type, "postgres")
            )
        except AttributeError as e:
            print(f"UYARI: 'arayuz.ui' dosyasındaki Veritabanı menü eylemleri kodla eşleşmiyor. {e}")

        # Menü Eylemleri (Ayarlar ve Araçlar)
        try:
            self.actionTaslak_Duzenle.triggered.connect(self.open_template_editor)
            self.actionGunluk_Ozet_Raporu.triggered.connect(self.open_daily_summary_dialog)
            self.actionVeritabani_Gezgini.triggered.connect(self.db_explorer.show)
        except AttributeError as e:
             print(f"UYARI: 'arayuz.ui' dosyasındaki Ayarlar/Araçlar/Gezgin menü eylemleri kodla eşleşmiyor. {e}")

        # Ana Butonlar
        try:
            # self.btn_Sorgula.clicked.connect(self.apply_selected_template) # Eski buton, 'btn_ApplyTemplate' tercih ediliyor
            self.btn_ApplyTemplate.clicked.connect(self.apply_selected_template)
            self.btn_Excel.clicked.connect(self.export_excel)
            self.btn_PDF.clicked.connect(self.export_pdf)
        except AttributeError as e:
             print(f"UYARI: 'arayuz.ui' dosyasındaki ana butonlar kodla eşleşmiyor. {e}")

        # Rapor Geçmişi (Eski Excel'ler)
        self.tarihSecCBox.currentIndexChanged.connect(self._on_report_history_selected)
        self.geriTarihButton.clicked.connect(self._show_previous_report)
        self.ileriTarihButton.clicked.connect(self._show_next_report)
        
        # Taslak Seçimi
        self.templateSecCBox.currentIndexChanged.connect(self._on_template_selection_changed)

    # --- Veritabanı Bağlantı Fonksiyonları ---

    def set_database_type(self, db_type):
        """Menüden bir veritabanı sistemi (Access, SQL...) seçildiğinde çalışır."""
        print(f"Veritabanı türü '{db_type}' olarak ayarlandı.")
        
        self.db_config = {'type': db_type}
        self.target_table = None
        self.target_date_column = None
        self.currently_viewing_excel = None
        self.raw_df_from_excel = None
        self.db_explorer.clear_tree()
        self.df = pd.DataFrame()
        self._populate_table(self.df)
        
        self.update_connection_status()
        self.statusbar.showMessage(f"Tür '{db_type}' seçildi. Lütfen 'Veritabanı -> Veritabanını Seç' menüsünden bağlantı kurun.", 5000)
        self.open_connection_settings()

    def open_connection_settings(self):
        """'Veritabanını Seç' menüsüne tıklandığında dinamik bağlantı diyaloğunu açar."""
        selected_type = self.db_config.get('type')
        if not selected_type:
            QMessageBox.warning(self, "Tür Seçilmedi", 
                "Lütfen önce 'Veritabanı -> Veritabanı Sistemleri' menüsünden bir sistem türü seçin.")
            return

        dialog = ConnectionDialog(selected_type, self)
        
        if dialog.exec():
            self.db_config = dialog.get_config()
            print(f"Bağlantı ayarları alındı: {self.db_config}")
            self.target_table = None
            self.target_date_column = None
            self.currently_viewing_excel = None
            self.raw_df_from_excel = None
            self._load_tables_from_db()
        else:
            print("Bağlantı ayarları iptal edildi.")
            self.db_config = {}
            self.target_table = None
            self.db_explorer.clear_tree()
            self.target_date_column = None
            self.currently_viewing_excel = None
            self.raw_df_from_excel = None
            self.update_connection_status()

    def _load_tables_from_db(self):
        """Tablo listesini çekmek için bir worker başlatır."""
        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")
        worker = Worker(get_tables_task, self.db_config) 
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_tables_loaded(self, results):
        """(Callback) Tablo listesini alır, tabloyu seçtirir ve tarih sütununu seçtirir."""
        self.close_loading_dialog()
        
        try:
            table_list, engine = results 
        except Exception as e:
            self._on_task_error(f"Tablo yükleme sonucu işlenemedi: {results} - Hata: {e}")
            return
            
        self.db_engine = engine 
        
        if not table_list:
            QMessageBox.warning(self, "Hata", "Veritabanında okunabilir bir tablo bulunamadı.")
            self.db_config = {} 
            self.update_connection_status()
            return
            
        table_name, ok = QInputDialog.getItem(
            self, "Tablo Seç", "Lütfen sorgulanacak tabloyu seçin:",
            table_list, 0, False
        )
        
        if ok and table_name:
            self.target_table = table_name
            print(f"Kullanıcı '{table_name}' tablosunu seçti. Şimdi sütunlar çekilecek...")
            self.show_loading_dialog(f"'{table_name}' tablosunun sütunları okunuyor...")
            worker = Worker(get_column_names_task, self.db_config, self.target_table)
            worker.signals.finished.connect(self._on_columns_loaded_for_date_selection)
            worker.signals.error.connect(self._on_task_error)
            self.threadpool.start(worker)
        else:
            self.db_config = {} 
            self.target_table = None
            self.target_date_column = None
            print("Tablo seçimi iptal edildi.")
            self.update_connection_status()

    def _on_columns_loaded_for_date_selection(self, column_names):
        """(Callback) Sütun adları geldikten sonra kullanıcıya tarih sütununu seçtirir."""
        self.close_loading_dialog()

        if not column_names:
             QMessageBox.warning(self, "Sütun Hatası", f"'{self.target_table}' tablosunun sütunları okunamadı.")
             self.db_config = {}
             self.target_table = None
             self.target_date_column = None
             self.update_connection_status()
             return

        date_col, ok = QInputDialog.getItem(
            self, "Tarih Sütununu Seç",
            "Lütfen tarih filtrelemesi için kullanılacak sütunu seçin:",
            column_names, 0, False
        )

        if ok and date_col:
            self.target_date_column = date_col
            print(f"Kullanıcı tarih sütunu olarak '{date_col}' seçti.")
            try:
                self.db_explorer.populate_tree(self.db_config, self.target_table, column_names)
            except Exception as e:
                print(f"HATA: Veritabanı Gezgini doldurulamadı: {e}")
        else:
            self.db_config = {}
            self.target_table = None
            self.target_date_column = None
            self.db_explorer.clear_tree()
            print("Tarih sütunu seçimi iptal edildi.")

        self.update_connection_status()

    # --- Ana Raporlama İş Akışı ---

    def apply_selected_template(self):
        """'Taslağı Uygula' (Rapor Al) butonuna basıldığında çalışır."""
        
        self.currently_viewing_excel = None
        self.raw_df_from_excel = None 
        
        self.commentLabel.setVisible(False)
        self.commentLabel.setText("")
        
        if not self.db_config or not self.target_table or not self.target_date_column:
            QMessageBox.warning(self, "Eksik Bilgi", 
                "Lütfen önce 'Veritabanı' menüsünden bir bağlantı kurun (Sistem, Tablo ve Tarih Sütunu).")
            return

        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None) 

        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")

        if is_raw_data_selected:
            self.show_loading_dialog("Ham veri getiriliyor...")
        else:
            self.show_loading_dialog(f"'{selected_template_name}' taslağı uygulanıyor...")

        # Worker'a 'tasks.py' dosyasındaki görevi ver
        worker = Worker(fetch_and_apply_task, 
                        self.db_config, 
                        self.target_table, 
                        baslangic, 
                        bitis, 
                        None if is_raw_data_selected else selected_template_name,
                        self.target_date_column)
                        
        worker.signals.finished.connect(self._on_query_or_template_applied) 
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_query_or_template_applied(self, processed_df):
        """(Callback) Worker'dan gelen SONUCU (işlenmiş veya ham) tabloya yükler."""
        print("Ana arayüz: İşlenmiş veri alındı. Tablo dolduruluyor...")
        
        self.df = processed_df 
        self._populate_table(self.df) 
        self.update_connection_status()
        self.statusbar.clearMessage() # Eski Excel mesajını (varsa) temizle

        self.close_loading_dialog() 
        print(f"Ana arayüz: İşlem tamamlandı ve sonuç tabloya yüklendi.")

    # --- Taslak (Template) Yönetimi ---

    def open_template_editor(self):
        """'Rapor Taslaklarını Yönet' menüsüne tıklandığında çalışır."""
        source_cols = []
        
        if not self.df.empty:
            source_cols = list(self.df.columns)
            self._show_template_editor_dialog(source_cols)
            
        elif self.db_config and self.target_table:
            self.show_loading_dialog("Kaynak sütunlar okunuyor...")
            worker = Worker(get_column_names_task, self.db_config, self.target_table)
            worker.signals.finished.connect(self._on_columns_loaded_for_editor) 
            worker.signals.error.connect(self._on_task_error)
            self.threadpool.start(worker)
        else:
             QMessageBox.warning(self, "Bağlantı Gerekli", 
                                 "Taslak düzenleyiciyi açmak için lütfen önce bir veritabanına bağlanın.")
             return

    def _on_columns_loaded_for_editor(self, column_names):
        """(Callback) Veritabanından sütun adları gelince Taslak Editörünü açar."""
        self.close_loading_dialog()
        if column_names:
            print(f"Kaynak sütunlar veritabanından alındı: {column_names}")
            self._show_template_editor_dialog(column_names)
        else:
            QMessageBox.warning(self, "Sütun Hatası", "Seçili tablonun sütun adları okunamadı.")

    def _show_template_editor_dialog(self, source_columns):
        """TemplateEditorDialog'u açar ve sonucu işler."""
        dialog = TemplateEditorDialog(source_columns=source_columns, parent=self)
        result = dialog.exec() 

        if result == QDialog.DialogCode.Accepted: 
            template_data = dialog.get_template_data()
            print("Alınan Taslak Verisi:", template_data)
            self._load_available_templates() # Listeyi yenile
            if template_data and template_data.get("template_name"):
                index = self.templateSecCBox.findText(template_data["template_name"])
                if index >= 0:
                    self.templateSecCBox.setCurrentIndex(index)
        else:
            print("Taslak Düzenleyici iptal edildi.")

    def _load_available_templates(self):
        """Kaydedilmiş taslakları tarar ve templateSecCBox'ı doldurur."""
        print("Kullanılabilir taslaklar yükleniyor...")
        self.templateSecCBox.blockSignals(True)
        self.templateSecCBox.clear()
        
        self.templateSecCBox.addItem("Taslak Uygulama (Varsayılan: Ham Veri)", userData=None) 
        
        templates = get_available_templates()
        if templates:
            for template_name in templates:
                self.templateSecCBox.addItem(template_name, userData=template_name) 
            print(f"{len(templates)} adet taslak bulundu.")
        else:
            print("Kaydedilmiş taslak bulunamadı.")
            
        self.templateSecCBox.blockSignals(False)

    def _on_template_selection_changed(self):
        """Excel'e göz atarken taslak ComboBox'ı değiştiğinde tetiklenir."""
        if self.raw_df_from_excel is not None:
            self._apply_template_to_loaded_data()

    def _apply_template_to_loaded_data(self):
        """Mevcut self.raw_df_from_excel'e seçili taslağı uygular."""
        if self.raw_df_from_excel is None or self.raw_df_from_excel.empty:
            return 

        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData()
        is_raw_data_selected = (selected_template_data is None)

        processed_df = None

        if is_raw_data_selected:
            print("Ham veri taslağı seçili, orijinal Excel verisi kullanılıyor.")
            processed_df = self.raw_df_from_excel.copy()
        elif selected_template_name:
            print(f"'{selected_template_name}' taslağı mevcut Excel verisine uygulanıyor...")
            try:
                template_data = load_template(template_name=selected_template_name, parent_widget=self)
                if template_data:
                    processed_df = apply_template(self.raw_df_from_excel, template_data) 
                else:
                    QMessageBox.warning(self, "Taslak Hatası", f"'{selected_template_name}' taslağı yüklenemedi. Ham veri gösteriliyor.")
                    processed_df = self.raw_df_from_excel.copy()
            except Exception as e:
                 QMessageBox.critical(self, "Taslak Uygulama Hatası", f"Taslak uygulanırken bir hata oluştu:\n{e}")
                 processed_df = self.raw_df_from_excel.copy()
        else:
             processed_df = self.raw_df_from_excel.copy()

        self.df = processed_df
        print("Tablo yeni işlenmiş veriyle dolduruluyor...")
        self._populate_table(self.df)
        self.update_connection_status()

    # --- Rapor Geçmişi (Eski Excel) Yönetimi ---

    def _load_saved_report_dates(self):
        """Kaydedilmiş Excel raporlarını tarar ve tarihSecCBox'ı doldurur."""
        print("Kaydedilmiş rapor tarihleri taranıyor...")
        self.tarihSecCBox.blockSignals(True)
        self.tarihSecCBox.clear()
        
        self.tarihSecCBox.addItem("Kaydedilmiş Rapor Seç...", userData=None)
        
        report_folders = get_saved_report_dates() # core.report_manager'dan
        
        try:
            sorted_keys = sorted(report_folders.keys(), 
                                 key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
        except ValueError:
            sorted_keys = sorted(report_folders.keys())
        
        for key in sorted_keys:
            self.tarihSecCBox.addItem(key, userData=report_folders[key])
            
        print(f"Tarama tamamlandı. {len(report_folders)} adet rapor tarihi bulundu.")
        self.tarihSecCBox.blockSignals(False)

    def _on_report_history_selected(self, index):
        """tarihSecCBox'tan bir tarih seçildiğinde Excel dosyalarını yükler."""
        folder_path = self.tarihSecCBox.currentData()
        if not folder_path: # "Kaydedilmiş Rapor Seç..." seçiliyse
            self.report_history_files = []
            self.df = pd.DataFrame() 
            self._populate_table(self.df)

            # Yorum kutusunu temizle ve gizle
            self.commentLabel.setVisible(False)
            self.commentLabel.setText("")

            self.currently_viewing_excel = None
            self.raw_df_from_excel = None
            self.statusbar.clearMessage()
            self.update_connection_status()
            return
            
        try:
            files = [f for f in os.listdir(folder_path) if f.endswith('.xlsx')]
            # 'excel1, excel10, excel2' sorununu çözmek için doğal sıralama
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
        """Geçmişten Excel okumak için bir worker BAŞLATIR."""
        if not self.report_history_files: return
            
        try:
            folder_path = self.tarihSecCBox.currentData()
            file_name = self.report_history_files[self.current_report_index]
            full_path = os.path.join(folder_path, file_name)

            self.currently_viewing_excel = file_name 
            
            self.show_loading_dialog(f"{file_name} yükleniyor...")
            
            worker = Worker(load_excel_file, full_path) 
            worker.signals.finished.connect(self._on_excel_loaded) 
            worker.signals.error.connect(self._on_task_error)
            self.threadpool.start(worker)
            
            status_text = f"Gösterilen: {file_name} ({self.current_report_index + 1} / {len(self.report_history_files)})"
            self.statusbar.showMessage(status_text)
            self.update_connection_status() 
        
        except Exception as e:
            self._on_task_error(f"Excel yükleme başlatılamadı: {e}")
            self.currently_viewing_excel = None 
            self.raw_df_from_excel = None
            self.statusbar.clearMessage() 

    def _show_previous_report(self):
        """'Önceki' butonu."""
        if not self.report_history_files: return
        if self.current_report_index > 0:
            self.current_report_index -= 1
            self._load_excel_from_history()
            
    def _show_next_report(self):
        """'Sonraki' butonu."""
        if not self.report_history_files: return
        if self.current_report_index < len(self.report_history_files) - 1:
            self.current_report_index += 1
            self._load_excel_from_history()

    def _on_excel_loaded(self, loaded_raw_df):
            """(Callback) Excel'den ham veri gelince saklar, yorumları yükler ve seçili taslağı uygular."""
            self.close_loading_dialog()
            
            if loaded_raw_df is None or loaded_raw_df.empty:
                QMessageBox.warning(self, "Excel Boş", "Yüklenen Excel dosyasında veri bulunamadı.")
                self.raw_df_from_excel = None
                self.df = pd.DataFrame()
                self._populate_table(self.df)
                self.update_connection_status()
                self.statusbar.clearMessage()
                self.commentLabel.setVisible(False) 
                return

            # 1. Ham veriyi sakla
            self.raw_df_from_excel = loaded_raw_df.copy()
            print("Excel'den ham veri saklandı.")

            # 2. Yorumları Yükle ve Göster
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
                    self.commentLabel.setText("")
            else:
                self.commentLabel.setVisible(False) 
            
            # 3. O an seçili olan taslağı uygula
            self._apply_template_to_loaded_data()

            # 4. Durum çubuğunu son haliyle güncelle
            # --- HATA DÜZELTMESİ BURADA ---
            status_text = f"Gösterilen: {self.currently_viewing_excel} ({self.current_report_index + 1} / {len(self.report_history_files)})"
            # -----------------------------
            self.statusbar.showMessage(status_text)
        # --- Dışa Aktarma Fonksiyonları ---

    def export_excel(self):
        """Veriyi (self.df) Excel'e aktarır ve yorum sorar."""
        if self.df.empty: 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        # 1. Yorumu Sor
        # (getText yerine getMultiLineText kullanarak çok satırlı yorumlara izin verelim)
        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyonel):")
        if not ok:
            print("Excel'e aktarma iptal edildi.")
            return # Kullanıcı 'Cancel'a bastı

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()

        kayit_yolu = get_yeni_kayit_yolu("excel", start_date, end_date, self.target_table, current_template) 

        if not kayit_yolu: 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return 

        self.show_loading_dialog("Excel dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(task_run_excel, kayit_yolu, self.df.copy()) 

        # 2. Yorumu ve Kayıt Yolunu Callback'e Gönder
        # (functools.partial kullanarak)
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def export_pdf(self):
        """Veriyi (self.df) PDF'e aktarır ve yorum sorar."""
        if self.df.empty: 
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        # 1. Yorumu Sor
        comment, ok = QInputDialog.getMultiLineText(self, "Rapor Yorumu", 
                                                    "Rapor için bir yorum ekleyin (opsiyonel):")
        if not ok:
            print("PDF'e aktarma iptal edildi.")
            return 

        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        current_template = self.templateSecCBox.currentText()

        kayit_yolu = get_yeni_kayit_yolu("pdf", start_date, end_date, self.target_table, current_template) 

        if not kayit_yolu: 
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return

        self.show_loading_dialog("PDF dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(task_run_pdf, kayit_yolu, self.df.copy())

        # 2. Yorumu ve Kayıt Yolunu Callback'e Gönder
        worker.signals.finished.connect(
            functools.partial(self._on_export_finished, kayit_yolu=kayit_yolu, comment_to_save=comment)
        )
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_export_finished(self, kayit_yolu, comment_to_save):
        """
        (Callback) Excel/PDF kaydetme bittiğinde çalışır.
        'kayit_yolu' ve 'comment_to_save' parametreleri functools.partial ile gelir.
        """
        self.close_loading_dialog()
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")

        # --- YENİ ADIM 3: Yorumu Kaydet ---
        if comment_to_save and comment_to_save.strip():
            print(f"'{kayit_yolu}' için yorum kaydediliyor...")

            # Yeni metadata yöneticimizi çağırıyoruz
            # İleride 'user' kısmını dinamik hale getirebiliriz (örn: self.current_user)
            save_report_comment(file_path=kayit_yolu, 
                                comment=comment_to_save, 
                                user="Admin") # Şimdilik "Admin" diyelim
        else:
            print("Kaydedilecek yorum girilmedi.")
        # ---------------------------------

        # Kaydedilen dosya Excel ise, 'Kaydedilmiş Raporlar' listesini yenile
        if kayit_yolu and kayit_yolu.endswith(".xlsx"):
            self._load_saved_report_dates()
        
                
    # --- Günlük Özet Aracı Fonksiyonları ---
        
    def open_daily_summary_dialog(self):
        """'Günlük Özet Raporu' menüsüne tıklandığında çalışır."""
        source_cols = [] 
        
        if self.db_config and self.target_table:
            # Her zaman DB'den en güncel sütun listesini al
             self._fetch_columns_and_open_summary_dialog()
        else:
             QMessageBox.warning(self, "Bağlantı Gerekli", 
                                 "Günlük özet aracını kullanmak için lütfen önce bir veritabanına bağlanın.")
             return

    def _fetch_columns_and_open_summary_dialog(self):
        """(Yardımcı) Sütunları DB'den çeker ve Günlük Özet diyaloğunu açar."""
        self.show_loading_dialog("Kaynak sütunlar okunuyor...")
        worker = Worker(get_column_names_task, self.db_config, self.target_table)
        worker.signals.finished.connect(self._on_columns_loaded_for_summary_dialog) 
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_columns_loaded_for_summary_dialog(self, column_names):
        """(Callback) Sütun adları gelince Günlük Özet diyaloğunu açar."""
        self.close_loading_dialog()
        if column_names:
            print(f"Kaynak sütunlar veritabanından alındı: {column_names}")
            
            dialog = DailySummaryDialog(source_columns=column_names, parent=self)
            dialog.exec() 
            print("Günlük Özet Diyaloğu kapatıldı.")
        else:
            QMessageBox.warning(self, "Sütun Hatası", "Seçili tablonun sütun adları okunamadı.")

    def run_daily_summary_worker(self, settings, dialog_instance):
        """DailySummaryDialog tarafından çağrılır. Worker'ı başlatır."""
        
        start_date = settings["start_date"]
        end_date = settings["end_date"]
        date_column_name = settings["date_col"]
        
        worker = Worker(
            run_summary_task, # tasks.py'den
            self.db_config,
            self.target_table,
            start_date,
            end_date,
            date_column_name,
            settings 
        )
        
        worker.signals.finished.connect(
            functools.partial(self._on_summary_finished, dialog_instance)
        )
        worker.signals.error.connect(
            functools.partial(self._on_summary_error, dialog_instance)
        )
        self.threadpool.start(worker)

    def _on_summary_finished(self, dialog_instance, summary_df):
        """(Callback) Günlük özet işi bitince sonucu diyaloğa gönderir."""
        print("Ana arayüz: Günlük özet alındı. Diyaloğa gönderiliyor.")
        dialog_instance.update_summary_table(summary_df)

    def _on_summary_error(self, dialog_instance, error_message):
        """(Callback) Günlük özet işi hata verirse."""
        print(f"Ana arayüz: Günlük özet hatası: {error_message}")
        self.close_loading_dialog() 
        QMessageBox.critical(self, "Özetleme Hatası", f"İşlem sırasında bir hata oluştu:\n{error_message}")
        dialog_instance.update_summary_table(None) 
            
    # --- Genel Hata ve UI Fonksiyonları ---

    def _on_task_error(self, hata_mesaji):
        """(Callback) Herhangi bir Worker'da hata olursa çalışır."""
        self.close_loading_dialog()
        print(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}")
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        
        self.db_config = {}
        self.target_table = None
        self.target_date_column = None
        self.currently_viewing_excel = None
        self.raw_df_from_excel = None
        self.db_engine = None
        self.db_explorer.clear_tree()
        self.df = pd.DataFrame()
        self.update_connection_status()

    def update_connection_status(self):
        """Bağlantı durumunu (ışık), etiketleri ve butonların aktifliğini günceller."""
        
        is_connected = bool(self.db_config and self.target_table and self.target_date_column)
        
        label_parts = []
        style = ""
        tooltip = ""
        db_type = self.db_config.get('type', 'Yok')
        
        if is_connected:
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            tooltip_parts = ["BAĞLANDI"]

            label_parts.append(f"Sistem: {db_type.capitalize()}")
            tooltip_parts.append(f"Sistem: {db_type}")

            if db_type == 'access':
                db_name = os.path.basename(self.db_config.get('path', 'Bilinmiyor'))
                label_parts.append(f"Dosya: {db_name}")
                tooltip_parts.append(f"Dosya: {self.db_config.get('path', 'Bilinmiyor')}")
            else:
                db_name = self.db_config.get('database', 'Bilinmiyor')
                host_name = self.db_config.get('host', 'Bilinmiyor')
                label_parts.append(f"DB: {db_name} ({host_name})")
                tooltip_parts.append(f"Veritabanı: {db_name} (Sunucu: {host_name})")

            label_parts.append(f"Tablo: {self.target_table}")
            tooltip_parts.append(f"Tablo: {self.target_table}")
            label_parts.append(f"Tarih Sütunu: {self.target_date_column}")
            tooltip_parts.append(f"Tarih Sütunu: {self.target_date_column}")
            
            try: self.btn_Sorgula.setEnabled(True)
            except AttributeError: pass
            try: self.btn_ApplyTemplate.setEnabled(True)
            except AttributeError: pass
            
            self.date_Baslangic.setEnabled(True)
            self.date_Bitis.setEnabled(True)
        else:
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            label_parts.append(f"Bağlı Değil. (Seçili Sistem: {db_type.capitalize()})")
            tooltip_parts = ["BAĞLI DEĞİL", "Lütfen 'Veritabanı' menüsünden bağlantı kurun."]

            try: self.btn_Sorgula.setEnabled(False) 
            except AttributeError: pass
            try: self.btn_ApplyTemplate.setEnabled(False) 
            except AttributeError: pass
            
            self.date_Baslangic.setEnabled(False)
            self.date_Bitis.setEnabled(False)

        if self.currently_viewing_excel:
             label_parts.append(f"Görüntülenen Excel: {self.currently_viewing_excel}")
             tooltip_parts.append(f"Görüntülenen Excel: {self.currently_viewing_excel}")

        label_text = "  |  ".join(label_parts)
        tooltip = "\n".join(tooltip_parts)
        
        self.status_light.setStyleSheet(style)
        self.status_light.setToolTip(tooltip)
        
        try:
            self.veritabaniLabel.setText(label_text)
            self.veritabaniLabel.setToolTip(tooltip)
        except AttributeError:
            pass 
        
        if not self.df.empty:
            self.btn_Excel.setEnabled(True)
            self.btn_PDF.setEnabled(True)
        else:
             self.btn_Excel.setEnabled(False)
             self.btn_PDF.setEnabled(False)

    def _populate_table(self, df):
        """Verilen DataFrame'i tbl_Veri'ye doldurur."""
        
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
        
    def show_loading_dialog(self, text):
        """Kapatılamayan ilerleme penceresini oluşturur ve gösterir."""
        if not self.progress_dialog:
            self.progress_dialog = QProgressDialog(text, None, 0, 0, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setLabelText(text)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        QApplication.processEvents()
   
    def close_loading_dialog(self):
        """İlerleme penceresini kapatır."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

    def closeEvent(self, event: QCloseEvent):
        """Ana pencere 'X' ile kapatıldığında çalışır."""
        print("Kapanma sinyali alındı. Arka plan görevleri temizleniyor...")
        self.threadpool.clear()
        self.threadpool.waitForDone()
        print("Tüm görevler tamamlandı. Uygulama kapanıyor.")
        event.accept()

# --- Ana Uygulama Başlangıcı ---
if __name__ == '__main__':
    # Bu, main.py'den çalıştırıldığında hata verebilir,
    # ancak main.py'nin import etmesi için gereklidir.
    # Genellikle bu bloğu sadece main.py'de tutmak daha iyidir.
    pass