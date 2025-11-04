# src/ui/db_explorer_window.py

import os
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidgetItem, QStyle # <-- QStyle BURAYA EKLENDİ
from PyQt6.QtCore import Qt

class DbExplorerWindow(QWidget):
    """
    Bağlı veritabanının yapısını (Tablolar, Sütunlar)
    bir ağaç görünümünde gösteren non-modal pencere.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_file_path = os.path.join(current_dir, 'db_explorer_window.ui')
        loadUi(ui_file_path, self)

        self.treeWidget_DB.setDragEnabled(True) 
        self.treeWidget_DB.setHeaderLabel("Veritabanı Yapısı") 
        self.treeWidget_DB.setHeaderHidden(False)

    
    def clear_tree(self):
        """Ağaç görünümünü temizler."""
        self.treeWidget_DB.clear()

    def populate_tree(self, db_config, full_schema_data):
        """
        Ağaç görünümünü TÜM veritabanı şemasıyla (sözlük) doldurur.
        """
        self.clear_tree()

        # 1. Ana Veritabanı Öğesi
        db_type = db_config.get('type', 'Bilinmiyor')
        db_name = ""
        if db_type == 'access':
            db_name = os.path.basename(db_config.get('path', 'Access DB'))
        else:
            db_name = db_config.get('database', 'Bilinmeyen DB')

        db_item = QTreeWidgetItem(self.treeWidget_DB, [f"{db_name} ({db_type.capitalize()})"])
        db_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)) 

        # 2. Tablolar Öğesi
        tables_item = QTreeWidgetItem(db_item, ["Tables"])

        if not full_schema_data:
            tables_item.setText(0, "Tables (No tables found or schema empty)")
            self.treeWidget_DB.expandAll()
            return

        # 3. Tüm Tabloları ve Sütunları Döngüye Al
        for table_name_full, column_names in sorted(full_schema_data.items()):

            # 3a. Tablo Öğesi
            table_item = QTreeWidgetItem(tables_item, [table_name_full])
            table_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)) 

            # 3b. Sütunlar Alt Öğesi
            columns_item = QTreeWidgetItem(table_item, ["Columns"])

            # 3c. Sütun Adlarını Ekle
            if column_names: 
                for col_name in column_names:
                    col_item = QTreeWidgetItem(columns_item, [col_name])
                    col_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)) 
                    col_item.setData(0, Qt.ItemDataRole.UserRole, f"[{col_name}]") 
            else:
                columns_item.setText(0, "Columns (Could not read)")

        self.treeWidget_DB.expandAll()

