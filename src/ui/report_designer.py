# src/ui/report_designer.py

import os
import pandas as pd
import functools
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, 
    QTableWidget, QTableWidgetItem, QVBoxLayout, QLabel,
    QApplication, QHeaderView, QGraphicsItem, QMessageBox,QFrame
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter

# --- Çekirdek (Core) ve Görev (Task) Importları ---
from src.core.tasks import fetch_preview_data_task # <-- YENİ GÖREVİMİZ
from src.threading.workers import Worker

# -------------------------------------------------------------------
# --- 1. SINIF: Sürükle-Bırak'ı yakalayan View ---
# -------------------------------------------------------------------
class DroppableGraphicsView(QGraphicsView):
    """
    Sürükle-bırak (Drag-and-Drop) olaylarını yakalayan
    ve bunları 'scene' (tuval) üzerine bırakan özel QGraphicsView.
    """
    def __init__(self, scene, parent_designer, main_window):
        super().__init__(scene, parent_designer)
        self.setAcceptDrops(True) 
        self.main_window = main_window # Ana pencereye (threadpool için) referans

    def dragEnterEvent(self, event):
        event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        event.acceptProposedAction() 

    def dropEvent(self, event):
        """Fare alana bırakıldığında tetiklenir."""

        if not event.mimeData().hasText():
            event.ignore()
            return

        drag_text = event.mimeData().text().strip()
        drop_position = self.mapToScene(event.position().toPoint()) 
        print(f"'{drag_text}' tuval üzerine bırakıldı (Pozisyon: {drop_position})")

        # Ana pencereden bağlantı ve şema bilgilerini al
        full_schema = self.main_window.full_schema_data
        config = self.main_window.db_config 

        item_type = None

        # --- YENİ MANTIK: Gelen veri Araç Kutusundan mı? ---
        if drag_text.startswith("__TOOL_"):
            if drag_text == "__TOOL_LABEL__":
                self._create_label_widget("Yeni Başlık", drop_position)
            elif drag_text == "__TOOL_LINE__":
                self._create_line_widget(drop_position)
            # TODO: Resim veya Grafik araçları buraya eklenebilir
            event.acceptProposedAction()
            return # İşlem bitti
        # --------------------------------------------------

        # --- ESKİ MANTIK: Veritabanı Gezgini'nden mi? ---
        if not full_schema:
            QMessageBox.warning(self, "Hata", "Veritabanı şeması bulunamadı.")
            event.ignore()
            return

        table_name = None
        column_name = None
        parts = drag_text.split('.')

        if drag_text in full_schema:
            item_type = "Table"
            table_name = drag_text
            column_name = None
            print(f"Bırakılan: Tablo ({table_name})")

        elif len(parts) > 1:
            potential_table_name = ".".join(parts[:-1]) 
            if potential_table_name in full_schema:
                item_type = "Column"
                table_name = potential_table_name
                column_name = parts[-1]
                print(f"Bırakılan: Sütun ({table_name}.{column_name})")

        if item_type:
            event.acceptProposedAction()

            # Gerçek veriyi çekmek için bir worker başlat
            loading_label = QLabel(f"{drag_text}\nVeri yükleniyor...")
            loading_label.setStyleSheet("background-color: white; border: 1px solid black; padding: 10px;")
            proxy = self.scene().addWidget(loading_label)
            proxy.setPos(drop_position)

            worker = Worker(fetch_preview_data_task, config, table_name, column_name, limit=10)

            worker.signals.finished.connect(
                functools.partial(self._on_preview_data_loaded, 
                                drop_position=drop_position, 
                                loading_proxy=proxy)
            )
            worker.signals.error.connect(
                functools.partial(self._on_preview_error, loading_proxy=proxy)
            )

            self.main_window.threadpool.start(worker)
        else:
            print(f"Anlaşılamayan sürükleme verisi: {drag_text}")
            event.ignore()

    # --- YENİ YARDIMCI FONKSİYONLAR (Araç Kutusu için) ---
    def _create_label_widget(self, text, position):
        """Tuvale taşınabilir bir başlık (QLabel) ekler."""
        label = QLabel(text)
        label.setStyleSheet("font-size: 18pt; background-color: white;")
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(label)
        proxy.setPos(position)
        proxy.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.scene().addItem(proxy)

    def _create_line_widget(self, position):
        """Tuvale taşınabilir yatay bir çizgi (QFrame) ekler."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setMinimumWidth(300) # Başlangıç genişliği
        line.setStyleSheet("background-color: white;")

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(line)
        proxy.setPos(position)
        proxy.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.scene().addItem(proxy)
    


    def _on_preview_data_loaded(self, data_frame, drop_position, loading_proxy):
        """(Callback) Worker'dan önizleme verisi (DataFrame) geldiğinde çalışır."""
        
        # "Yükleniyor..." etiketini kaldır
        self.scene().removeItem(loading_proxy)
        del loading_proxy
        
        if data_frame is None or data_frame.empty:
            QMessageBox.warning(self, "Veri Yok", "Önizleme için veri çekilemedi veya seçilen kaynak boş.")
            return

        # Veriyle doldurulacak yeni bir QTableWidget oluştur
        new_table = QTableWidget()
        self._populate_preview_table(new_table, data_frame) # Helper fonksiyonu çağır
        
        # Boyut ve pozisyon ayarları
        new_table.resize(400, 250) # Boyutu biraz büyütelim

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(new_table)
        proxy.setPos(drop_position)
        
        # Taşınabilir/Seçilebilir yap
        proxy.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                       QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        
        self.scene().addItem(proxy)

    def _on_preview_error(self, error_message, loading_proxy):
        """(Callback) Worker'dan hata gelirse çalışır."""
        # "Yükleniyor..." etiketini kaldır
        self.scene().removeItem(loading_proxy)
        del loading_proxy
        
        print(f"HATA: Önizleme verisi çekilemedi: {error_message}")
        QMessageBox.critical(self, "Önizleme Hatası", 
                             f"Veri önizlemesi alınırken bir hata oluştu:\n{error_message}")
        
    def _populate_preview_table(self, table_widget, df):
        """Bir QTableWidget'ı gelen DataFrame ile doldurur."""
        table_widget.setRowCount(len(df))
        table_widget.setColumnCount(len(df.columns))
        table_widget.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j in range(len(df.columns)):
                item_value = str(df.iloc[i, j])
                table_widget.setItem(i, j, QTableWidgetItem(item_value))
        
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

# -------------------------------------------------------------------
# --- 2. SINIF: Asıl Tasarımcı Widget'ı (Değişiklik yok) ---
# -------------------------------------------------------------------
class ReportDesignerWidget(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        
        self.main_window = main_window 
        
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 794, 1123) 
        self.scene.setBackgroundBrush(Qt.GlobalColor.white)

        self.view = DroppableGraphicsView(self.scene, self, main_window=self.main_window)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.setContentsMargins(0,0,0,0)