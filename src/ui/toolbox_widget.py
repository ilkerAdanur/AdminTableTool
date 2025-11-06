# src/ui/toolbox_widget.py

import os
# --- DÜZELTME 1: Gerekli import'ları (QStyle dahil) ekleyin ---
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
    QAbstractItemView, QStyle 
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QMimeData

class ToolboxWidget(QWidget):
    """
    Rapor tasarımcısına sürüklenecek standart rapor elemanlarını
    (Başlık, Resim vb.) içeren widget.
    """
    
    TOOLBOX_MIME_TYPE = "application/x-admintabletool-tool"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        self.toolList = QListWidget()
        layout.addWidget(self.toolList)
        
        # Sürükle-Bırak Ayarları
        self.toolList.setDragEnabled(True)
        self.toolList.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.toolList.setDefaultDropAction(Qt.DropAction.CopyAction)
        
        self.toolList.mimeTypes = self.mimeTypes
        self.toolList.mimeData = self.mimeData
        
        self._populate_tools()

    def _populate_tools(self):
        """Araç kutusuna eklenecek öğeleri tanımlar."""
        
        # 1. Başlık (Label) Aracı
        label_item = QListWidgetItem("Başlık (Metin)")
        # QStyle artık import edildiği için bu satır çalışacaktır
        label_item.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_TitleBarMenuButton 
        ))
        label_item.setData(Qt.ItemDataRole.UserRole, "__TOOL_LABEL__")
        self.toolList.addItem(label_item)

        # 2. Resim Aracı
        image_item = QListWidgetItem("Resim")
        image_item.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileIcon 
        ))
        image_item.setData(Qt.ItemDataRole.UserRole, "__TOOL_IMAGE__")
        self.toolList.addItem(image_item)
        
        # 3. Çizgi Aracı
        line_item = QListWidgetItem("Yatay Çizgi")
        
        # --- DÜZELTME 2: 'SP_SplitterHandleHorizontal' geçersizdi. ---
        # Bunun yerine 'SP_ArrowRight' gibi geçerli bir ikon kullanalım.
        line_item.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_ArrowRight 
        ))
        line_item.setData(Qt.ItemDataRole.UserRole, "__TOOL_LINE__")
        self.toolList.addItem(line_item)

    # --- Sürükleme Mantığı (Değişiklik yok) ---
    def mimeTypes(self):
        """Bu widget'ın hangi formatı sürüklediğini belirtir."""
        return [self.TOOLBOX_MIME_TYPE, "text/plain"]

    def mimeData(self, items):
        """Sürükleme başladığında, seçilen öğenin özel verisini paketler."""
        mime_data = QMimeData()
        
        if items:
            item = items[0] 
            tool_type = item.data(Qt.ItemDataRole.UserRole) # "__TOOL_LABEL__" vb.
            
            if tool_type:
                mime_data.setData(self.TOOLBOX_MIME_TYPE, tool_type.encode('utf-8'))
                mime_data.setText(tool_type) 
                print(f"Araç Kutusu: Sürükleme başladı. Taşınan veri: {tool_type}")
                
        return mime_data