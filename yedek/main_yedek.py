import sys
import urllib.parse
import os
import re
import traceback 
from datetime import datetime

# --- GÜNCELLENMİŞ IMPORTLAR ---
from PyQt6.QtCore import (
    QRunnable, QThreadPool, QObject, pyqtSignal, Qt
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTableWidgetItem, 
    QMessageBox, QProgressDialog, 
    QFileDialog, # Dosya seçme penceresi için eklendi
    QInputDialog, # Tablo seçme penceresi için eklendi
    QLabel        # Bağlantı ışığı (lamba) için eklendi
)
from PyQt6.uic import loadUi 

import pandas as pd
# --- YENİ IMPORT: Veritabanı yapıSını incelemek için 'inspect' eklendi ---
from sqlalchemy import create_engine, inspect
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- GEREKLİ KÜTÜPHANE KONTROLÜ (python-calamine) ---
try:
    import python_calamine
    EXCEL_ENGINE = "calamine"
    print("Hızlı Excel motoru (python-calamine) bulundu.")
except ImportError:
    EXCEL_ENGINE = "openpyxl" # Calamine yoksa varsayılana dön
    print("UYARI: 'python-calamine' kütüphanesi bulunamadı. pip install python-calamine")
    print("Hızlı Excel okuma için varsayılan (yavaş) motor 'openpyxl' kullanılacak.")


# --- PDF Font Ayarı (Değişiklik yok) ---
def register_pdf_fonts():
    try:
        pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial_Bold', r'C:\Windows\Fonts\arialbd.ttf'))
        print("PDF fontları (Arial) başarıyla yüklendi.")
    except Exception as e:
        print(f"UYARI: PDF fontları yüklenemedi. Hata: {e}")
        pdfmetrics.registerFont(TTFont('Arial', 'Helvetica'))
        pdfmetrics.registerFont(TTFont('Arial_Bold', 'Helvetica-Bold'))

# --- Doğal Sıralama (Değişiklik yok) ---
def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]

# --- Worker Sınıfları (Değişiklik yok) ---
class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            print(f"Worker hatası: {e}")
            traceback.print_exc()
            self.signals.error.emit(str(e))
        else:
            self.signals.finished.emit(result)

# -------------------------------------------------------------------
# --- GÜNCELLENMİŞ MainWindow Sınıfı ---
# -------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        loadUi('arayuz.ui', self) 
        
        # --- GÜNCELLENMİŞ Sınıf Değişkenleri ---
        self.df = pd.DataFrame()
        self.rapor_ana_klasoru = r"C:\rapor\excel"
        self.secili_dosyalar_listesi = []
        self.secili_dosya_index = 0
        
        # --- YENİ: Veritabanı Durum Değişkenleri ---
        self.db_path = None       # Kullanıcının seçtiği .mdb dosyasının yolu
        self.target_table = None  # Kullanıcının seçtiği tablo adı (örn: "DEBILER")
        
        # --- Thread Pool (Değişiklik yok) ---
        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")

        # --- Tablo Sıralama (Değişiklik yok) ---
        self.tbl_Veri.setSortingEnabled(True)

        # --- İlerleme Penceresi (Değişiklik yok) ---
        self.progress_dialog = None

        # --- YENİ: Bağlantı Durum Işığı ---
        # 1. Bir QLabel widget'ı (lamba) oluşturuyoruz
        self.status_light = QLabel()
        # 2. Bu lambayı programatik olarak sağ alta (statusbar) kalıcı olarak ekliyoruz.
        self.statusbar.addPermanentWidget(self.status_light)
        # addPermanentWidget, ışığın her zaman en sağda kalmasını sağlar.

        # --- GÜNCELLENMİŞ Buton Bağlantıları ---
        self.btn_Sorgula.clicked.connect(self.sorgulama_yap)
        self.btn_Excel.clicked.connect(self.export_excel)
        self.btn_PDF.clicked.connect(self.export_pdf)
        self.tarihSecCBox.currentIndexChanged.connect(self.combobox_degisti)
        self.ileriTarihButton.clicked.connect(self.sonraki_rapor)
        self.geriTarihButton.clicked.connect(self.onceki_rapor)

        # --- YENİ: Menü Çubuğu Bağlantıları ---
        # .ui dosyasındaki 'actionVeritaban_n_Se' eylemini 'select_database_file' fonksiyonuna bağlıyoruz.
        try:
            self.actionVeritaban_n_Se.triggered.connect(self.select_database_file)
        except AttributeError as e:
            print(f"HATA: 'arayuz.ui' dosyanızda 'actionVeritaban_n_Se' adında bir QAction bulunamadı. {e}")

        # --- GÜNCELLENMİŞ Başlangıç Ayarları ---
        # Başlangıçta bağlantı olmadığı için tüm işlemleri kilitliyoruz.
        self.update_connection_status() # Işığı kırmızı yap ve butonları kilitle
        self.kayitli_raporlari_tara()

    # -------------------------------------------------------------------
    # --- YENİ FONKSİYONLAR (Veritabanı Seçimi ve Durum Işığı) ---
    # -------------------------------------------------------------------

    def update_connection_status(self):
        """Bağlantı durumunu (ışık), etiketleri ve butonların aktifliğini günceller."""
        
        # Bağlantı var mı? (Hem dosya yolu hem de tablo adı seçilmiş mi?)
        is_connected = bool(self.db_path and self.target_table)
        
        label_text = ""
        style = ""
        tooltip = ""
        
        if is_connected:
            # 1. Işığı YEŞİL yap
            style = "background-color: #4CAF50; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            
            # --- YENİ ETİKET MANTIĞI ---
            # Tam yolu (C:\...) göstermek yerine sadece dosya adını al
            db_filename = os.path.basename(self.db_path) 
            label_text = f"Veritabanı: {db_filename}  |  Tablo: {self.target_table}"
            tooltip = f"BAĞLANDI\n{label_text}"
            
            # 2. İşlem butonlarını aç
            self.btn_Sorgula.setEnabled(True)
            self.date_Baslangic.setEnabled(True)
            self.date_Bitis.setEnabled(True)
        else:
            # 1. Işığı KIRMIZI yap
            style = "background-color: #F44336; border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;"
            
            # --- YENİ ETİKET MANTIĞI ---
            label_text = "Bağlı Değil. Lütfen 'Veritabanı' menüsünden seçim yapın."
            tooltip = "BAĞLI DEĞİL\nLütfen 'Veritabanı' menüsünden bir veritabanı ve tablo seçin."

            # 2. İşlem butonlarını kilitle
            self.btn_Sorgula.setEnabled(False)
            self.date_Baslangic.setEnabled(False)
            self.date_Bitis.setEnabled(False)
            self.btn_Excel.setEnabled(False)
            self.btn_PDF.setEnabled(False)
        
        self.status_light.setStyleSheet(style)
        self.status_light.setToolTip(tooltip)
        
        # --- YENİ ETİKET GÜNCELLEMESİ ---
        # .ui dosyanıza 'veritabaniLabel' ekleyip eklemediğinizi kontrol et
        try:
            self.veritabaniLabel.setText(label_text)
        except AttributeError:
            # Eğer .ui dosyasında bu isimde bir label yoksa hata vermeden devam et
            print("Bilgi: 'veritabaniLabel' adında bir widget bulunamadı.")
        except Exception as e:
            print(f"veritabaniLabel ayarlanırken hata: {e}")
        
        # Excel/PDF butonları SADECE sorgu yapıldıktan sonra (self.df doluysa) açılmalı
        if is_connected and not self.df.empty:
            self.btn_Excel.setEnabled(True)
            self.btn_PDF.setEnabled(True)


    def select_database_file(self):
        """'Veritabanını Seç' menüsüne tıklandığında çalışır. Dosya seçim penceresini açar."""
        
        # Dosya seçim penceresini aç (Sadece Access dosyalarını göster)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Access Veritabanı Seç",
            "", # Varsayılan dizin (boş)
            "Access Dosyaları (*.mdb *.accdb);;Tüm Dosyalar (*.*)"
        )
        
        if file_path:
            # Kullanıcı bir dosya seçti
            print(f"Veritabanı dosyası seçildi: {file_path}")
            self.db_path = file_path
            self.target_table = None # Yeni DB seçildi, tabloyu sıfırla
            # Şimdi bu veritabanındaki tabloları kullanıcıya sormamız lazım
            self.load_tables_from_db()
        else:
            # Kullanıcı iptal'e bastı
            print("Veritabanı seçimi iptal edildi.")

    def load_tables_from_db(self):
        """Veritabanına bağlanıp tablo listesini çekmek için bir worker başlatır."""
        
        self.show_loading_dialog("Veritabanına bağlanılıyor ve tablolar okunuyor...")
        
        worker = Worker(self._task_get_db_tables, self.db_path)
        worker.signals.finished.connect(self._on_tables_loaded)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _task_get_db_tables(self, db_path):
        """(Worker) Veritabanına bağlanır ve tablo isimlerinin listesini döndürür."""
        print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {db_path}")
        
        connection_string = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"Dbq={db_path};"
        )
        quoted_connection_string = urllib.parse.quote_plus(connection_string)
        engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
        
        # SQLAlchemy'nin 'inspect' özelliğini kullanarak tablo listesini al
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        # Access'in sistem tablolarını ("MSys...") filtrele
        user_tables = [name for name in table_names if not name.startswith("MSys")]
        
        print(f"Çalışan iş parçacığı: Bulunan tablolar: {user_tables}")
        return user_tables

    def _on_tables_loaded(self, table_list):
        """(Callback) Worker'dan gelen tablo listesini alır ve kullanıcıya sunar."""
        self.close_loading_dialog()
        
        if not table_list:
            QMessageBox.warning(self, "Hata", "Veritabanında okunabilir bir tablo bulunamadı.")
            self.db_path = None # Bağlantıyı başarısız say
            self.update_connection_status()
            return
            
        # Kullanıcıya QInputDialog ile bir seçim yaptır
        table_name, ok = QInputDialog.getItem(
            self,
            "Tablo Seç",
            "Lütfen sorgulanacak tabloyu seçin:",
            table_list, # Seçenekler
            0,          # Varsayılan (ilk tablo)
            False       # Düzenlenemez
        )
        
        if ok and table_name:
            # Kullanıcı bir tablo seçti ve 'Tamam'a bastı
            self.target_table = table_name
            print(f"Kullanıcı '{table_name}' tablosunu seçti.")
        else:
            # Kullanıcı 'İptal'e bastı
            self.db_path = None # Bağlantıyı başarısız say
            self.target_table = None
            print("Tablo seçimi iptal edildi.")
            
        # Durum ışığını (yeşil veya kırmızı) ve butonları güncelle
        self.update_connection_status()

    # -------------------------------------------------------------------
    # --- MEVCUT FONKSİYONLARIN GÜNCELLENMESİ ---
    # -------------------------------------------------------------------

    # --- İlerleme Penceresi (Hatalı satır yorumda) ---
    def show_loading_dialog(self, text):
        if not self.progress_dialog:
            self.progress_dialog = QProgressDialog(text, None, 0, 0, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setCancelButton(None)
            # self.progress_dialog.setWindowFlag(Qt.WindowCloseButtonHint, False) # Hata veren satır
            self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setLabelText(text)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        QApplication.processEvents()
   
    def close_loading_dialog(self):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
    # --- GÜNCELLENDİ: SORGULAMA ---
    def sorgulama_yap(self):
        """1. Adım: 'Sorgula' butonu. Artık 'self.db_path' ve 'self.target_table' kullanıyor."""
        
        # Bağlantı yoksa (ekstra güvenlik, normalde buton kilitli olmalı)
        if not self.db_path or not self.target_table:
            QMessageBox.warning(self, "Hata", "Lütfen önce 'Veritabanı' menüsünden bir veritabanı ve tablo seçin.")
            return

        self.show_loading_dialog("Veritabanı sorgulanıyor... Lütfen bekleyin.")
        
        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")
        
        # Worker'ı, Sınıf değişkenlerindeki (self.) değerlerle başlat
        worker = Worker(self._task_run_query, baslangic, bitis, self.db_path, self.target_table) 
        
        worker.signals.finished.connect(self._on_query_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    # --- GÜNCELLENDİ: ARKA PLAN SORGUSU ---
    def _task_run_query(self, baslangic_tarihi, bitis_tarihi, db_path, target_table):
        """2. Adım: (Worker) Artık parametre olarak gelen db_path ve target_table'ı kullanıyor."""
        
        print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}, Tarih: {baslangic_tarihi} - {bitis_tarihi}")
        
        # --- SABİT YOL KALDIRILDI ---
        # db_path = r"C:\Users\User\..." (KALDIRILDI)
        connection_string = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"Dbq={db_path};" # GÜNCELLENDİ
        )
        quoted_connection_string = urllib.parse.quote_plus(connection_string)
        engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
        
        # --- SABİT TABLO ADI KALDIRILDI ---
        # sql_query = "SELECT * FROM [DEBILER] ..." (KALDIRILDI)
        # Sütun adının [TARIH] olduğunu varsaymaya devam ediyoruz.
        # Bu da ilerde dinamik hale getirilebilir.
        sql_query = f"SELECT * FROM [{target_table}] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]" # GÜNCELLENDİ
        
        df = pd.read_sql(sql_query, engine, params=(baslangic_tarihi, bitis_tarihi))
        
        print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
        return df

    # --- YENİ GÖREV: EXCEL OKUMA (Calamine ile) ---
    def _task_run_excel_load(self, tam_yol):
        """(Worker) Excel okuma işi (Calamine motoruyla)"""
        print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
        df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
        print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
        return df

    # --- SORGULAMA/EXCEL YÜKLEME SONUCU ---
    def _on_query_finished(self, df):
        """3. Adım: (Callback) Gelen veriyi (DB veya Excel) işler."""
        print("Ana arayüz: Veri alındı. Tablo dolduruluyor...")
        
        self.df = df 
        
        # Ağır tablo doldurma işi
        self.tabloyu_doldur(self.df) 
        
        # Bağlantı durumunu ve butonları güncelle (Excel/PDF butonlarını açar)
        self.update_connection_status()

        # Excel'den yüklendiyse durum çubuğunu güncelle
        try:
            if self.tarihSecCBox.currentData() and self.secili_dosyalar_listesi:
                dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
                self.statusbar.showMessage(f"Gösterilen: {dosya_adi} ({self.secili_dosya_index + 1} / {len(self.secili_dosyalar_listesi)})")
        except Exception as e:
            pass 

        # Ağır iş bittikten sonra pencereyi kapat
        self.close_loading_dialog() 
        print(f"Ana arayüz: İşlem tamamlandı ve sonuç tabloya yüklendi.")

    # --- EXCEL YÜKLEME BAŞLANGIÇ ---

    def excel_dosyasini_yukle(self):
        """Excel okumak için bir worker BAŞLATIR."""
        
        # Hatayı düzelt (secili_dosyasini_yukle -> secili_dosyalar_listesi)
        if not self.secili_dosyalar_listesi: 
            return
            
        try:
            klasor_yolu = self.tarihSecCBox.currentData()
            dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
            tam_yol = os.path.join(klasor_yolu, dosya_adi)
            
            self.show_loading_dialog(f"{dosya_adi} yükleniyor... Lütfen bekleyin.")
            
            worker = Worker(self._task_run_excel_load, tam_yol)
            worker.signals.finished.connect(self._on_query_finished) 
            worker.signals.error.connect(self._on_task_error)
            self.threadpool.start(worker)
        
        except Exception as e:
            self._on_task_error(f"Excel yükleme başlatılamadı: {e}")
            
    # --- DİĞER FONKSİYONLAR (Çoğunlukla Değişiklik Yok) ---

    def export_excel(self):
        if self.df.empty: QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı."); return
        kayit_yolu = self.get_yeni_kayit_yolu("excel")
        if not kayit_yolu: return 
        self.show_loading_dialog("Excel dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(self._task_run_excel, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _task_run_excel(self, kayit_yolu, df_to_save):
        print(f"Çalışan iş parçacığı: Excel kaydetme başlatıldı -> {kayit_yolu}")
        df_to_save.to_excel(kayit_yolu, index=False)
        print("Çalışan iş parçacığı: Excel kaydetme bitti.")
        return kayit_yolu

    def export_pdf(self):
        if self.df.empty: QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı."); return
        kayit_yolu = self.get_yeni_kayit_yolu("pdf")
        if not kayit_yolu: return
        self.show_loading_dialog("PDF dosyası oluşturuluyor... Lütfen bekleyin.")
        worker = Worker(self._task_run_pdf, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _task_run_pdf(self, kayit_yolu, df_to_save):
        print(f"Çalışan iş parçacığı: PDF kaydetme başlatıldı -> {kayit_yolu}")
        doc = SimpleDocTemplate(kayit_yolu, pagesize=landscape(A4))
        data = [list(df_to_save.columns)] + df_to_save.values.tolist()
        table = Table(data)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Arial_Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Arial'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        doc.build([table])
        print("Çalışan iş parçacığı: PDF kaydetme bitti.")
        return kayit_yolu

    def _on_export_finished(self, kayit_yolu):
        self.close_loading_dialog()
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        if kayit_yolu.endswith(".xlsx"):
            self.kayitli_raporlari_tara()
            
    def _on_task_error(self, hata_mesaji):
        self.close_loading_dialog()
        print(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}")
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        
        # Hata durumunda bağlantıyı (varsa) sıfırla ve butonları kilitle
        self.db_path = None
        self.target_table = None
        self.df = pd.DataFrame()
        self.update_connection_status() # Işığı kırmızıya çeker ve butonları kilitler


    def kayitli_raporlari_tara(self):
        print("Kayıtlı raporlar taranıyor...")
        self.tarihSecCBox.blockSignals(True)
        self.tarihSecCBox.clear()
        rapor_klasorleri = {}
        if not os.path.exists(self.rapor_ana_klasoru):
            print(f"Rapor klasörü bulunamadı: {self.rapor_ana_klasoru}")
            self.tarihSecCBox.blockSignals(False)
            return
        for yil_klasor in os.listdir(self.rapor_ana_klasoru):
            yil_yolu = os.path.join(self.rapor_ana_klasoru, yil_klasor)
            if os.path.isdir(yil_yolu) and yil_klasor.isdigit():
                for gun_ay_klasor in os.listdir(yil_yolu):
                    gun_ay_yolu = os.path.join(yil_yolu, gun_ay_klasor)
                    if os.path.isdir(gun_ay_yolu) and '_' in gun_ay_klasor:
                        if any(f.endswith('.xlsx') for f in os.listdir(gun_ay_yolu)):
                            combo_text = f"{gun_ay_klasor}_{yil_klasor}"
                            rapor_klasorleri[combo_text] = gun_ay_yolu
        try:
            sorted_keys = sorted(rapor_klasorleri.keys(), key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
        except ValueError:
            sorted_keys = sorted(rapor_klasorleri.keys())
        self.tarihSecCBox.addItem("Geçmiş Rapor Seçin...", userData=None)
        for key in sorted_keys:
            self.tarihSecCBox.addItem(key, userData=rapor_klasorleri[key])
        self.tarihSecCBox.blockSignals(False)
        print(f"Tarama tamamlandı. {len(rapor_klasorleri)} adet rapor tarihi bulundu.")

    def get_yeni_kayit_yolu(self, format):
        """
        Dinamik kayıt yolu ve 'TABLO(BAŞLANGIÇ-BİTİŞ)' formatında dosya adı oluşturan fonksiyon.
        Eğer dosya varsa 'TABLO(BAŞLANGIÇ-BİTİŞ) (1).xlsx' şeklinde devam eder.
        """
        try:
            # 1. Ana klasörler
            base_folder = r"C:\rapor" 
            format_folder = os.path.join(base_folder, format)
            
            # 2. Tarihleri al ve istediğin 'DD.MM.YYYY' formatına çevir
            start_date_obj = self.date_Baslangic.date().toPyDate()
            end_date_obj = self.date_Bitis.date().toPyDate()
            
            start_str = start_date_obj.strftime("%d.%m.%Y")
            end_str = end_date_obj.strftime("%d.%m.%Y")
            
            # 3. Klasör yolu için tarihleri al (YIL\GUN_AY)
            yil = start_date_obj.strftime("%Y")
            gun_ay = start_date_obj.strftime("%d_%m")
            
            # 4. Tablo adını al (Bağlantı yoksa 'Rapor' olarak varsay)
            table_name = self.target_table if self.target_table else "Rapor"
            
            # 5. İstenen formatta ana dosya adını oluştur
            # (Dosya adlarında / \ : * ? " < > | gibi karakterler olamaz, 
            #  ama bizim formatımız (DD.MM.YYYY) buna uygun.)
            base_filename = f"{table_name}({start_str}-{end_str})"
            
            # 6. Kayıt klasörünü oluştur
            tam_klasor_yolu = os.path.join(format_folder, yil, gun_ay)
            os.makedirs(tam_klasor_yolu, exist_ok=True)
            
            # 7. Dosya adı çakışmasını kontrol et
            uzanti = "xlsx" if format == "excel" else "pdf"
            dosya_adi = f"{base_filename}.{uzanti}" # Örn: "DEBILER(1.01.2024-4.01.2024).xlsx"
            tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
            
            sayac = 1
            # Döngü: Dosya zaten varsa, adını (1), (2) diye değiştir
            while os.path.exists(tam_dosya_yolu):
                dosya_adi = f"{base_filename} ({sayac}).{uzanti}" # Örn: "DEBILER(1.01.2024-4.01.2024) (1).xlsx"
                tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
                sayac += 1
                
            return tam_dosya_yolu
            
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kayıt yolu oluşturulamadı:\n{e}")
            return None


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
        if not self.secili_dosyalar_listesi: return
        if self.secili_dosya_index < len(self.secili_dosyalar_listesi) - 1:
            self.secili_dosya_index += 1
            self.excel_dosyasini_yukle()
            
    def onceki_rapor(self):
        if not self.secili_dosyalar_listesi: return
        if self.secili_dosya_index > 0:
            self.secili_dosya_index -= 1
            self.excel_dosyasini_yukle()

    # --- TABLO DOLDURMA (PERFORMANSLI VERSİYON) ---
    def tabloyu_doldur(self, df):
        # 1. Güncellemeleri durdur (HIZLI)
        self.tbl_Veri.setUpdatesEnabled(False)
        self.tbl_Veri.setSortingEnabled(False)

        self.tbl_Veri.setRowCount(0)
        self.tbl_Veri.setColumnCount(0)

        if df.empty:
            print("Veri bulunamadı. Tablo temizleniyor.")
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
            
            # processEvents() KALDIRILDI (setUpdatesEnabled daha hızlı)
        
        # 2. Güncellemeleri tek seferde yap (HIZLI)
        self.tbl_Veri.setSortingEnabled(True)
        self.tbl_Veri.setUpdatesEnabled(True)

# --- Ana Uygulama Başlangıcı ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    register_pdf_fonts()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())