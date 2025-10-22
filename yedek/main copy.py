import sys
import urllib.parse
import os
import re
import traceback # Hata ayıklama için eklendi
from datetime import datetime

# --- GEREKLİ YENİ IMPORTLAR ---
from PyQt6.QtCore import (
    QRunnable, QThreadPool, QObject, pyqtSignal, Qt  # <-- BURAYA 'Qt' EKLENDİ
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTableWidgetItem, 
    QMessageBox, QProgressDialog
)
from PyQt6.uic import loadUi # Sadece loadUi'yi import etmek daha temiz

import pandas as pd
from sqlalchemy import create_engine
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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

# -------------------------------------------------------------------
# --- YENİ BÖLÜM: Arka Plan Çalışanı (Worker) Sınıfları ---
# -------------------------------------------------------------------

class WorkerSignals(QObject):
    '''
    İş parçacığından ana arayüze gönderilecek sinyalleri tanımlar.
    
    finished: Görev bittiğinde tetiklenir, sonucu (örn: bir DataFrame) taşır.
    error:    Görev sırasında bir hata olursa tetiklenir, hata mesajını taşır.
    '''
    finished = pyqtSignal(object) # Görev bitince 'object' tipinde bir sonuç gönder
    error = pyqtSignal(str)       # Hata olunca 'str' tipinde bir mesaj gönder

class Worker(QRunnable):
    '''
    Arka planda çalışacak olan işçi sınıfı.
    QRunnable'dan miras alır.
    '''
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn  # Arka planda çalıştırılacak fonksiyon
        self.args = args  # Fonksiyonun argümanları
        self.kwargs = kwargs  # Fonksiyonun anahtar kelimeli argümanları
        self.signals = WorkerSignals() # Sinyalleri bu çalışana bağla

    def run(self):
        '''
        İş parçacığı başlatıldığında bu fonksiyon otomatik olarak çalışır.
        '''
        try:
            # Verilen fonksiyonu (örn: _run_query_task) argümanlarıyla çalıştır
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            # Hata oluşursa
            print(f"Worker hatası: {e}")
            traceback.print_exc() # Detaylı hata dökümünü terminale yaz
            self.signals.error.emit(str(e)) # Hata sinyali gönder
        else:
            # Başarılı olursa
            self.signals.finished.emit(result) # Bitiş sinyali ve sonucu gönder

# -------------------------------------------------------------------
# --- GÜNCELLENMİŞ MainWindow Sınıfı ---
# -------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # arayuz.ui dosyasını yüklüyoruz (artık QtWidgets import etmeye gerek yok)
        loadUi('arayuz.ui', self) 
        
        # --- Sınıf Değişkenleri ---
        self.df = pd.DataFrame()
        self.rapor_ana_klasoru = r"C:\rapor\excel"
        self.secili_dosyalar_listesi = []
        self.secili_dosya_index = 0
        
        # --- YENİ: Thread Pool (İş Parçacığı Havuzu) ---
        self.threadpool = QThreadPool()
        print(f"Multithreading için {self.threadpool.maxThreadCount()} adet iş parçacığı mevcut.")

        self.tbl_Veri.setSortingEnabled(True)

        # -----------------------------

        self.progress_dialog = None

        # --- YENİ: İlerleme Penceresi (Progress Dialog) ---
        self.progress_dialog = None

        # --- Buton Bağlantıları (Değişiklik yok) ---
        self.btn_Sorgula.clicked.connect(self.sorgulama_yap)
        self.btn_Excel.clicked.connect(self.export_excel)
        self.btn_PDF.clicked.connect(self.export_pdf)
        self.tarihSecCBox.currentIndexChanged.connect(self.combobox_degisti)
        self.ileriTarihButton.clicked.connect(self.sonraki_rapor)
        self.geriTarihButton.clicked.connect(self.onceki_rapor)

        # --- Başlangıç Ayarları (Değişiklik yok) ---
        self.btn_Excel.setEnabled(False)
        self.btn_PDF.setEnabled(False)
        self.kayitli_raporlari_tara()

# --- YENİ: İlerleme Penceresi Fonksiyonları ---
# --- YENİ: İlerleme Penceresi Fonksiyonları ---
    # --- YENİ: İlerleme Penceresi Fonksiyonları ---
    def show_loading_dialog(self, text):
        """Kapatılamayan ilerleme penceresini oluşturur ve gösterir."""
        if not self.progress_dialog:
            self.progress_dialog = QProgressDialog(text, None, 0, 0, self) # Min=0, Max=0 -> Sürekli dönen bar
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal) # Diğer pencereleri kitler
            self.progress_dialog.setCancelButton(None) # İptal butonunu gizler
            
            # --- HATA VEREN SATIR DEVRE DIŞI BIRAKILDI ---
            # self.progress_dialog.setWindowFlag(Qt.WindowCloseButtonHint, False) 
            # 
            # Üstteki satır sizin PyQt6 sürümünüzde ısrarla 'AttributeError' verdiği için
            # programın çökmesini engellemek adına devre dışı bırakıldı.
            # 'setCancelButton(None)' zaten 'X' butonunu da etkisiz hale getirmelidir.
            
            self.progress_dialog.setMinimumDuration(0) # Hemen göster
        
        self.progress_dialog.setLabelText(text)
        self.progress_dialog.setValue(0) # Sürekli dönen bar için
        self.progress_dialog.show()
        QApplication.processEvents() # Arayüzün güncellenmesini zorla
   
    def close_loading_dialog(self):
        """İlerleme penceresini kapatır."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
    # --- GÜNCELLENEN FONKSİYONLAR (THREADING İÇİN BÖLÜNDÜ) ---

    # --- SORGULAMA ---
    def sorgulama_yap(self):
        """1. Adım: Kullanıcı butona bastığında tetiklenir."""
        self.show_loading_dialog("Veritabanı sorgulanıyor... Lütfen bekleyin.")
        
        # Gerekli parametreleri al
        baslangic = self.date_Baslangic.date().toString("yyyy-MM-dd")
        bitis = self.date_Bitis.date().toString("yyyy-MM-dd")
        
        # Worker'ı oluştur ve çalıştırılacak fonksiyonu (_task_run_query) ver
        worker = Worker(self._task_run_query, baslangic, bitis) 
        
        # Worker bittiğinde veya hata verdiğinde çalışacak fonksiyonları bağla
        worker.signals.finished.connect(self._on_query_finished)
        worker.signals.error.connect(self._on_task_error)
        
        # Worker'ı arka planda çalıştır
        self.threadpool.start(worker)


# DOSYANIZDA ZATEN MEVCUT OLAN BU FONKSİYONU AŞAĞIDAKİ İLE DEĞİŞTİRİN
# (Yaklaşık 175. satırda olmalı)

    def _task_run_query(self, baslangic_tarihi, bitis_tarihi):
        """2. Adım: ARKA PLANDA (Worker Thread) çalışacak olan asıl sorgu işi."""
        print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tarih: {baslangic_tarihi} - {bitis_tarihi}")
        
        db_path = r"C:\Users\User\OneDrive\Desktop\rapor\Yedek - CARSAMBA_RAPOR.mdb"
        connection_string = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"Dbq={db_path};"
        )
        quoted_connection_string = urllib.parse.quote_plus(connection_string)
        engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
        
        sql_query = "SELECT * FROM [DEBILER] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"
        
        # Sorguyu çalıştır ve DataFrame'i döndür
        df = pd.read_sql(sql_query, engine, params=(baslangic_tarihi, bitis_tarihi))
        
        print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
        return df # Bu 'df' nesnesi, finished sinyali ile _on_query_finished'e gidecek


# --- YENİ FONKSİYON EKLEYİN ---
# Aşağıdaki yeni fonksiyonu _task_run_query fonksiyonunun HEMEN ALTINA ekleyin.

    def _task_run_excel_load(self, tam_yol):
        """ARKA PLANDA çalışacak Excel okuma işi."""
        print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
        # 'engine="calamine"' parametresi, okuma hızını ciddi oranda artırır.
        df = pd.read_excel(tam_yol, engine="calamine")
        print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
        return df # Bu df, _on_query_finished'e gidecek


# --- DOSYANIZDA ZATEN MEVCUT OLAN BU FONKSİYONU AŞAĞIDAKİ İLE DEĞİŞTİRİN ---
# (Yaklaşık 195. satırda olmalı)
# Bu fonksiyon artık hem veritabanı sorgusunun hem de excel yüklemesinin sonucunu işleyecek

    def _on_query_finished(self, df):
        """3. Adım: ANA ARAYÜZDE çalışır. (Worker'dan gelen DB VEYA Excel sonucunu işler)"""
        print("Ana arayüz: Veri alındı. Tablo dolduruluyor... (Bu işlem donmaya neden olabilir)")
        
        # 1. Gelen sonucu global DataFrame'e ata
        self.df = df 
        
        # 2. Asıl ağır UI işini (tabloyu doldur) yap.
        #    Bekleme penceresi bu işlem sırasında donuk da olsa görünür kalacak.
        self.tabloyu_doldur(self.df) 
        
        # 3. İş bittikten sonra butonları ayarla
        if not self.df.empty:
            self.btn_Excel.setEnabled(True)
            self.btn_PDF.setEnabled(True)
        else:
            self.btn_Excel.setEnabled(False)
            self.btn_PDF.setEnabled(False)

        # 4. (Sadece Excel yüklemesi için) Durum çubuğunu güncelle
        try:
            if self.tarihSecCBox.currentData() and self.secili_dosyalar_listesi:
                dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
                self.statusbar.showMessage(f"Gösterilen: {dosya_adi} ({self.secili_dosya_index + 1} / {len(self.secili_dosyalar_listesi)})")
        except Exception as e:
            pass # Hata olursa önemli değil

        # 5. !!! DEĞİŞİKLİK BURADA !!!
        #    Tüm ağır işler bittikten SONRA bekleme penceresini kapat.
        self.close_loading_dialog() 
        print(f"Ana arayüz: İşlem tamamlandı ve sonuç tabloya yüklendi.")


# --- DOSYANIZDA ZATEN MEVCUT OLAN BU FONKSİYONU AŞAĞIDAKİ İLE DEĞİŞTİRİN ---
# (Yaklaşık 340. satırda olmalı)
# Artık bu fonksiyon da donmaya neden olmasın diye bir worker başlatacak.

    def excel_dosyasini_yukle(self):
        """Seçili index'e göre Excel dosyasını okumak için bir worker BAŞLATIR."""
        if not self.secili_dosyalar_listesi:
            return
            
        try:
            klasor_yolu = self.tarihSecCBox.currentData()
            dosya_adi = self.secili_dosyalar_listesi[self.secili_dosya_index]
            tam_yol = os.path.join(klasor_yolu, dosya_adi)
            
            # 1. Bekleme penceresini göster
            self.show_loading_dialog(f"{dosya_adi} yükleniyor... Lütfen bekleyin.")
            
            # 2. Excel okuma işi için bir worker oluştur
            worker = Worker(self._task_run_excel_load, tam_yol)
            
            # 3. İş bitince, veritabanı sorgusuyla aynı 'bitiş' fonksiyonunu (on_query_finished)
            #    çağırarak sonucu tabloya yükle.
            worker.signals.finished.connect(self._on_query_finished) 
            worker.signals.error.connect(self._on_task_error)
            
            # 4. Worker'ı arka planda başlat
            self.threadpool.start(worker)
        
        except Exception as e:
            # Henüz worker başlamadan bir hata olursa (örn: dosya adı okunamadı)
            print(f"Excel yükleme başlatılamadı: {e}")
            self._on_task_error(f"Excel yükleme başlatılamadı: {e}")
    # --- EXCEL AKTARMA ---
    def export_excel(self):
        """1. Adım: Excel butonu."""
        if self.df.empty:
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        kayit_yolu = self.get_yeni_kayit_yolu("excel")
        if not kayit_yolu:
            return 
            
        self.show_loading_dialog("Excel dosyası oluşturuluyor... Lütfen bekleyin.")
        
        # Worker'ı oluştur ve çalıştırılacak fonksiyonu (_task_run_excel) ver
        worker = Worker(self._task_run_excel, kayit_yolu, self.df.copy()) # df'in kopyasını gönder
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _task_run_excel(self, kayit_yolu, df_to_save):
        """2. Adım: ARKA PLANDA çalışacak Excel kaydetme işi."""
        print(f"Çalışan iş parçacığı: Excel kaydetme başlatıldı -> {kayit_yolu}")
        df_to_save.to_excel(kayit_yolu, index=False)
        print("Çalışan iş parçacığı: Excel kaydetme bitti.")
        return kayit_yolu # Bitiş sinyaline dosya yolunu gönder

    # --- PDF AKTARMA ---
    def export_pdf(self):
        """1. Adım: PDF butonu."""
        if self.df.empty:
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak veri bulunamadı.")
            return

        kayit_yolu = self.get_yeni_kayit_yolu("pdf")
        if not kayit_yolu:
            return

        self.show_loading_dialog("PDF dosyası oluşturuluyor... Lütfen bekleyin.")
        
        # Worker'ı oluştur ve çalıştırılacak fonksiyonu (_task_run_pdf) ver
        worker = Worker(self._task_run_pdf, kayit_yolu, self.df.copy())
        worker.signals.finished.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_task_error)
        self.threadpool.start(worker)

    def _task_run_pdf(self, kayit_yolu, df_to_save):
        """2. Adım: ARKA PLANDA çalışacak PDF kaydetme işi."""
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
        return kayit_yolu # Bitiş sinyaline dosya yolunu gönder

    # --- GENEL BİTİŞ VE HATA FONKSİYONLARI ---
    
    def _on_export_finished(self, kayit_yolu):
        """3. Adım: ANA ARAYÜZDE çalışır. Excel VEYA PDF kaydetme bittiğinde."""
        self.close_loading_dialog()
        
        QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{kayit_yolu}")
        
        # Eğer kaydedilen bir Excel ise, ComboBox'ı yenile
        if kayit_yolu.endswith(".xlsx"):
            self.kayitli_raporlari_tara()
            
    def _on_task_error(self, hata_mesaji):
        """3. Adım: ANA ARAYÜZDE çalışır. Herhangi bir Worker'da hata olursa."""
        self.close_loading_dialog()
        print(f"Ana arayüz: Görev hatası alındı: {hata_mesaji}")
        QMessageBox.critical(self, "Hata", f"İşlem sırasında bir hata oluştu:\n\n{hata_mesaji}")
        
        # Hata durumunda butonları ve df'i sıfırla
        self.df = pd.DataFrame()
        self.btn_Excel.setEnabled(False)
        self.btn_PDF.setEnabled(False)


    # -------------------------------------------------------------------
    # --- GERİ KALAN FONKSİYONLAR (Değişiklik Gerekmiyor) ---
    # -------------------------------------------------------------------

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
            sorted_keys = sorted(rapor_klasorleri.keys(), 
                                 key=lambda d: datetime.strptime(d, '%d_%m_%Y'))
        except ValueError:
            sorted_keys = sorted(rapor_klasorleri.keys())

        self.tarihSecCBox.addItem("Geçmiş Rapor Seçin...", userData=None)
        for key in sorted_keys:
            self.tarihSecCBox.addItem(key, userData=rapor_klasorleri[key])
        
        self.tarihSecCBox.blockSignals(False)
        print(f"Tarama tamamlandı. {len(rapor_klasorleri)} adet rapor tarihi bulundu.")

    def get_yeni_kayit_yolu(self, format):
        try:
            base_folder = r"C:\rapor" 
            format_folder = os.path.join(base_folder, format)
            
            start_date = self.date_Baslangic.date().toPyDate()
            yil = start_date.strftime("%Y")
            gun_ay = start_date.strftime("%d_%m")
            
            tam_klasor_yolu = os.path.join(format_folder, yil, gun_ay)
            os.makedirs(tam_klasor_yolu, exist_ok=True)
            
            sayac = 1
            while True:
                uzanti = "xlsx" if format == "excel" else "pdf"
                dosya_adi = f"{format}{sayac}.{uzanti}"
                tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
                if not os.path.exists(tam_dosya_yolu):
                    return tam_dosya_yolu 
                sayac += 1
        except Exception as e:
            print(f"Kayıt yolu oluşturulurken hata: {e}")
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
            # Excel yükleme de donmaya neden olabilir, bunu da thread'e alabiliriz
            # Şimdilik basit tutalım:
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




    def tabloyu_doldur(self, df):
        # --- YENİ PERFORMANS İYİLEŞTİRMESİ ---
        # 1. Qt'ye arayüz güncellemelerini geçici olarak durdurmasını söylüyoruz.
        self.tbl_Veri.setUpdatesEnabled(False)
        # 2. Sıralamayı da doldurma sırasında kapatıyoruz (bu zaten vardı).
        self.tbl_Veri.setSortingEnabled(False)

        # Önce tabloyu tamamen temizle
        self.tbl_Veri.setRowCount(0)
        self.tbl_Veri.setColumnCount(0)

        if df.empty:
            print("Veri bulunamadı. Tablo temizleniyor.")
            # Güncellemeleri tekrar açmayı unutma!
            self.tbl_Veri.setSortingEnabled(True)
            self.tbl_Veri.setUpdatesEnabled(True)
            return

        # Satır ve sütun sayılarını ayarla
        self.tbl_Veri.setRowCount(len(df))
        self.tbl_Veri.setColumnCount(len(df.columns))
        self.tbl_Veri.setHorizontalHeaderLabels(df.columns)

        # Ana döngü
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
            
            # --- KALDIRILDI ---
            # 'processEvents()' komutunu buradan kaldırıyoruz,
            # çünkü 'setUpdatesEnabled(False)' ile çakışır ve yavaşlatır.
            # if i % 100 == 0:
            #     QApplication.processEvents() 
        
        # --- YENİ PERFORMANS İYİLEŞTİRMESİ ---
        # 3. Doldurma bitti, sıralamayı tekrar aktif et.
        self.tbl_Veri.setSortingEnabled(True)
        # 4. Qt'ye arayüzü şimdi (ve tek seferde) güncellemesini söylüyoruz.
        self.tbl_Veri.setUpdatesEnabled(True)

# --- Ana Uygulama Başlangıcı ---


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # PDF fontlarını (Arial) program başlarken yükle
    register_pdf_fonts()
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())