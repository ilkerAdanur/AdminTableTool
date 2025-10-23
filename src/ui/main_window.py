import sys
import os
import re
import traceback
import urllib.parse
from datetime import datetime

from PyQt6.QtCore import QThreadPool, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidgetItem,
    QMessageBox, QProgressDialog, QFileDialog, QInputDialog, QLabel
)
from PyQt6.uic import loadUi

import pandas as pd

from src.threading.workers import Worker
from src.core.database import get_database_tables, run_database_query, load_excel_file
from src.core.file_exporter import get_yeni_kayit_yolu, task_run_excel, task_run_pdf
from src.core.utils import register_pdf_fonts

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

        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")

        self.tbl_Veri.setSortingEnabled(True)
        self.progress_dialog = None

        self.status_light = QLabel()
        try:
            self.statusbar.addPermanentWidget(self.status_light)
        except Exception:
            pass

        # Connect UI signals
        try:
            self.btn_Sorgula.clicked.connect(self.sorgulama_yap)
            self.btn_Excel.clicked.connect(self.export_excel)
            self.btn_PDF.clicked.connect(self.export_pdf)
            self.tarihSecCBox.currentIndexChanged.connect(self.combobox_degisti)
            self.ileriTarihButton.clicked.connect(self.sonraki_rapor)
            self.geriTarihButton.clicked.connect(self.onceki_rapor)
        except Exception as e:
            print(f"UI element missing: {e}")

        try:
            self.actionVeritaban_n_Se.triggered.connect(self.select_database_file)
        except Exception:
            pass

        self.update_connection_status()
        self.kayitli_raporlari_tara()

    def update_connection_status(self):
        is_connected = bool(self.db_path and self.target_table)
        label_text = ""
        style = ""
        tooltip = ""

        if is_connected:
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            db_filename = os.path.basename(self.db_path)
            label_text = f"Veritabanı: {db_filename}  |  Tablo: {self.target_table}"
            tooltip = f"BAĞLANDI\n{label_text}"
            try:
                self.btn_Sorgula.setEnabled(True)
                self.date_Baslangic.setEnabled(True)
                self.date_Bitis.setEnabled(True)
            except Exception:
                pass
        else:
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            label_text = "Bağlı Değil. Lütfen 'Veritabanı' menüsünden seçim yapın."
            tooltip = "BAĞLI DEĞİL\nLütfen 'Veritabanı' menüsünden bir veritabanı ve tablo seçin."
            try:
                self.btn_Sorgula.setEnabled(False)
                self.date_Baslangic.setEnabled(False)
                self.date_Bitis.setEnabled(False)
                self.btn_Excel.setEnabled(False)
                self.btn_PDF.setEnabled(False)
            except Exception:
                pass

        try:
            self.status_light.setStyleSheet(style)
            self.status_light.setToolTip(tooltip)
        except Exception:
            pass

        try:
            self.veritabaniLabel.setText(label_text)
        except Exception:
            pass

        if is_connected and not self.df.empty:
            try:
                self.btn_Excel.setEnabled(True)
                self.btn_PDF.setEnabled(True)
            except Exception:
                pass

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
        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")
        worker = Worker(get_database_tables, self.db_path)
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_tables_loaded(self, table_list):
        self.close_loading_dialog()
        if not table_list:
            QMessageBox.warning(self, "Hata", "Veritabanında okunabilir bir tablo bulunamadı.")
            self.db_path = None
            self.update_connection_status()
            return
        table_name, ok = QInputDialog.getItem(self, "Tablo Seç", "Lütfen sorgulanacak tabloyu seçin:", table_list, 0, False)
        if ok and table_name:
            self.target_table = table_name
        else:
            self.db_path = None
            self.target_table = None
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
        if not self.db_path or not self.target_table:
            QMessageBox.warning(self, "Hata", "Lütfen önce 'Veritabanı' menüsünden bir veritabanı ve tablo seçin.")
            return
        self.show_loading_dialog("Veritabanı sorgulanıyor... Lütfen bekleyin.")
        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")
        worker = Worker(run_database_query, self.db_path, self.target_table, baslangic, bitis)
        worker.signals.finished.connect(self._on_query_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _on_query_finished(self, df):
        self.df = df
        self.tabloyu_doldur(self.df)
        self.update_connection_status()
        try:
            if self.tarihSecCBox.currentData() and self.secili_dosyalar_listesi:
                dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
                self.statusbar.showMessage(f"Gösterilen: {dosya_adi} ({self.secili_dosya_index + 1} / {len(self.secili_dosyalar_listesi)})")
        except Exception:
            pass
        self.close_loading_dialog()

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
        self.db_path = None
        self.target_table = None
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

# --- Ana Uygulama Başlangıcı ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    register_pdf_fonts()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())