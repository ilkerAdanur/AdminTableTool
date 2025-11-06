# src/ui/dynamic_table_tab.py

import os
import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
    QHeaderView, QMenu, QAbstractItemView, QMessageBox, QInputDialog,
    QLabel, QLineEdit
)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QAction

# Gerekli modüller (senin proje yapına göre)
from src.core.tasks import fetch_preview_data_task
from src.threading.workers import Worker

from PyQt6.QtWidgets import QHeaderView, QAbstractItemView
from PyQt6.QtCore import pyqtSignal, Qt

class DroppableHeaderView(QHeaderView):
    """
    Sadece başlık alanına sürükle-bırak yapılmasını sağlayan
    özel HeaderView sınıfı.
    """
    # [sütun_adları], hedef_index
    columns_dropped = pyqtSignal(list, int) 

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setAcceptDrops(True) # Sadece bu widget bırakmayı kabul eder
        self.setSectionsMovable(True) # Sütunları taşımaya izin ver

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """Bir öğe başlığın üzerine bırakıldığında."""
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        # Bırakılan yerin hangi sütun başlığına denk geldiğini bul
        drop_pos = event.position().toPoint()
        target_index = self.logicalIndexAt(drop_pos.x())

        # Eğer boş bir alana (son sütunun sağı) bırakıldıysa,
        # onu 'Yeni Sütun Ekle' (son sütun) olarak kabul et
        if target_index == -1:
            target_index = self.count() - 1 

        dropped_columns = drag_text.split('\n') 

        print(f"Header'a bırakıldı: {dropped_columns} -> {target_index} indeksine.")

        # Ana sekmeye (DynamicTableTab) sinyali gönder
        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()


class DynamicTableWidget(QTableWidget):
    """
    Sütun başlıklarına sürükle-bırak yapılabilen özel QTableWidget.
    """
    # Yeni bir sütun bırakıldığında ana widget'a sinyal gönder
    columns_dropped = pyqtSignal(list, int) # [sütun_adları], hedef_index
    
    def __init__(self, parent=None):
        
        super().__init__(parent)

        # --- YENİ: Sürüklemeyi özel header'a devret ---
        new_header = DroppableHeaderView(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(new_header)
        # -----------------------------------------------

        # Artık bu widget'ın kendisi drop'u kabul etmiyor
        # self.setAcceptDrops(True) # <-- BU SATIRI SİLİN

        # Başlangıçta "Yeni Sütun Ekle" sütununu oluştur
        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(["[Yeni Sütun Ekle]"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)


    def dragEnterEvent(self, event):
        # Sadece metin (sütun adı) içeren sürüklemeleri kabul et
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """
        Sütun başlığına bir öğe bırakıldığında tetiklenir.
        """
        drag_text = event.mimeData().text().strip()
        if not drag_text:
            event.ignore()
            return

        # Bırakılan yerin hangi sütun başlığına denk geldiğini bul
        drop_pos = event.position().toPoint()
        target_index = self.horizontalHeader().logicalIndexAt(drop_pos.x())

        # Gelen veri birden fazla sütun içerebilir (örn: \n ile ayrılmış)
        dropped_columns = drag_text.split('\n') 
        
        print(f"{dropped_columns} sütun(ları) {target_index} indeksine bırakıldı.")
        
        # Ana widget'a (DynamicTableTab) sinyali gönder
        self.columns_dropped.emit(dropped_columns, target_index)
        event.acceptProposedAction()



class DynamicTableTab(QWidget):
    """
    Yeni 'Veri Tablosu (Dönüştürme)' sekmesi.
    İçinde sürükle-bırak özellikli bir DynamicTableWidget barındırır.
    """
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window 
        self.defined_columns = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5) 

        # Sürükle-bırak özellikli özel tablomuz
        self.table = DynamicTableWidget(self)
        layout.addWidget(self.table)

        # --- DÜZELTME (Arayüz Sorunu): Spacer ekle ---
        # Bu, tablonun üste yapışmasını sağlar, ortalanmasını engeller
        layout.addStretch(1) 
        # ---------------------------------------------

        # --- Sinyalleri GÜNCELLE ---
        # Sinyal artık self.table'dan değil, self.table.horizontalHeader()'dan geliyor
        self.table.horizontalHeader().columns_dropped.connect(self.handle_columns_dropped)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_header_menu)

        # --- YENİ SİNYAL: Çift tıklayınca formül sorma ---
        self.table.horizontalHeader().doubleClicked.connect(self.edit_column_formula)

    def handle_columns_dropped(self, dropped_column_names, target_index):
        """
        (YENİ İŞ AKIŞI)
        Sütun(lar) başlığa bırakıldığında çalışır.
        Formül sormaz, doğrudan yeni bir sütun oluşturur.
        """

        # Hata ayıklaması (AttributeError'u önlemek için)
        if target_index < 0:
            print(f"Hata: Geçersiz hedef index ({target_index}). Bırakma işlemi iptal edildi.")
            return

        header_item = self.table.horizontalHeaderItem(target_index)
        if not header_item:
            # Bu durum, -1 index hatasını (AttributeError) çözer
            print(f"Hata: {target_index} indeksinde başlık öğesi bulunamadı (None).")
            return

        is_new_column_target = (header_item.text() == "[Yeni Sütun Ekle]")

        # --- YENİ MANTIĞI BURAYA EKLE ---

        if is_new_column_target:
            # 1. Yeni bir sütun oluşturuluyor

            # Formülü ve adı tahmin et
            # Sadece bir sütun bırakıldıysa (en yaygın senaryo)
            if len(dropped_column_names) == 1:
                source_col = dropped_column_names[0] # örn: "DEBILER.Kimlik"

                # Sütun adını tahmin et (örn: "Kimlik")
                guessed_name = source_col.split('.')[-1]
                # Formülü oluştur (örn: "[DEBILER.Kimlik]")
                formula = f"[{source_col}]"

                new_column_def = {
                    'name': guessed_name,
                    'type': 'formula', # Şimdilik hepsi formül
                    'formula': formula,
                    'sources': dropped_column_names # Ham kaynakları sakla
                }

            # Birden fazla sütun bırakıldıysa (Toplama)
            else:
                guessed_name = "Hesaplama"
                formula = " + ".join([f"[{col}]" for col in dropped_column_names])

                new_column_def = {
                    'name': guessed_name,
                    'type': 'formula',
                    'formula': formula,
                    'sources': dropped_column_names
                }

            # Yeni sütun tanımını hafızaya ekle
            # [Yeni Sütun Ekle]'den ÖNCE eklemeliyiz
            self.defined_columns.insert(target_index, new_column_def)

        else:
            # 2. Mevcut bir sütunun üzerine bırakılıyor
            # TODO: Sütunları birleştirme mantığı buraya eklenebilir
            # Şimdilik: "Bu sütunu güncellemek istediğinizden emin misiniz?"
            print(f"'{dropped_column_names[0]}' mevcut sütunun ({target_index}) üzerine bırakıldı. (Henüz desteklenmiyor)")
            return

        # Tablo arayüzünü güncelle
        self.refresh_table_headers()

        # TODO: Worker'ı tetikleyip tabloyu ilk 10 satır veriyle doldur (Önizleme)



    def refresh_table_headers(self):
        """
        Hafızadaki 'self.defined_columns' listesine göre
        tablonun başlıklarını (headers) yeniden oluşturur.
        """
        self.table.setColumnCount(len(self.defined_columns) + 1) # Tanımlananlar + [Yeni Sütun Ekle]
        
        header_labels = []
        for i, col_def in enumerate(self.defined_columns):
            header_labels.append(col_def['name'])
            # TODO: Belki başlığın tooltip'ine formülü ekleyebiliriz
            
        header_labels.append("[Yeni Sütun Ekle]") # En sona 'Yeni' sütununu ekle
        
        self.table.setHorizontalHeaderLabels(header_labels)
        
        # Son sütun hariç diğerlerini genişlet
        for i in range(len(self.defined_columns)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        # Son sütunu ([Yeni Sütun Ekle]) içeriğe sığdır
        self.table.horizontalHeader().setSectionResizeMode(len(self.defined_columns), QHeaderView.ResizeMode.ResizeToContents)

    def open_header_menu(self, position):
        """Sütun başlığına sağ tıklandığında menü açar."""
        index = self.table.horizontalHeader().logicalIndexAt(position)
        if index < 0 or index >= len(self.defined_columns): # [Yeni Sütun Ekle]'ye veya boşa tıklandıysa
            return 
            
        menu = QMenu(self)
        
        # TODO: 'Formülü Düzenle' eylemi
        edit_action = QAction("Formülü Düzenle", self)
        edit_action.triggered.connect(lambda: self.edit_column_formula(index))
        menu.addAction(edit_action)
        
        # 'Sütunu Sil' eylemi
        delete_action = QAction("Sütunu Sil", self)
        delete_action.triggered.connect(lambda: self.delete_column(index))
        menu.addAction(delete_action)
        
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))

    def edit_column_formula(self, index): # <-- 'index' parametresi eklendi
        """Bir sütunun formülünü düzenler (Başlığa çift tıklandığında)."""

        if index < 0 or index >= len(self.defined_columns): # [Yeni Sütun Ekle]'ye tıklandıysa
            return

        col_def = self.defined_columns[index]

        # Formülü sormadan önce 'tip'ini kontrol et
        col_type = col_def.get('type', 'formula') # Varsayılan 'formula'

        if col_type != 'formula':
            QMessageBox.information(self, "Düzenlenemez", "Bu sütun tipi (örn: ham veri) formül düzenlemeyi desteklemiyor.")
            return

        # Mevcut adı ve formülü al
        current_name = col_def['name']
        current_formula = col_def.get('formula', f"[{col_def.get('sources', ['HATA'])[0]}]")

        # Adı düzenle
        new_name, ok = QInputDialog.getText(self, "Sütun Adını Düzenle",
                                            "Sütun adını girin:",
                                            QLineEdit.EchoMode.Normal,
                                            current_name)
        if not (ok and new_name):
            return # İptal edildi

        # Formülü düzenle
        new_formula, ok = QInputDialog.getText(self, "Formülü Düzenle",
                                            f"'{new_name}' için formülü girin:\n(Ham sütun adlarını [ ] içinde kullanın)",
                                            QLineEdit.EchoMode.Normal,
                                            current_formula)
        if not (ok and new_formula):
            return # İptal edildi

        # Tanımı güncelle
        self.defined_columns[index]['name'] = new_name
        self.defined_columns[index]['formula'] = new_formula

        # Tablo başlığını yenile
        self.refresh_table_headers()
        # TODO: Tablodaki veriyi de yenile

    def delete_column(self, index):
        """Bir sütunu taslaktan kaldırır."""
        if index < 0 or index >= len(self.defined_columns):
            return
        
        col_def = self.defined_columns[index]
        reply = QMessageBox.question(self, "Sütunu Sil",
                                     f"'{col_def['name']}' sütununu taslaktan kaldırmak istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.defined_columns[index]
            self.refresh_table_headers()
            # TODO: Tablodaki veriyi de yenile