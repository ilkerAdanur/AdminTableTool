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

    def populate_tree(self, db_config, target_table, column_names):
        """
        Ağaç görünümünü gelen veritabanı bilgileriyle doldurur.
        """
        # --- HATA AYIKLAMA İÇİN PRINT (KALABİLİR) ---
        print("\n--- DbExplorer: populate_tree çağrıldı ---")
        try:
             print(f"  db_config: {db_config.get('type')}")
        except:
             print(f"  db_config: (Yazdırılamadı)")
        print(f"  target_table: {target_table}")
        print(f"  column_names (ilk 5): {column_names[:5] if column_names else 'BOŞ'}")
        print("------------------------------------------")
        
        self.clear_tree() 

        # 1. Ana Veritabanı Öğesi
        db_type = db_config.get('type', 'Bilinmiyor')
        db_name = ""
        if db_type == 'access':
            db_name = os.path.basename(db_config.get('path', 'Access DB'))
        else:
            db_name = db_config.get('database', 'Bilinmeyen DB')
            
        db_item = QTreeWidgetItem(self.treeWidget_DB, [f"{db_name} ({db_type.capitalize()})"])
        
        # --- DÜZELTME: Doğru enum kullanıldı (getattr(..., 0) kaldırıldı) ---
        db_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)) 

        # 2. Tablolar Öğesi
        tables_item = QTreeWidgetItem(db_item, ["Tables"])
        
        # 3. Seçili Tablo Öğesi
        table_item = QTreeWidgetItem(tables_item, [target_table])
        
        # --- DÜZELTME: Doğru enum kullanıldı ---
        table_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)) 

        # 4. Sütunlar Öğesi
        columns_item = QTreeWidgetItem(table_item, ["Columns"])
        
        # 5. Sütun Adlarını Ekle
        if column_names: 
            for col_name in column_names:
                col_item = QTreeWidgetItem(columns_item, [col_name])
                
                # --- DÜZELTME: Doğru enum kullanıldı ---
                col_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)) 
                col_item.setData(0, Qt.ItemDataRole.UserRole, f"[{col_name}]") 

        self.treeWidget_DB.expandAll()

    def clear_tree(self):
        """Ağaç görünümünü temizler."""
        self.treeWidget_DB.clear()