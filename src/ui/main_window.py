# src/ui/main_window.py

import sys
import os
import pandas as pd
import functools
from datetime import datetime
import logging  # <-- 1. logging'i import edin

from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal, Qt, QDate
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTableWidgetItem, QDialog,
    QMessageBox, QProgressDialog, 
    QFileDialog, QInputDialog, QLabel, QDockWidget
)
from PyQt6.QtGui import QCloseEvent, QPainter 
from PyQt6.uic import loadUi 

# --- Göreli UI Importları ---
from .dialogs import ConnectionDialog, TemplateEditorDialog, NewFileDialog
from .daily_summary_dialog import DailySummaryDialog
from .db_explorer_window import DbExplorerWindow
from .report_tab import ReportTabWidget
from .report_designer import ReportDesignerWidget
from .dynamic_table_tab import DynamicTableTab 

# --- Çekirdek (Core) ve Görev (Task) Importları ---
from src.core.database import create_db_engine, inspect 
from src.core.tasks import (
    get_column_names_task, run_summary_task,
    get_tables_task, fetch_full_schema_task
)
from src.core.utils import register_pdf_fonts
from src.threading.workers import Worker, WorkerSignals

# <-- 2. Modüle özel logger'ı tanımlayın
logger = logging.getLogger(__name__)

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
            logger.info("Ana pencere UI (arayuz.ui) başarıyla yüklendi.") # <-- LOG
        except Exception as e:
             # <-- LOG (Kritik)
             logger.critical(f"'arayuz.ui' yüklenemedi: {e}", exc_info=True)
             QMessageBox.critical(self, "UI Yükleme Hatası", f"'arayuz.ui' yüklenemedi: {e}")
             sys.exit()

        # --- Durum Değişkenleri (Sadece bağlantı) ---
        self.db_config = {}
        self.db_engine = None     
        self.full_schema_data = {} # Bağlı DB'nin tam şeması
        
        self.threadpool = QThreadPool()
        
        logger.info(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")
        
        self.progress_dialog = None
        self.status_light = QLabel()
        self.statusbar.addPermanentWidget(self.status_light)
        
        self._setup_docks()
        self._setup_file_menu()
        self._connect_signals()
        self._setup_profile_menu()

        self.logout_requested = False

        self.update_connection_status("Bağlı Değil", is_connected=False)
        self.mainTabWidget.tabCloseRequested.connect(self._close_tab)

    def _setup_profile_menu(self):
        """Profil menüsünü giriş yapan kullanıcıya göre düzenler."""
        from src.core.user_manager import get_current_user
        
        current_user = get_current_user()
        if not current_user:
            return

        self.menuProfil.setTitle(f"👤 {current_user.username}")
        
        self.menuProfil.clear()
        
        # 1. Profilim Aksiyonu
        action_profile = self.menuProfil.addAction("Profilim")
        action_profile.triggered.connect(self.open_profile_details)
        
        self.menuProfil.addSeparator()
        
        # 2. Çıkış Yap Aksiyonu
        action_logout = self.menuProfil.addAction("Çıkış Yap")
        action_logout.triggered.connect(self.logout_application)

    def open_profile_details(self):
        """Profil detay ekranını açar (İleride geliştirilecek)."""
        QMessageBox.information(self, "Profilim", "Profil detay ekranı yapım aşamasındadır.")

    def logout_application(self):
        """Çıkış yap bayrağını kaldırır ve pencereyi kapatır."""
        reply = QMessageBox.question(self, "Çıkış Yap", "Oturumu kapatmak istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Kullanıcı çıkış yapıyor...")
            self.logout_requested = True # Bayrağı kaldır
            self.close() # Pencereyi kapat (main.py döngüyü yakalayacak)

    def save_current_tab(self):
        """Aktif sekmedeki save_file fonksiyonunu tetikler."""
        current_widget = self.mainTabWidget.currentWidget()
        if hasattr(current_widget, "save_file"):
            current_widget.save_file()
        else:
            self.statusbar.showMessage("Bu sekme kaydedilebilir bir dosya değil.", 2000)

    def save_as_current_tab(self):
        """Aktif sekmedeki save_file_as fonksiyonunu tetikler."""
        current_widget = self.mainTabWidget.currentWidget()
        if hasattr(current_widget, "save_file_as"):
            current_widget.save_file_as()

    def open_saved_file(self):
        """Dosya açma diyaloğunu başlatır."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Dosya Aç",
            "",
            "AdminTableTool Dosyası (*.tuem);;JSON Dosyası (*.json);;Tüm Dosyalar (*.*)" # <-- GÜNCELLENDİ
        )
        
        if file_path:
            self.load_tuem_file(file_path)

    def load_tuem_file(self, file_path): 
        """Verilen yoldaki .tuem dosyasını yeni bir sekmede açar."""
        
        tab_name = os.path.basename(file_path).split('.')[0]
        
        # Yeni sekme oluştur
        new_tab = DynamicTableTab(self)
        
        # Sekmeyi ekle
        index = self.mainTabWidget.addTab(new_tab, tab_name)
        self.mainTabWidget.setCurrentIndex(index)
        
        # Dosyayı yükle
        new_tab.load_from_file(file_path)

    def _setup_docks(self):
        """Veritabanı Gezgini'ni (.py) bulur ve .ui'daki dock'a yerleştirir."""
        self.db_explorer = DbExplorerWindow(parent=None) 
        try:
            self.dbExplorerDock.setWidget(self.db_explorer)
        except AttributeError as e:
            
            logger.error(f"HATA: 'arayuz.ui' dosyasında 'dbExplorerDock' QDockWidget'ı bulunamadı. {e}", exc_info=True)
            self.dbExplorerDock = QDockWidget("Veritabanı Gezgini (Hata)", self)
            self.dbExplorerDock.setWidget(self.db_explorer)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dbExplorerDock)
            
        try:
            self.tools_dock = QDockWidget("Araç Kutusu", self)
            self.tools_dock.setObjectName("toolsDock")
            from .toolbox_widget import ToolboxWidget
            self.toolbox = ToolboxWidget(self) 
            self.tools_dock.setWidget(self.toolbox)
            self.tabifyDockWidget(self.dbExplorerDock, self.tools_dock)
            self.dbExplorerDock.raise_()
        except ImportError:
            
            logger.warning("UYARI: toolbox_widget.py bulunamadı.")
        except AttributeError as e:
            
             logger.error(f"HATA: Araç kutusu dock'u kurulamadı: {e}", exc_info=True)

    def _connect_signals(self):
        """Ana kabuğun sinyallerini bağlar."""
        logger.debug("MainWindow sinyalleri bağlanıyor...") # <-- LOG
        try:
            self.actionYeni_Dosya.triggered.connect(self.open_new_file_dialog)
        except AttributeError: pass
            
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
            self.actionMySQL.triggered.connect(
                functools.partial(self.set_database_type, "mysql")
            )
            self.actionVeritabani_Gezgini.triggered.connect(self.dbExplorerDock.toggleViewAction().trigger)
        except AttributeError: pass

        try:
            self.actionTaslak_Duzenle.triggered.connect(self.open_template_editor)
            self.actionGunluk_Ozet_Raporu.triggered.connect(self.open_daily_summary_dialog)
            if hasattr(self, 'tools_dock'): # tools_dock oluşturulduysa bağla
                self.actionArac_Kutusu.triggered.connect(self.tools_dock.toggleViewAction().trigger)
        except AttributeError: pass
             
        self.db_explorer.table_activated.connect(self.create_new_report_tab)
        logger.debug("MainWindow sinyalleri bağlandı.") # <-- LOG
        try:
            self.actionShow_Excel.triggered.connect(self.open_excel_archive_tab)
        except AttributeError:
            logger.warning("UYARI: 'actionShow_Excel' ui dosyasında bulunamadı.")

    def _close_tab(self, index):
        """Sekmeyi kapatmadan önce kaydedilmemiş değişiklik kontrolü yapar."""
        widget = self.mainTabWidget.widget(index)
        
        # --- YENİ: Kaydedilmemiş Değişiklik Kontrolü ---
        # Eğer widget'ın 'is_unsaved' özelliği varsa ve True ise uyar
        if hasattr(widget, "is_unsaved") and widget.is_unsaved:
            tab_name = self.mainTabWidget.tabText(index).replace("*", "") # Yıldızı temizle
            
            reply = QMessageBox.question(
                self, 
                "Kaydedilmemiş Değişiklikler", 
                f"'{tab_name}' dosyasında kaydedilmemiş değişiklikler var.\n\nKaydetmeden kapatmak istediğinize emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            # Eğer kullanıcı 'Hayır' derse (yani kapatmaktan vazgeçerse)
            if reply == QMessageBox.StandardButton.No:
                return 
        # -----------------------------------------------

        tab_name_log = self.mainTabWidget.tabText(index)
        if widget:
            widget.deleteLater()
        self.mainTabWidget.removeTab(index)
        logger.info(f"Sekme kapatıldı: '{tab_name_log}' (index {index})")

    # --- Sekme Oluşturma Fonksiyonları ---
    
    def open_new_file_dialog(self):
        """'Dosya > Yeni Dosya' tıklandığında çalışır."""
        logger.debug("'Yeni Dosya' menüsü tıklandı.") # <-- LOG
        if not self.db_config:
            logger.warning("Yeni dosya oluşturma denemesi, veritabanı bağlantısı yok.") # <-- LOG
            QMessageBox.warning(self, "Bağlantı Gerekli", 
                                "Yeni bir dosya oluşturmak için lütfen önce bir veritabanına bağlanın.")
            return

        dialog = NewFileDialog(self)
        if dialog.exec():
            file_type = dialog.get_selected_type()
            
            if file_type == "designer":
                new_tab = ReportDesignerWidget(self) 
                tab_name = f"Yeni Tasarım {self.mainTabWidget.count() + 1}"
                
            elif file_type == "table":
                new_tab = DynamicTableTab(self)
                tab_name = f"Yeni Veri Tablosu {self.mainTabWidget.count() + 1}"
            else:
                return 

            index = self.mainTabWidget.addTab(new_tab, tab_name)
            self.mainTabWidget.setCurrentIndex(index)
            logger.info(f"Yeni sekme eklendi: '{tab_name}' (Tip: {file_type})") # <-- LOG
        else:
            logger.info("Yeni dosya oluşturma iptal edildi.")

    def create_new_report_tab(self, table_name):
        """Veritabanı Gezgininden çift tıklama üzerine 'Eski' rapor sekmesini oluşturur."""
        logger.info(f"Veritabanı Gezgini'nden yeni rapor sekmesi oluşturma talebi: '{table_name}'") # <-- LOG
        
        if table_name not in self.full_schema_data:
             logger.warning(f"'{table_name}' için şema verisi bulunamadı, sekme oluşturulamadı.") # <-- LOG
             QMessageBox.warning(self, "Hata", f"'{table_name}' için şema verisi bulunamadı.")
             return
             
        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            if isinstance(tab, ReportTabWidget) and tab.target_table == table_name:
                self.mainTabWidget.setCurrentIndex(i)
                logger.debug(f"Mevcut sekme bulundu, '{table_name}' sekmesine geçildi.") # <-- LOG
                return 

        column_names = self.full_schema_data.get(table_name, [])
        date_col, ok = QInputDialog.getItem(
            self, "Tarih Sütununu Seç",
            f"'{table_name}' tablosu için tarih sütununu seçin:",
            column_names, 0, False
        )

        if not (ok and date_col):
            logger.info("Kullanıcı tarih sütunu seçimini iptal etti.") # <-- LOG
            return 

        new_report_tab = ReportTabWidget(
            main_window=self, 
            db_config=self.db_config,
            target_table=table_name,
            target_date_column=date_col,
            full_schema_data=self.full_schema_data
        )
        
        index = self.mainTabWidget.addTab(new_report_tab, table_name)
        self.mainTabWidget.setCurrentIndex(index)
        logger.info(f"Yeni 'ReportTabWidget' sekmesi oluşturuldu: '{table_name}' (Tarih Sütunu: {date_col})") # <-- LOG

    def open_excel_archive_tab(self):
        """
        Araçlar -> Excel Görüntüleyici.
        Veritabanı bağlantısı olmadan sadece kayıtlı raporları gezmek için bir sekme açar.
        """
        logger.info("Excel Arşiv Görüntüleyici açılıyor...")
        
        # Bağlantı yokmuş gibi 'offline' bir konfigürasyon oluşturuyoruz
        dummy_config = {
            'type': 'Arşiv Modu', 
            'database': 'Yerel Dosyalar', 
            'host': 'PC'
        }
        
        # Sekmeyi oluştur
        # target_table="Excel Arşivi" diyerek başlığı belirliyoruz
        archive_tab = ReportTabWidget(
            main_window=self,
            db_config=dummy_config,
            target_table="Kayıtlı Excel Arşivi",
            target_date_column="TARIH", # Varsayılan
            full_schema_data={} # Şema yok
        )
        
        # Sekmeyi ekle ve odaklan
        index = self.mainTabWidget.addTab(archive_tab, "📂 Excel Arşivi")
        self.mainTabWidget.setCurrentIndex(index)
        
        # Kullanıcıya bilgi ver
        self.statusbar.showMessage("Kayıtlı raporlar 'Kayıtlı Rapor Seç' kutusundan görüntülenebilir.", 5000)
    # --- Veritabanı Bağlantı Akışı ---

    def set_database_type(self, db_type):
        logger.info(f"Veritabanı türü '{db_type}' olarak ayarlandı.")
        self.db_config = {'type': db_type}
        self.full_schema_data = {}
        self.db_explorer.clear_tree()
        self.update_connection_status("Bağlantı bekleniyor...", is_connected=False)
        self.open_connection_settings()

    def open_connection_settings(self):
        selected_type = self.db_config.get('type')
        if not selected_type:
            logger.warning("Bağlantı ayarları açılmak istendi ancak DB türü seçilmemişti.") # <-- LOG
            QMessageBox.warning(self, "Tür Seçilmedi", 
                "Lütfen önce 'Veritabanı -> Veritabanı Sistemleri' menüsünden bir sistem türü seçin.")
            return

        dialog = ConnectionDialog(selected_type, self)
        
        if dialog.exec():
            self.db_config = dialog.get_config()
            self.full_schema_data = {}
            logger.info(f"Bağlantı ayarları kabul edildi ({self.db_config.get('type')}). Tablolar yükleniyor...") # <-- LOG
            self._load_tables_from_db()
        else:
            
            logger.info("Bağlantı ayarları iptal edildi.")
            self.db_config = {}
            self.db_explorer.clear_tree()
            self.update_connection_status("Bağlantı iptal edildi.", is_connected=False)

    def _load_tables_from_db(self):
        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")
        logger.info("Tablo listesi çekme worker'ı başlatılıyor...") # <-- LOG
        worker = Worker(get_tables_task, self.db_config) 
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_tables_loaded(self, results):
        self.close_loading_dialog()
        try:
            table_list, engine = results 
            logger.info(f"{len(table_list)} adet tablo başarıyla çekildi.") # <-- LOG
        except Exception as e:
            logger.error(f"Tablo yükleme sonucu işlenemedi: {results} - Hata: {e}", exc_info=True) # <-- LOG
            self._on_task_error(f"Tablo yükleme sonucu işlenemedi: {results} - Hata: {e}")
            return
            
        self.db_engine = engine 
        
        if not table_list:
            logger.warning("Veritabanında okunabilir bir tablo bulunamadı.") # <-- LOG
            QMessageBox.warning(self, "Hata", "Veritabanında okunabilir bir tablo bulunamadı.")
            self.db_config = {} 
            self.update_connection_status("Tablo bulunamadı.", is_connected=False)
            return
        
        self.show_loading_dialog(f"{len(table_list)} tablonun şeması okunuyor...")
        logger.info(f"{len(table_list)} tablonun tam şemasını çekme worker'ı başlatılıyor...") # <-- LOG
        
        worker = Worker(fetch_full_schema_task, self.db_config, self.db_engine, table_list)
        worker.signals.finished.connect(self._on_full_schema_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_full_schema_loaded(self, full_schema_data):
        self.close_loading_dialog()
        
        if not full_schema_data:
            logger.error("Veritabanı şeması okunamadı (boş döndü).") # <-- LOG
            self._on_task_error("Veritabanı şeması okunamadı.")
            return

        logger.info(f"Tam şema yüklendi. {len(full_schema_data)} tablo işlendi.")
        self.full_schema_data = full_schema_data
        
        try:
            self.db_explorer.populate_tree(self.db_config, self.full_schema_data)
        except Exception as e:
            
            logger.error(f"HATA: Veritabanı Gezgini doldurulamadı: {e}", exc_info=True)

        self.update_connection_status("Bağlandı. Gezginden bir tablo seçin.", is_connected=True)

    # --- Araç Pencerelerini Açma Fonksiyonları ---

    def open_template_editor(self):
        logger.debug("'Taslak Düzenleyici' açıldı.") # <-- LOG
        current_tab = self.mainTabWidget.currentWidget()
        source_cols = []
        if isinstance(current_tab, ReportTabWidget):
            source_cols = current_tab.full_schema_data.get(current_tab.target_table, [])
        elif self.full_schema_data:
             all_columns = set()
             for cols in self.full_schema_data.values():
                 all_columns.update(cols)
             source_cols = sorted(list(all_columns))
        else:
             logger.warning("Taslak düzenleyici açılmak istendi ancak veritabanı bağlantısı yok.") # <-- LOG
             QMessageBox.warning(self, "Bağlantı Gerekli", 
                                 "Taslak düzenleyiciyi açmak için lütfen önce bir veritabanına bağlanın.")
             return
                 
        self._show_template_editor_dialog(source_cols)

    def _show_template_editor_dialog(self, source_columns):
        dialog = TemplateEditorDialog(source_columns=source_columns, parent=self)
        result = dialog.exec() 

        if result == QDialog.DialogCode.Accepted: 
            template_data = dialog.get_template_data()
            
            logger.debug(f"Alınan Taslak Verisi: {template_data}")
            self._update_all_template_comboboxes()
        else:
            
            logger.info("Taslak Düzenleyici iptal edildi.")

    def _update_all_template_comboboxes(self):
        logger.info("Tüm açık sekmelerdeki taslak combobox'ları güncelleniyor...") # <-- LOG
        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            if isinstance(tab, ReportTabWidget):
                tab._load_available_templates()

    def open_daily_summary_dialog(self):
        logger.debug("'Günlük Özet Diyaloğu' açıldı.") # <-- LOG
        if not (self.db_config and self.full_schema_data):
            logger.warning("Günlük özet açılmak istendi ancak veritabanı bağlantısı yok.") # <-- LOG
            QMessageBox.warning(self, "Bağlantı Gerekli", "Lütfen önce bir veritabanına bağlanın.")
            return
            
        all_columns = set()
        for cols in self.full_schema_data.values():
            all_columns.update(cols)
            
        self._show_daily_summary_dialog(sorted(list(all_columns)))

    def _show_daily_summary_dialog(self, source_columns):
        dialog = DailySummaryDialog(source_columns=source_columns, parent=self)
        dialog.exec() 
        
        logger.info("Günlük Özet Diyaloğu kapatıldı.")

    # --- Günlük Özet Worker Çağrıları ---
    
    def run_daily_summary_worker(self, settings, dialog_instance):
        logger.info("Günlük özet worker'ı başlatılıyor...") # <-- LOG
        start_date = settings["start_date"]
        end_date = settings["end_date"]
        date_column_name = settings["date_col"]
        data_column_name = settings["data_col"]

        target_table_for_summary = None
        for table, cols in self.full_schema_data.items():
             if date_column_name in cols and data_column_name in cols:
                 target_table_for_summary = table
                 break
        
        if not target_table_for_summary:
             logger.warning(f"'{date_column_name}' ve '{data_column_name}' sütunlarını içeren tablo bulunamadı.") # <-- LOG
             QMessageBox.warning(self, "Hata", 
                                 f"'{date_column_name}' ve '{data_column_name}' sütunlarını aynı anda içeren bir tablo bulunamadı.")
             dialog_instance.update_summary_table(None)
             return
             
        logger.debug(f"Günlük özet için hedef tablo bulundu: {target_table_for_summary}") # <-- LOG
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
        
        logger.info("Ana arayüz: Günlük özet alındı. Diyaloğa gönderiliyor.")
        dialog_instance.update_summary_table(summary_df)

    def _on_summary_error(self, dialog_instance, error_message):
        
        logger.error(f"Ana arayüz: Günlük özet hatası: {error_message}")
        self.show_loading_dialog(f"Özetleme Hatası: {error_message}", 3000)
        dialog_instance.update_summary_table(None) 
            
    # --- Genel Hata ve UI Fonksiyonları ---

    def _on_task_error(self, hata_mesaji):
        """(Callback) Herhangi bir Worker'da hata olursa çalışır."""
        self.close_loading_dialog()
        
        logger.error(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}", exc_info=True)
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        
        # --- DÜZELTME: Her hatada bağlantıyı koparma! ---
        # Sadece veritabanı bağlantısı ile ilgili kritik hatalarda kopar.
        # Örneğin: "Connection refused", "Login failed", "Adaptive Server is unavailable" vb.
        
        kritik_hatalar = ["Connection refused", "Login failed", "SQL Server", "access denied", "Database error"]
        
        if any(hata in str(hata_mesaji) for hata in kritik_hatalar):
            logger.warning("Kritik veritabanı hatası algılandı. Bağlantı sıfırlanıyor.")
            self.db_config = {}
            self.db_engine = None
            self.full_schema_data = {}
            self.db_explorer.clear_tree()
            self.update_connection_status("Hata oluştu. Bağlantı kesildi.", is_connected=False)
        else:
            logger.info("Hata kritik değil, bağlantı korunuyor.")

    def update_connection_status(self, message, is_connected):
        """Bağlantı durumunu (ışık) ve etiketleri günceller."""
        
        style = ""
        tooltip = ""
        
        if is_connected:
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            tooltip = f"BAĞLANDI\n{message}"
            logger.debug(f"Bağlantı durumu: BAŞARILI ({message})") # <-- LOG
        else:
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            tooltip = f"BAĞLI DEĞİL\n{message}"
            logger.debug(f"Bağlantı durumu: BAĞLI DEĞİL ({message})") # <-- LOG
        
        self.statusbar.showMessage(message, 5000)
        self.status_light.setStyleSheet(style)
        self.status_light.setToolTip(tooltip)
        
    def show_loading_dialog(self, text, duration=0):
        """Kapatılamayan ilerleme penceresini oluşturur ve gösterir."""
        if duration > 0:
            self.statusbar.showMessage(text, duration)
            return
            
        logger.debug(f"Yükleme penceresi gösteriliyor: {text}") # <-- LOG
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
            logger.debug("Yükleme penceresi kapatılıyor.") # <-- LOG
            self.progress_dialog.close()
            self.progress_dialog = None

    def closeEvent(self, event: QCloseEvent):
        """Ana pencere 'X' ile kapatıldığında çalışır."""
        
        logger.info("Kapanma sinyali alındı. Arka plan görevleri temizleniyor...")
        self.threadpool.clear()
        self.threadpool.waitForDone()
        logger.info("Tüm görevler tamamlandı. Uygulama kapanıyor.") # <-- LOG
        event.accept()

    def _setup_file_menu(self):
        """Dosya menüsüne Kaydet, Farklı Kaydet ve Aç seçeneklerini ekler."""
        from PyQt6.QtGui import QAction, QKeySequence

        # Dosya Menüsünü Bul (ui dosyasından gelen)
        file_menu = self.menuDosya 
        
        # Ayırıcı ekle (Yeni Dosya'dan sonra)
        file_menu.addSeparator()

        # 1. Dosyayı Aç
        self.actionDosyayi_Ac = QAction("Dosyayı Aç...", self)
        self.actionDosyayi_Ac.setShortcut(QKeySequence("Ctrl+O"))
        self.actionDosyayi_Ac.triggered.connect(self.open_saved_file)
        file_menu.addAction(self.actionDosyayi_Ac)

        # 2. Kaydet
        self.actionKaydet = QAction("Kaydet", self)
        self.actionKaydet.setShortcut(QKeySequence("Ctrl+S"))
        self.actionKaydet.triggered.connect(self.save_current_tab)
        file_menu.addAction(self.actionKaydet)

        # 3. Farklı Kaydet
        self.actionFarkli_Kaydet = QAction("Farklı Kaydet...", self)
        self.actionFarkli_Kaydet.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.actionFarkli_Kaydet.triggered.connect(self.save_as_current_tab)
        file_menu.addAction(self.actionFarkli_Kaydet)

    def open_generated_excel_tab(self, file_path):
        """
        (YENİ) Oluşturulan Excel dosyasını yeni bir ReportTabWidget sekmesinde açar.
        """
        file_name = os.path.basename(file_path)
        logger.info(f"Yeni oluşturulan Excel için sekme açılıyor: {file_name}")

        # Yeni bir rapor sekmesi oluştur (Bağlantı olmasa bile açılabilmeli)
        # Dummy (sahte) verilerle başlatıyoruz çünkü sadece Excel gösterecek
        new_tab = ReportTabWidget(
            main_window=self,
            db_config=self.db_config if self.db_config else {'type': 'offline'},
            target_table="Excel Raporu",
            target_date_column="TARIH",
            full_schema_data={}
        )

        # Sekmeyi ekle
        index = self.mainTabWidget.addTab(new_tab, file_name)
        self.mainTabWidget.setCurrentIndex(index)

        # Dosyayı yüklemesini söyle
        new_tab.load_specific_file(file_path)
    
