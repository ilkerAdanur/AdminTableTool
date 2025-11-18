# src/ui/daily_summary_dialog.py

import os
import logging
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, 
    QTableWidgetItem, QHeaderView, QFileDialog
)
from PyQt6.QtCore import QDate

# <-- 2. Modüle özel logger'ı tanımlayın
logger = logging.getLogger(__name__)

class DailySummaryDialog(QDialog):
    def __init__(self, source_columns=None, parent=None):
        super().__init__(parent)
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            ui_file_path = os.path.join(current_dir, 'daily_summary_dialog.ui')
            loadUi(ui_file_path, self)
            logger.info("DailySummaryDialog UI dosyası başarıyla yüklendi.") # <-- LOG
        except Exception as e:
            # <-- LOG (Kritik hata, UI yüklenemedi)
            logger.critical(f"UI dosyası 'daily_summary_dialog.ui' yüklenemedi: {e}", exc_info=True)
            self.setWindowTitle("Hata")
            fallback_layout = QVBoxLayout(self)
            fallback_layout.addWidget(QLabel(f"UI dosyası 'daily_summary_dialog.ui' yüklenemedi.\n{e}"))
            return

        self.source_columns = source_columns if source_columns else []
        self.summary_df = None 
        
        self.main_window = parent # Ana pencereye referans

        self.groupBox_Results.setVisible(False)
        self.btn_ExportExcel.setEnabled(False)

        self._populate_comboboxes()
        
        self.date_Start.setDate(QDate.currentDate().addMonths(-1))
        self.date_End.setDate(QDate.currentDate())

        self.btn_RunSummary.clicked.connect(self.run_summary)
        self.btn_ExportExcel.clicked.connect(self.export_excel)
        logger.debug("DailySummaryDialog başlatıldı ve sinyaller bağlandı.") # <-- LOG

    def _populate_comboboxes(self):
        if self.source_columns:
            self.combo_DateColumn.addItems(self.source_columns)
            self.combo_DataColumn.addItems(self.source_columns)
            
            if "TARIH" in self.source_columns:
                self.combo_DateColumn.setCurrentText("TARIH")
            elif self.source_columns:
                 self.combo_DateColumn.setCurrentIndex(0) 
                 
            if self.source_columns:
                 self.combo_DataColumn.setCurrentIndex(0) 
            logger.debug(f"Combobox'lar {len(self.source_columns)} sütun ile dolduruldu.") # <-- LOG

    def run_summary(self):
        logger.info("Günlük Özet Oluşturma tıklandı.")
        
        settings = self.get_summary_settings()
        if not settings["date_col"] or not settings["data_col"]:
            # --- LOG (Uyarı) ---
            logger.warning("Kullanıcı 'Tarih Sütunu' veya 'Veri Sütunu' seçmeden özeti çalıştırmayı denedi.")
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen bir Tarih Sütunu ve Veri Sütunu seçin.")
            return

        logger.info(f"İstenen özet ayarları: {settings}")
        
        # Ana pencereden (parent) worker'ı başlatmasını iste
        if self.main_window and hasattr(self.main_window, "run_daily_summary_worker"):
            self.main_window.run_daily_summary_worker(settings, self) # 'self'i (diyaloğu) de gönder
            self.btn_RunSummary.setEnabled(False) # İşlem bitene kadar kilitle
            self.btn_RunSummary.setText("İşleniyor...")
        else:
            # --- LOG (Kritik hata) ---
            logger.critical("Ana pencereye (main_window) ulaşılamadı. Worker başlatılamıyor.")
            QMessageBox.critical(self, "Hata", "Ana pencereye ulaşılamadı. Worker başlatılamıyor.")

    def export_excel(self):
        logger.info("Günlük Özet Excel'e Aktar tıklandı.")
        if self.summary_df is None or self.summary_df.empty:
            # --- LOG (Uyarı) ---
            logger.warning("Dışa aktarılacak özet veri bulunamadı, işlem iptal edildi.")
            QMessageBox.warning(self,"Veri Yok", "Dışa aktarılacak özet veri bulunamadı.")
            return
            
        try:
            default_path = os.path.abspath(os.path.join("rapor", "gunluk_ozetler"))
            os.makedirs(default_path, exist_ok=True) 

            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Özet Raporu Kaydet", 
                default_path, 
                "Excel Dosyaları (*.xlsx)"
            )

            if not file_path:
                logger.info("Kullanıcı Excel kayıt işlemini iptal etti (QFileDialog).") # <-- LOG
                return 

            self.summary_df.to_excel(file_path, index=True) 
            
            # --- LOG (Başarı) ---
            logger.info(f"Günlük özet başarıyla Excel'e kaydedildi: {file_path}")
            QMessageBox.information(self, "Başarılı", f"Dosya başarıyla kaydedildi:\n{file_path}")

        except Exception as e:
            # --- LOG (Hata) ---
            logger.error(f"Excel dosyası kaydedilirken hata oluştu: {e}", exc_info=True)
            QMessageBox.critical(self, "Kayıt Hatası", f"Excel dosyası kaydedilirken hata oluştu:\n{e}")

    def get_summary_settings(self):
        return {
            "start_date": self.date_Start.date().toString("yyyy-MM-dd"),
            "end_date": self.date_End.date().toString("yyyy-MM-dd"),
            "date_col": self.combo_DateColumn.currentText(),
            "data_col": self.combo_DataColumn.currentText(),
            "agg_type": self.combo_AggType.currentText()
        }

    def update_summary_table(self, summary_df):
        self.summary_df = summary_df
        
        self.btn_RunSummary.setEnabled(True)
        self.btn_RunSummary.setText("Özeti Oluştur")
        
        self.table_SummaryResults.setRowCount(0) 

        if summary_df is None or summary_df.empty:
            # --- LOG (Uyarı) ---
            logger.warning("update_summary_table çağrıldı ancak özetleme sonucunda veri bulunamadı (None veya empty).")
            QMessageBox.warning(self, "Sonuç Yok", "Özetleme sonucunda veri bulunamadı.")
            self.btn_ExportExcel.setEnabled(False)
            self.groupBox_Results.setVisible(True) 
            return

        self.groupBox_Results.setVisible(True)

        # --- LOG (Bilgi) ---
        logger.info(f"Günlük özet tablosu {len(summary_df)} satır ile dolduruluyor...")

        self.table_SummaryResults.setRowCount(len(summary_df))
        self.table_SummaryResults.setColumnCount(len(summary_df.columns) + 1)
        
        header_labels = [summary_df.index.name if summary_df.index.name else "Tarih"] 
        header_labels.extend(summary_df.columns) 
        self.table_SummaryResults.setHorizontalHeaderLabels(header_labels)

        for i, (index_val, row) in enumerate(summary_df.iterrows()):
            self.table_SummaryResults.setItem(i, 0, QTableWidgetItem(str(index_val.strftime('%Y-%m-%d')))) 
            
            for j, col_name in enumerate(summary_df.columns):
                item_value = str(row[col_name])
                self.table_SummaryResults.setItem(i, j + 1, QTableWidgetItem(item_value))
        
        self.table_SummaryResults.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.btn_ExportExcel.setEnabled(True)
        logger.info("Günlük özet tablosu başarıyla dolduruldu.") # <-- LOG