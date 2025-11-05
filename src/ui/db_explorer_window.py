# src/ui/db_explorer_window.py

import os
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidgetItem, QStyle, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal

class DbExplorerWindow(QWidget):
    # Kullanıcı bir tabloya çift tıkladığında bu sinyal tetiklenecek
    table_activated = pyqtSignal(str) 
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Hata gizleyen try...except bloğu KALDIRILDI.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_file_path = os.path.join(current_dir, 'db_explorer_window.ui')
        loadUi(ui_file_path, self)

        # Sürükle-Bırak ayarları
        self.treeWidget_DB.setDragEnabled(True) 
        self.treeWidget_DB.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        
        # Başlık ayarları
        self.treeWidget_DB.setHeaderLabel("Veritabanı Yapısı") 
        self.treeWidget_DB.setHeaderHidden(False)
        
        # Çift tıklama sinyali
        self.treeWidget_DB.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, item, column):
        """Ağaçtaki bir öğeye çift tıklandığında çalışır."""
        parent = item.parent()
        # Sadece bir 'Tables' öğesinin altındaki öğeye (yani tabloya) tıklandıysa
        if parent and parent.text(0) == "Tables":
            table_name = item.data(0, Qt.ItemDataRole.UserRole) # Sadece metni değil, tam adı al
            if table_name:
                print(f"Veritabanı Gezgini: '{table_name}' tablosu aktive edildi.")
                self.table_activated.emit(table_name)

    def populate_tree(self, db_config, full_schema_data):
        """Ağaç görünümünü TÜM veritabanı şemasıyla (sözlük) doldurur."""
        self.clear_tree()

        db_type = db_config.get('type', 'Bilinmiyor')
        db_name = ""
        if db_type == 'access':
            db_name = os.path.basename(db_config.get('path', 'Access DB'))
        else:
            db_name = db_config.get('database', 'Bilinmeyen DB')
            
        db_item = QTreeWidgetItem(self.treeWidget_DB, [f"{db_name} ({db_type.capitalize()})"])
        db_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)) 

        tables_item = QTreeWidgetItem(db_item, ["Tables"])
        
        if not full_schema_data:
            tables_item.setText(0, "Tables (No tables found or schema empty)")
            self.treeWidget_DB.expandAll()
            return

        for table_name_full, column_names in sorted(full_schema_data.items()):
            table_item = QTreeWidgetItem(tables_item, [table_name_full])
            table_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)) 
            table_item.setData(0, Qt.ItemDataRole.UserRole, table_name_full) # Çift tıklama için tam adı sakla

            columns_item = QTreeWidgetItem(table_item, ["Columns"])
            
            if column_names: 
                for col_name in column_names:
                    col_item = QTreeWidgetItem(columns_item, [col_name])
                    col_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)) 
                    # Sürükleme için tam sütun adını sakla (örn: "dbo.ogrenciler.ad")
                    full_column_name = f"{table_name_full}.{col_name}"
                    col_item.setData(0, Qt.ItemDataRole.UserRole, full_column_name) 
            else:
                columns_item.setText(0, "Columns (Could not read)")

        self.treeWidget_DB.expandAll()

    def clear_tree(self):
        """Ağaç görünümünü temizler."""
        self.treeWidget_DB.clear()