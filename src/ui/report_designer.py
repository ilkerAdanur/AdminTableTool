# src/ui/report_designer.py

import os
import pandas as pd
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, 
    QTableWidget, QTableWidgetItem, QVBoxLayout, QLabel,
    QApplication, QHeaderView
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter 

# -------------------------------------------------------------------
# --- YENİ SINIF: Sürükle-Bırak'ı yakalayan View ---
# -------------------------------------------------------------------

class DroppableGraphicsView(QGraphicsView):
    """
    Sürükle-bırak (Drag-and-Drop) olaylarını yakalayan
    ve bunları 'scene' (tuval) üzerine bırakan özel QGraphicsView.
    """
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        # Bırakma olaylarını kabul etmesi için bu widget'ı etkinleştir
        self.setAcceptDrops(True) 

    def dragEnterEvent(self, event):
        """
        Fare sürükleyerek alana girdiğinde tetiklenir.
        DÜZELTME: Sadece 'text' değil, her türlü sürüklemeyi kabul et
        (Çarpı işaretini engellemek için)
        """
        event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        """Fare alanda sürüklenirken tetiklenir."""
        event.acceptProposedAction() # Bunu da her zaman kabul et

    def dropEvent(self, event):
        """Fare alana bırakıldığında tetiklenir."""
        
        # Bırakma anında metin olup olmadığını KONTROL ET
        if event.mimeData().hasText():
            # Veriyi düz metin olarak al (örn: "id", "ad", "dbo.ogrenciler")
            drag_text = event.mimeData().text()
            
            # Olayın pozisyonunu (ekran) Tuval (scene) koordinatlarına çevir
            drop_position = self.mapToScene(event.pos())

            print(f"'{drag_text}' tuval üzerine bırakıldı (Pozisyon: {drop_position})")

            # TODO: 'drag_text'i kullanarak ana pencereden (main_window)
            # bir worker tetikleyip gerçek veritabanı sorgusu yapabiliriz.
            
            # Şimdilik, sürüklenen öğeyi gösteren basit bir tablo oluşturalım:
            new_table = QTableWidget(5, 2) # 5 satır, 2 sütun
            new_table.setHorizontalHeaderLabels(["Sütun Adı", "Değer (Örnek)"])
            
            new_table.setItem(0, 0, QTableWidgetItem("Sürüklenen Sütun"))
            new_table.setItem(0, 1, QTableWidgetItem(drag_text))
            
            new_table.setItem(1, 0, QTableWidgetItem("Örnek Veri 1"))
            new_table.setItem(1, 1, QTableWidgetItem("123"))
            
            new_table.resize(300, 200) # Tabloya varsayılan bir boyut ver
            new_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            # Widget'ı Tuvale Eklemek için "Proxy" Kullanma
            proxy = QGraphicsProxyWidget()
            proxy.setWidget(new_table)
            proxy.setPos(drop_position) # Bırakıldığı konuma yerleştir
            
            # Eklenen tabloyu tuval üzerinde seçilebilir ve taşınabilir yap
            proxy.setFlags(QGraphicsProxyWidget.GraphicsProxyWidgetFlag.ItemIsSelectable | 
                           QGraphicsProxyWidget.GraphicsProxyWidgetFlag.ItemIsMovable)
            
            self.scene().addItem(proxy) # 'scene()' metodunu çağırarak ekle
            event.acceptProposedAction()
        else:
            # Bırakılan veri metin değilse (örn: dosya) yok say
            print("Bırakılan veri metin içermiyor, yok sayıldı.")
            event.ignore()

# -------------------------------------------------------------------
# --- Güncellenmiş ReportDesignerWidget Sınıfı ---
# -------------------------------------------------------------------
class ReportDesignerWidget(QWidget):
    """
    Sürükle-bırak ile raporların (tablolar, grafikler) tasarlandığı
    "boş sayfa" (tuval) sekmesi.
    """
    def __init__(self, main_window):
        super().__init__(main_window)
        
        self.main_window = main_window 
        
        # 1. Ana Tuval (Scene)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 794, 1123) # A4 Portre boyutu
        self.scene.setBackgroundBrush(Qt.GlobalColor.white)

        # 2. Görüntüleyici (View) - ARTIK YENİ ÖZEL SINIFIMIZI KULLANIYORUZ
        self.view = DroppableGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing) # Yumuşak görüntü

        # 3. Ana Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.setContentsMargins(0,0,0,0)

    # --- Sürükle-Bırak Olayları ---
    # Bu fonksiyonlar artık bu sınıfta değil, 'DroppableGraphicsView' sınıfının içinde.
    # Bu, 'ReportDesignerWidget' sınıfını temiz tutar.