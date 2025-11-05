# src/ui/main_window.py

import sys
import os
import pandas as pd
import functools
from datetime import datetime

from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal, Qt, QDate
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTableWidgetItem, 
    QMessageBox, QProgressDialog, 
    QFileDialog, QInputDialog, QLabel, QDockWidget,QDialog
)
from PyQt6.QtGui import QCloseEvent, QPainter # QPainter eklendi (Gerekebilir)
from PyQt6.uic import loadUi 

# --- Göreli UI Importları ---
from .dialogs import ConnectionDialog, TemplateEditorDialog
from .daily_summary_dialog import DailySummaryDialog
from .db_explorer_window import DbExplorerWindow
from .report_tab import ReportTabWidget
from .report_designer import ReportDesignerWidget # <<< YENİ TASARIMCI SINIFI

# --- Çekirdek (Core) ve Görev (Task) Importları ---
from src.core.database import create_db_engine, inspect
from src.core.tasks import (
    get_column_names_task, run_summary_task,
    get_tables_task, fetch_full_schema_task
)
from src.core.utils import register_pdf_fonts
from src.threading.workers import Worker, WorkerSignals


class MainWindow(QMainWindow):
    """
    Ana 'Kabuk' (Shell) Penceresi.
    Sekmeleri, menüleri ve Veritabanı Gezgini'ni yönetir.
    """
    def __init__(self):
        super().__init__()
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file_path = os.path.join(current_dir, 'arayuz.ui')
            loadUi(ui_file_path, self) 
        except Exception as e:
             QMessageBox.critical(self, "UI Yükleme Hatası", f"'arayuz.ui' yüklenemedi: {e}")
             sys.exit()

        # --- Durum Değişkenleri ---
        self.db_config = {}
        self.db_engine = None     
        self.full_schema_data = {}
        
        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")
        
        self.progress_dialog = None
        self.status_light = QLabel()
        self.statusbar.addPermanentWidget(self.status_light)
        
        # --- Bileşenleri Oluştur ve Yerleştir ---
        self._setup_docks()
        self._connect_signals()

        # --- Başlangıç Ayarları ---
        self.update_connection_status("Bağlı Değil", is_connected=False)
        self.mainTabWidget.tabCloseRequested.connect(self._close_tab)

    def _setup_docks(self):
        """Veritabanı Gezgini'ni (.py) bulur ve .ui'daki dock'a yerleştirir."""
        
        # 1. Asıl Gezgin widget'ını EBEVEYNSİZ (parent=None) olarak oluştur
        self.db_explorer = DbExplorerWindow(parent=None) 
        
        # 2. .ui dosyasından 'dbExplorerDock' adlı QDockWidget'ı bul
        try:
            # self.dbExplorerDock, loadUi tarafından otomatik olarak oluşturulur.
            # İçeriğini (widget'ını) bizim 'db_explorer'ımızla değiştiriyoruz.
            self.dbExplorerDock.setWidget(self.db_explorer)
            
        except AttributeError as e:
            # Bu hata, 'arayuz.ui' dosyasında 'dbExplorerDock' adında
            # bir QDockWidget bulunamazsa meydana gelir.
            print(f"HATA: 'arayuz.ui' dosyasında 'dbExplorerDock' QDockWidget'ı bulunamadı. {e}")
            self.dbExplorerDock = QDockWidget("Veritabanı Gezgini (Hata)", self)
            self.dbExplorerDock.setWidget(self.db_explorer)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dbExplorerDock)

    def _connect_signals(self):
        """Ana kabuğun sinyallerini bağlar."""
        
        # Dosya Menüsü
        try:
            self.actionYeni_Dosya.triggered.connect(self.open_new_designer_tab)
        except AttributeError as e:
            print(f"UYARI: 'actionYeni_Dosya' menü eylemi bulunamadı. {e}")
            
        # Veritabanı Menüsü
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
            # Dock'un kendi "göster/gizle" eylemini menüye bağla
            self.actionVeritabani_Gezgini.triggered.connect(self.dbExplorerDock.toggleViewAction().trigger)
            
        except AttributeError as e:
            print(f"UYARI: Veritabanı menü eylemleri kodla eşleşmiyor. {e}")

        # Ayarlar & Araçlar Menüleri
        try:
            self.actionTaslak_Duzenle.triggered.connect(self.open_template_editor)
            self.actionGunluk_Ozet_Raporu.triggered.connect(self.open_daily_summary_dialog)
        except AttributeError as e:
             print(f"UYARI: Ayarlar/Araçlar menü eylemleri kodla eşleşmiyor. {e}")
             
        # Veritabanı Gezgini Sinyali (Çift Tıklama)
        self.db_explorer.table_activated.connect(self.create_new_report_tab)
    
    
    
    def _close_tab(self, index):
        """Bir sekme üzerindeki 'X' butonuna basıldığında çalışır."""
        widget = self.mainTabWidget.widget(index)
        if widget:
            widget.deleteLater()
        self.mainTabWidget.removeTab(index)

    # --- Sekme Oluşturma Fonksiyonları ---
    
    def open_new_designer_tab(self):
        """'Dosya > Yeni Dosya' tıklandığında yeni bir tasarımcı sekmesi açar."""
        if not self.db_config:
            QMessageBox.warning(self, "Bağlantı Gerekli", 
                                "Lütfen önce bir veritabanına bağlanın. Tasarımcı, sürükle-bırak için bu bağlantıyı kullanacaktır.")
            return
            
        print("Yeni 'Tasarımcı' sekmesi açılıyor...")
        
        new_designer_tab = ReportDesignerWidget(self) 
        
        tab_index = self.mainTabWidget.addTab(new_designer_tab, "Yeni Tasarım 1")
        self.mainTabWidget.setCurrentIndex(tab_index)
    
    def create_new_report_tab(self, table_name):
        """
        Veritabanı Gezgininden çift tıklama üzerine yeni bir veri raporu sekmesi oluşturur.
        """
        if table_name not in self.full_schema_data:
             QMessageBox.warning(self, "Hata", f"'{table_name}' için şema verisi bulunamadı.")
             return
             
        # Zaten açık olan bir sekme var mı?
        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            if isinstance(tab, ReportTabWidget) and tab.target_table == table_name:
                self.mainTabWidget.setCurrentIndex(i)
                return # Varsa o sekmeye geç, yenisini açma

        column_names = self.full_schema_data.get(table_name, [])
        date_col, ok = QInputDialog.getItem(
            self, "Tarih Sütununu Seç",
            f"'{table_name}' tablosu için tarih sütununu seçin:",
            column_names, 0, False
        )

        if not (ok and date_col):
            return 

        new_report_tab = ReportTabWidget(
            main_window=self, 
            target_table=table_name,
            target_date_column=date_col
        )
        
        index = self.mainTabWidget.addTab(new_report_tab, table_name)
        self.mainTabWidget.setCurrentIndex(index)

    # --- Veritabanı Bağlantı Akışı (Ana Pencere Yönetir) ---

    def set_database_type(self, db_type):
        print(f"Veritabanı türü '{db_type}' olarak ayarlandı.")
        self.db_config = {'type': db_type}
        self.full_schema_data = {}
        self.db_explorer.clear_tree()
        self.update_connection_status("Bağlantı bekleniyor...", is_connected=False)
        self.open_connection_settings()

    def open_connection_settings(self):
        selected_type = self.db_config.get('type')
        if not selected_type:
            QMessageBox.warning(self, "Tür Seçilmedi", 
                "Lütfen önce 'Veritabanı -> Veritabanı Sistemleri' menüsünden bir sistem türü seçin.")
            return

        dialog = ConnectionDialog(selected_type, self)
        
        if dialog.exec():
            self.db_config = dialog.get_config()
            self.full_schema_data = {}
            self._load_tables_from_db()
        else:
            print("Bağlantı ayarları iptal edildi.")
            self.db_config = {}
            self.db_explorer.clear_tree()
            self.update_connection_status("Bağlantı iptal edildi.", is_connected=False)

    def _load_tables_from_db(self):
        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")
        worker = Worker(get_tables_task, self.db_config) 
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_tables_loaded(self, results):
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
            self.update_connection_status("Tablo bulunamadı.", is_connected=False)
            return
        
        self.show_loading_dialog(f"{len(table_list)} tablonun şeması okunuyor...")
        
        worker = Worker(fetch_full_schema_task, self.db_config, self.db_engine, table_list)
        worker.signals.finished.connect(self._on_full_schema_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_full_schema_loaded(self, full_schema_data):
        self.close_loading_dialog()
        
        if not full_schema_data:
            self._on_task_error("Veritabanı şeması okunamadı.")
            return

        print(f"Tam şema yüklendi. {len(full_schema_data)} tablo işlendi.")
        self.full_schema_data = full_schema_data
        
        try:
            self.db_explorer.populate_tree(self.db_config, self.full_schema_data)
        except Exception as e:
            print(f"HATA: Veritabanı Gezgini doldurulamadı: {e}")

        self.update_connection_status("Bağlandı. Gezginden bir tablo seçin.", is_connected=True)

    # --- Araç Pencerelerini Açma Fonksiyonları ---

    def open_template_editor(self):
        current_tab = self.mainTabWidget.currentWidget()
        source_cols = []
        if isinstance(current_tab, ReportTabWidget):
            # Aktif sekmenin kaynak sütunlarını al
            source_cols = current_tab.full_schema_data.get(current_tab.target_table, [])
        elif self.full_schema_data:
             # Aktif sekme yoksa, son bağlanan DB'deki tüm sütunları topla
             all_columns = set()
             for cols in self.full_schema_data.values():
                 all_columns.update(cols)
             source_cols = sorted(list(all_columns))
        else:
             QMessageBox.warning(self, "Bağlantı Gerekli", 
                                 "Taslak düzenleyiciyi açmak için lütfen önce bir veritabanına bağlanın.")
             return
                 
        self._show_template_editor_dialog(source_cols)

    def _show_template_editor_dialog(self, source_columns):
        dialog = TemplateEditorDialog(source_columns=source_columns, parent=self)
        result = dialog.exec() 

        if result == QDialog.DialogCode.Accepted: 
            template_data = dialog.get_template_data()
            print("Alınan Taslak Verisi:", template_data)
            self._update_all_template_comboboxes()
        else:
            print("Taslak Düzenleyici iptal edildi.")

    def _update_all_template_comboboxes(self):
        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            if isinstance(tab, ReportTabWidget):
                tab._load_available_templates()

    def open_daily_summary_dialog(self):
        if not (self.db_config and self.full_schema_data):
            QMessageBox.warning(self, "Bağlantı Gerekli", "Lütfen önce bir veritabanına bağlanın.")
            return
            
        all_columns = set()
        for cols in self.full_schema_data.values():
            all_columns.update(cols)
            
        self._show_daily_summary_dialog(sorted(list(all_columns)))

    def _show_daily_summary_dialog(self, source_columns):
        dialog = DailySummaryDialog(source_columns=source_columns, parent=self)
        dialog.exec() 
        print("Günlük Özet Diyaloğu kapatıldı.")

    # --- Günlük Özet Worker Çağrıları ---
    
    def run_daily_summary_worker(self, settings, dialog_instance):
        start_date = settings["start_date"]
        end_date = settings["end_date"]
        date_column_name = settings["date_col"]
        data_column_name = settings["data_col"]

        # TODO: Hangi tablonun kullanılacağını bulmamız lazım.
        # Şimdilik, o sütunu içeren ilk tabloyu bul (basit varsayım)
        target_table_for_summary = None
        for table, cols in self.full_schema_data.items():
             if date_column_name in cols and data_column_name in cols:
                 target_table_for_summary = table
                 break
        
        if not target_table_for_summary:
             QMessageBox.warning(self, "Hata", 
                                 f"'{date_column_name}' ve '{data_column_name}' sütunlarını aynı anda içeren bir tablo bulunamadı.")
             dialog_instance.update_summary_table(None)
             return
             
        worker = Worker(
            run_summary_task,
            self.db_config,
            target_table_for_summary,
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
        print("Ana arayüz: Günlük özet alındı. Diyaloğa gönderiliyor.")
        dialog_instance.update_summary_table(summary_df)

    def _on_summary_error(self, dialog_instance, error_message):
        print(f"Ana arayüz: Günlük özet hatası: {error_message}")
        self.show_loading_dialog(f"Özetleme Hatası: {error_message}", 3000)
        dialog_instance.update_summary_table(None) 
            
    # --- Genel Hata ve UI Fonksiyonları ---

    def _on_task_error(self, hata_mesaji):
        """(Callback) Herhangi bir Worker'da hata olursa çalışır."""
        self.close_loading_dialog()
        print(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}")
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        
        self.db_config = {}
        self.db_engine = None
        self.full_schema_data = {}
        self.db_explorer.clear_tree()
        self.update_connection_status("Hata oluştu. Bağlantı kesildi.", is_connected=False)

    def update_connection_status(self, message, is_connected):
        """Bağlantı durumunu (ışık) ve etiketleri günceller."""
        
        style = ""
        tooltip = ""
        
        if is_connected:
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            tooltip = f"BAĞLANDI\n{message}"
        else:
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            tooltip = f"BAĞLI DEĞİL\n{message}"
        
        self.statusbar.showMessage(message, 5000)
        self.status_light.setStyleSheet(style)
        self.status_light.setToolTip(tooltip)
        
    def show_loading_dialog(self, text, duration=0):
        """Kapatılamayan ilerleme penceresini oluşturur ve gösterir."""
        if duration > 0:
            self.statusbar.showMessage(text, duration)
            return
            
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