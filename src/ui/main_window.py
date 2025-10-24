import sys
import os
import re
import traceback
from datetime import datetime
import functools

from src.core.database import get_database_tables # Bunu zaten import ediyor olmalısınız

from src.ui.dialogs import TemplateEditorDialog

from PyQt6.QtCore import QThreadPool, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidgetItem,
    QMessageBox, QProgressDialog, QFileDialog, QInputDialog, QLabel,QDialog
)
from PyQt6.uic import loadUi

from src.ui.dialogs import ConnectionDialog

import pandas as pd

from src.core.database import create_db_engine,inspect

from src.threading.workers import Worker, WorkerSignals
from src.core.database import get_database_tables, run_database_query, load_excel_file
from src.core.file_exporter import get_yeni_kayit_yolu, task_run_excel, task_run_pdf
from src.core.utils import register_pdf_fonts
from src.core.template_manager import get_available_templates

from src.core.data_processor import apply_template
from src.core.template_manager import load_template


# --- Doğal Sıralama ---
def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_file_path = os.path.join(current_dir, 'arayuz.ui')
        loadUi(ui_file_path, self)

        self.df = pd.DataFrame()
        self.rapor_ana_klasoru = r"C:\rapor\excel"
        self.secili_dosyalar_listesi = []
        self.secili_dosya_index = 0

        self.db_path = None
        self.target_table = None

        self.db_config = {}       
        self.db_engine = None     
        self.target_table = None  

        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")

        self.tbl_Veri.setSortingEnabled(True)
        self.progress_dialog = None

        self.status_light = QLabel()
        try:
            self.statusbar.addPermanentWidget(self.status_light)
        except Exception:
            pass
        
        try:
             self.actionTaslak_Duzenle.triggered.connect(self.open_template_editor)
        except AttributeError:
             print("UYARI: 'actionTaslak_Duzenle' menü eylemi .ui dosyasında bulunamadı.")

        try:
            self.btn_ApplyTemplate.clicked.connect(self.apply_selected_template) 
        except AttributeError:
            print("UYARI: 'btn_ApplyTemplate' butonu .ui dosyasında bulunamadı.")

        try:
            self.btn_Sorgula.clicked.connect(self.sorgulama_yap)
            self.btn_Excel.clicked.connect(self.export_excel)
            self.btn_PDF.clicked.connect(self.export_pdf)
            self.tarihSecCBox.currentIndexChanged.connect(self.combobox_degisti)
            self.ileriTarihButton.clicked.connect(self.sonraki_rapor)
            self.geriTarihButton.clicked.connect(self.onceki_rapor)
            self.actionVeritaban_n_Se.triggered.connect(self.open_connection_settings)

        except Exception as e:
            print(f"UI element missing: {e}")

        try:
            self.actionAccess_Database.triggered.connect(
                functools.partial(self.set_database_type, "access")
            )
            self.actionMicrosoft_SQL.triggered.connect(
                functools.partial(self.set_database_type, "sql")
            )
            self.actionPostgreSQL.triggered.connect(
                functools.partial(self.set_database_type, "postgres")
            )
            # ... (actionMySQL, actionOracle_Database vb. buraya eklenebilir) ...
        except AttributeError as e:
            print(f"HATA: 'arayuz.ui' dosyanızdaki menü eylemleri (actionAccess_Database vb.) kodla eşleşmiyor. {e}")


        self.update_connection_status()
        self.kayitli_raporlari_tara()
        self._load_available_templates()

    def apply_selected_template(self):
        """ 'Taslağı Uygula' butonuna basıldığında çalışır."""

        if not self.db_config or not self.target_table:
            QMessageBox.warning(self, "Bağlantı Yok", "Lütfen önce bir veritabanı ve tablo seçin.")
            return

        selected_template_name = self.templateSecCBox.currentText()
        selected_template_data = self.templateSecCBox.currentData() 

        is_raw_data_selected = (selected_template_data is None) 

        if not is_raw_data_selected and not selected_template_name:
            QMessageBox.warning(self, "Taslak Seçilmedi", "Lütfen 'Rapor Taslağı' listesinden bir taslak seçin.")
            return

        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")

        if is_raw_data_selected:
            self.show_loading_dialog("Ham veri getiriliyor...")
        else:
            self.show_loading_dialog(f"'{selected_template_name}' taslağı uygulanıyor...")

        worker = Worker(self._task_fetch_and_apply, 
                        self.db_config, 
                        self.target_table, 
                        baslangic, 
                        bitis, 
                        None if is_raw_data_selected else selected_template_name) 

        worker.signals.finished.connect(self._on_template_applied) 
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)


    def _on_template_applied(self, processed_df):
        """(Callback) Worker'dan gelen SONUCU (işlenmiş veya ham) tabloya yükler."""

        print("Ana arayüz: İşlenmiş veri alındı. Tablo dolduruluyor...")

        self.df = processed_df 

        self.tabloyu_doldur(self.df) 

        self.update_connection_status()

        self.close_loading_dialog() 
        print(f"Ana arayüz: İşlem tamamlandı ve sonuç tabloya yüklendi.")

    def _task_fetch_and_apply(self, config, target_table, start_date, end_date, template_name):
        """(Worker) Ham veriyi çeker, taslağı yükler ve uygular. (Hata ayıklama print'leri eklendi)"""
        
        print(f"\n--- Görev Başladı: _task_fetch_and_apply ---")
        print(f"Alınan Parametreler:")
        print(f"  config: {config}")
        print(f"  target_table: {target_table}")
        print(f"  start_date: {start_date}")
        print(f"  end_date: {end_date}")
        print(f"  template_name: {template_name}")
        
        try:
            print("Çalışan iş parçacığı: Ham veri çekiliyor...")
            raw_df = run_database_query(config, target_table, start_date, end_date)
            print(f"Çalışan iş parçacığı: Ham veri çekildi. Boyut: {raw_df.shape}")

            if not template_name:
                print("Çalışan iş parçacığı: Taslak adı yok, ham veri döndürülüyor.")
                print(f"--- Görev Bitti (Ham Veri): _task_fetch_and_apply ---\n")
                return raw_df 
                
            print(f"Çalışan iş parçacığı: '{template_name}' taslağı yükleniyor...")
            template_data = load_template(template_name=template_name) 
            
            if template_data:
                 print(f"Çalışan iş parçacığı: Taslak başarıyla yüklendi.")
            else:
                 print(f"Çalışan iş parçacığı: Taslak yüklenemedi!")

            if not template_data:
                raise FileNotFoundError(f"'{template_name}' taslak dosyası bulunamadı veya yüklenemedi.")
                
            print("Çalışan iş parçacığı: Taslak uygulanıyor (apply_template çağrılıyor)...")
            processed_df = apply_template(raw_df, template_data)
            print(f"Çalışan iş parçacığı: Taslak uygulandı. Sonuç Boyutu: {processed_df.shape}")


            print("Çalışan iş parçacığı: İşlem tamamlandı, işlenmiş veri döndürülüyor.")
            print(f"--- Görev Bitti (İşlenmiş Veri): _task_fetch_and_apply ---\n")
            return processed_df 

        except Exception as e:
             print(f"!!! HATA (_task_fetch_and_apply içinde): {e}")
             traceback.print_exc() # Detaylı hata bilgisini yazdır
             raise e

    def _load_available_templates(self):
        """ Kaydedilmiş taslakları tarar ve templateSecCBox'ı doldurur."""
        print("Kullanılabilir taslaklar yükleniyor...")
        self.templateSecCBox.blockSignals(True) 
        self.templateSecCBox.clear()
        
        self.templateSecCBox.addItem("Taslak Uygulama (Varsayılan: Ham Veri)", userData=None) 
        
        templates = get_available_templates()
        if templates:
            for template_name in templates:
                self.templateSecCBox.addItem(template_name, userData=template_name) 
            # ----------------------------------------------
            print(f"{len(templates)} adet taslak bulundu ve ComboBox'a eklendi.")
        else:
            print("Kaydedilmiş taslak bulunamadı.")
            
        self.templateSecCBox.blockSignals(False) 

    def open_template_editor(self):
        """Taslak Düzenleyici diyaloğunu açar."""
        
        source_cols = [] 
        
        if not self.df.empty:
            source_cols = list(self.df.columns)
            print(f"Kaynak sütunlar mevcut DataFrame'den alındı: {source_cols}")
            
            self._show_template_editor_dialog(source_cols)
            
        elif self.db_config and self.target_table:
            print("DataFrame boş, kaynak sütunlar veritabanından çekilecek...")
            self.show_loading_dialog("Kaynak sütunlar okunuyor...")
            
            worker = Worker(self._task_get_column_names, self.db_config, self.target_table)
            worker.signals.finished.connect(self._on_columns_loaded_for_editor) 
            worker.signals.error.connect(self._on_task_error) 
            self.threadpool.start(worker)
            
        else:
             QMessageBox.warning(self, "Bağlantı Gerekli", 
                                 "Taslak düzenleyiciyi açmak için lütfen önce bir veritabanına bağlanın.")
             return

    def _task_get_column_names(self, config, target_table):
        """(Worker) Sadece belirtilen tablonun sütun adlarını çeker."""
        print(f"Çalışan iş parçacığı: '{target_table}' tablosunun sütunları çekiliyor...")
        engine = create_db_engine(config) 
        inspector = inspect(engine) 
        
        schema_name = None
        table_only_name = target_table
        if config.get('type') != 'access' and '.' in target_table:
            schema_name, table_only_name = target_table.split('.', 1)
            
        columns_info = inspector.get_columns(table_only_name, schema=schema_name)
        column_names = [col['name'] for col in columns_info]
        
        print(f"Çalışan iş parçacığı: Sütunlar bulundu: {column_names}")
        return column_names


    def _on_columns_loaded_for_editor(self, column_names):
        """(Callback) Veritabanından sütun adları gelince Taslak Editörünü açar."""
        self.close_loading_dialog()
        if column_names:
            print(f"Kaynak sütunlar veritabanından alındı: {column_names}")
            self._show_template_editor_dialog(column_names)
        else:
            QMessageBox.warning(self, "Sütun Hatası", 
                                 "Seçili tablonun sütun adları okunamadı.")


    def _show_template_editor_dialog(self, source_columns):
        """TemplateEditorDialog'u verilen kaynak sütunlarla açar ve sonucu işler."""
        dialog = TemplateEditorDialog(source_columns=source_columns, parent=self)
        result = dialog.exec() 

        if result == QDialog.DialogCode.Accepted: 
            template_data = dialog.get_template_data()
            print("Alınan Taslak Verisi:", template_data)
            self._load_available_templates() 
            if template_data and template_data.get("template_name"):
                index = self.templateSecCBox.findText(template_data["template_name"])
                if index >= 0:
                    self.templateSecCBox.setCurrentIndex(index)
        else:
            print("Taslak Düzenleyici iptal edildi.")

    def update_connection_status(self):
        """Bağlantı durumunu (ışık), etiketleri ve butonların aktifliğini günceller."""
        
        is_connected = bool(self.db_config and self.target_table)
        
        label_text = ""
        style = ""
        tooltip = ""
        db_type = self.db_config.get('type', 'Yok')
        
        if is_connected:
            # 1. Işığı YEŞİL yap (Stil kodu tamamlandı)
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            
            # Etiket metnini güncelle
            label_text = f"Sistem: {db_type.capitalize()}  |  Tablo: {self.target_table}"
            tooltip = f"BAĞLANDI\nSistem: {db_type}\nTablo: {self.target_table}"
            
            self.btn_Sorgula.setEnabled(True)
            self.date_Baslangic.setEnabled(True)
            self.date_Bitis.setEnabled(True)
        else:
            # 1. Işığı KIRMIZI yap (Stil kodu tamamlandı)
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            
            # Etiket metnini güncelle
            label_text = f"Bağlı Değil. (Seçili Sistem: {db_type.capitalize()})"
            tooltip = "BAĞLI DEĞİL\nLütfen 'Veritabanı' menüsünden bağlantı kurun."

            self.btn_Sorgula.setEnabled(False)
            self.date_Baslangic.setEnabled(False)
            self.date_Bitis.setEnabled(False)
            self.btn_Excel.setEnabled(False)
            self.btn_PDF.setEnabled(False)
        
        # Işığı ve etiketi ayarla
        self.status_light.setStyleSheet(style)
        self.status_light.setToolTip(tooltip)
        
        try:
            self.veritabaniLabel.setText(label_text)
        except AttributeError:
            pass 
        
        if is_connected and not self.df.empty:
            self.btn_Excel.setEnabled(True)
            self.btn_PDF.setEnabled(True)

    def select_database_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Access Veritabanı Seç",
            "",
            "Access Dosyaları (*.mdb *.accdb);;Tüm Dosyalar (*.*)"
        )
        if file_path:
            self.db_path = file_path
            self.target_table = None
            self.load_tables_from_db()

    def load_tables_from_db(self):
        """Veritabanına bağlanıp tablo listesini çekmek için bir worker başlatır."""

        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")

        worker = Worker(get_database_tables, self.db_config) 
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)


    def _on_tables_loaded(self, results):
        """(Callback) Worker'dan gelen tablo listesini alır ve kullanıcıya sunar."""
        self.close_loading_dialog()

        try:
            table_list, engine = results 
        except Exception as e:
            print(f"Tablo yükleme sonucu işlenemedi: {e}")
            self._on_task_error(f"Tablo yükleme sonucu işlenemedi: {results}")
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
            print(f"Kullanıcı '{table_name}' tablosunu seçti.")
        else:
            self.db_config = {} 
            self.target_table = None
            print("Tablo seçimi iptal edildi.")

        self.update_connection_status()
        
    def show_loading_dialog(self, text):
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

    def sorgulama_yap(self):
        """1. Adım: 'Sorgula' butonu."""

        if not self.db_config or not self.target_table:
            QMessageBox.warning(self, "Hata", "Lütfen önce 'Veritabanı' menüsünden bir veritabanı ve tablo seçin.")
            return

        self.show_loading_dialog("Veritabanı sorgulanıyor... Lütfen bekleyin.")

        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")


        worker = Worker(run_database_query, self.db_config, self.target_table, baslangic, bitis) 

        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def excel_dosyasini_yukle(self):
        if not self.secili_dosyalar_listesi:
            return
        try:
            klasor_yolu = self.tarihSecCBox.currentData()
            dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
            tam_yol = os.path.join(klasor_yolu, dosya_adi)
            self.show_loading_dialog(f"{dosya_adi} yükleniyor... Lütfen bekleyin.")
            worker = Worker(load_excel_file, tam_yol)
            worker.signals.finished.connect(self._on_query_finished)
            worker.signals.error.connect(self._on_task_error)
            self.threadpool.start(worker)
        except Exception as e:
            self._on_task_error(f"Excel yükleme başlatılamadı: {e}")

    def combobox_degisti(self, index):
        klasor_yolu = self.tarihSecCBox.currentData()
        if not klasor_yolu:
            self.secili_dosyalar_listesi = []
            self.secili_dosya_index = 0
            return
        try:
            dosyalar = [f for f in os.listdir(klasor_yolu) if f.endswith('.xlsx')]
            self.secili_dosyalar_listesi = sorted(dosyalar, key=natural_sort_key)
            if not self.secili_dosyalar_listesi:
                return
            self.secili_dosya_index = 0
            self.excel_dosyasini_yukle()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Rapor klasörü okunurken hata:\n{e}")

    def sonraki_rapor(self):
        if not self.secili_dosyalar_listesi:
            return
        if self.secili_dosya_index < len(self.secili_dosyalar_listesi) - 1:
            self.secili_dosya_index += 1
            self.excel_dosyasini_yukle()

    def onceki_rapor(self):
        if not self.secili_dosyalar_listesi:
            return
        if self.secili_dosya_index > 0:
            self.secili_dosya_index -= 1
            self.excel_dosyasini_yukle()

    def tabloyu_doldur(self, df):
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

    def export_excel(self):
        if self.df.empty:
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return
        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        kayit_yolu = get_yeni_kayit_yolu("excel", start_date, end_date, self.target_table)
        if not kayit_yolu:
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return
        self.show_loading_dialog("Excel dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(task_run_excel, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def export_pdf(self):
        if self.df.empty:
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return
        start_date = self.date_Baslangic.date().toPyDate()
        end_date = self.date_Bitis.date().toPyDate()
        kayit_yolu = get_yeni_kayit_yolu("pdf", start_date, end_date, self.target_table)
        if not kayit_yolu:
            QMessageBox.critical(self, "Hata", "Kayıt yolu oluşturulamadı.")
            return
        self.show_loading_dialog("PDF dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(task_run_pdf, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_export_finished(self, kayit_yolu):
        self.close_loading_dialog()
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        if kayit_yolu.endswith('.xlsx'):
            self.kayitli_raporlari_tara()

    def _on_task_error(self, hata_mesaji):
        self.close_loading_dialog()
        print(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}")
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        self.db_config = {} 
        self.target_table = None
        self.db_engine = None
        self.df = pd.DataFrame()
        self.update_connection_status() 

    def kayitli_raporlari_tara(self):
            self.tarihSecCBox.blockSignals(True)
            self.tarihSecCBox.clear()
            rapor_klasorleri = {}
            if not os.path.exists(self.rapor_ana_klasoru):
                self.tarihSecCBox.blockSignals(False)
                return
            for yil_klasor in os.listdir(self.rapor_ana_klasoru):
                yil_yolu = os.path.join(self.rapor_ana_klasoru, yil_klasor)
                if os.path.isdir(yil_yolu) and yil_klasor.isdigit():
                    for gun_ay_klasor in os.listdir(yil_yolu):
                        # use yil_yolu here (was typo yil_klasoru)
                        gun_ay_yolu = os.path.join(yil_yolu, gun_ay_klasor)
                        if os.path.isdir(gun_ay_yolu) and '_' in gun_ay_klasor:
                            if any(f.endswith('.xlsx') for f in os.listdir(gun_ay_yolu)):
                                combo_text = f"{gun_ay_klasor}_{yil_klasor}"
                                rapor_klasorleri[combo_text] = gun_ay_yolu
            try:
                sorted_keys = sorted(rapor_klasorleri.keys(), key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
            except Exception:
                sorted_keys = sorted(rapor_klasorleri.keys())
            self.tarihSecCBox.addItem("Geçmiş Rapor Seçin...", userData=None)
            for key in sorted_keys:
                self.tarihSecCBox.addItem(key, userData=rapor_klasorleri[key])
            self.tarihSecCBox.blockSignals(False)
        # MainWindow sınıfının içine ekleyin

    def set_database_type(self, db_type):
        """
        Kullanıcı menüden bir veritabanı sistemi (Access, SQL...) seçtiğinde çalışır.
        """
        print(f"Veritabanı türü '{db_type}' olarak ayarlandı.")

        self.db_config = {'type': db_type}
        self.target_table = None
        self.df = pd.DataFrame()
        self.tabloyu_doldur(self.df)

        self.update_connection_status()

        self.statusbar.showMessage(f"Tür '{db_type}' seçildi. Lütfen 'Veritabanı -> Veritabanını Seç' menüsünden bağlantı kurun.", 5000)

        self.open_connection_settings()

    def open_connection_settings(self):
        """
        'Veritabanını Seç' menüsüne tıklandığında çalışır.
        Seçili türe göre dinamik bağlantı diyaloğunu açar.
        """
        selected_type = self.db_config.get('type')

        if not selected_type:
            QMessageBox.warning(self, "Tür Seçilmedi", 
                "Lütfen önce 'Veritabanı -> Veritabanı Sistemleri' menüsünden bir sistem türü (Access, SQL Server vb.) seçin.")
            return

        dialog = ConnectionDialog(selected_type, self)

        if dialog.exec():
            self.db_config = dialog.get_config() 
            print(f"Bağlantı ayarları alındı: {self.db_config}")
            self.target_table = None 

            
            self.load_tables_from_db()
        else:
            
            print("Bağlantı ayarları iptal edildi.")


# --- Ana Uygulama Başlangıcı ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    register_pdf_fonts()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())