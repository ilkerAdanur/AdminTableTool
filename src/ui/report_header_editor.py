# src/ui/report_header_editor.py

import os
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem,
    QGraphicsItem, QMenu, QInputDialog, QFileDialog, QGraphicsRectItem,
    QFontDialog, QColorDialog
)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QAction, QCursor

class ResizablePixmapSizeHandle(QGraphicsRectItem):
    """Resimlerin köşelerindeki boyutlandırma tutamaçları."""
    def __init__(self, parent, cursor_shape, position_flags):
        super().__init__(0, 0, 10, 10, parent)
        self.setBrush(QColor("black"))
        self.setCursor(QCursor(cursor_shape))
        self.position_flags = position_flags # (top, bottom, left, right)
        self.parent_item = parent
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, event):
        self.parent_item.set_resizing(True, self.position_flags)
        super().mousePressEvent(event)

class DraggableImageItem(QGraphicsPixmapItem):
    """Hareket ettirilebilir ve boyutlandırılabilir resim nesnesi."""
    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        
        self.original_pixmap = pixmap 
        
        self.handles = []
        self.is_resizing = False
        self.resize_direction = None
        self._create_handles()
        self._update_handles()

    def _create_handles(self):
        # Sağ-Alt Köşe Tutamacı
        handle = ResizablePixmapSizeHandle(self, Qt.CursorShape.SizeFDiagCursor, (False, True, False, True))
        self.handles.append(handle)

    def _update_handles(self):
        rect = self.boundingRect()
        # Sağ alt köşe
        self.handles[0].setPos(rect.width() - 10, rect.height() - 10)

    def set_resizing(self, resizing, direction):
        self.is_resizing = resizing
        self.resize_direction = direction

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            pos = event.pos()
            new_width = int(pos.x())
            new_height = int(pos.y())
            
            if new_width < 20: new_width = 20
            if new_height < 20: new_height = 20
            
            scaled_pixmap = self.original_pixmap.scaled(
                new_width, 
                new_height, 
                Qt.AspectRatioMode.IgnoreAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)
            
            self._update_handles()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_resizing = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        delete_action = menu.addAction("Sil")
        action = menu.exec(event.screenPos())
        if action == delete_action:
            self.scene().removeItem(self)

class DraggableTextItem(QGraphicsTextItem):
    """Hareket ettirilebilir ve düzenlenebilir metin nesnesi."""
    def __init__(self, text):
        super().__init__(text)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setDefaultTextColor(QColor("black"))
        self.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)

    def contextMenuEvent(self, event):
        menu = QMenu()
        font_action = menu.addAction("Yazı Tipi ve Boyutu...") 
        color_action = menu.addAction("Yazı Rengi...")         
        delete_action = menu.addAction("Sil")
        
        action = menu.exec(event.screenPos())
        
        if action == delete_action:
            self.scene().removeItem(self)
            
        elif action == font_action:
            current_font = self.font()
            # --- DÜZELTME BURADA: (font, ok) sırasında alınmalı ---
            new_font, ok = QFontDialog.getFont(current_font)
            if ok:
                self.setFont(new_font)
        
        elif action == color_action:
            current_color = self.defaultTextColor()
            new_color = QColorDialog.getColor(current_color, title="Yazı Rengini Seç")
            if new_color.isValid():
                self.setDefaultTextColor(new_color)

class HeaderEditorView(QGraphicsView):
    """
    Rapor başlığı için düzenleme alanı (Canvas).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.scene.setSceneRect(0, 0, 1000, 200) 
        self.setFixedSize(1000, 220) 
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAcceptDrops(True)
        
        self.setBackgroundBrush(QColor("white"))
        
        self.placeholder = self.scene.addText("Resim sürükleyin veya Sağ Tık ile metin ekleyin...")
        self.placeholder.setDefaultTextColor(QColor("gray"))
        self.placeholder.setPos(300, 80)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        if self.placeholder:
            self.scene.removeItem(self.placeholder)
            self.placeholder = None

        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                pixmap = QPixmap(file_path)
                pixmap = pixmap.scaledToHeight(100, Qt.TransformationMode.SmoothTransformation)
                
                item = DraggableImageItem(pixmap)
                item.setPos(event.position().x(), event.position().y())
                self.scene.addItem(item)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            super().contextMenuEvent(event)
            return

        menu = QMenu()
        add_text = menu.addAction("Başlık / Yazı Ekle")
        change_bg = menu.addAction("Arka Plan Rengi Seç...") 
        clear_all = menu.addAction("Temizle")
        
        action = menu.exec(event.globalPos())
        
        if action == add_text:
            if self.placeholder:
                self.scene.removeItem(self.placeholder)
                self.placeholder = None
            text, ok = QInputDialog.getText(self, "Yazı Ekle", "Metin:")
            if ok and text:
                t_item = DraggableTextItem(text)
                t_item.setPos(event.pos().x(), event.pos().y())
                self.scene.addItem(t_item)
                
        elif action == change_bg:
            current_color = self.backgroundBrush().color()
            new_color = QColorDialog.getColor(current_color, title="Arka Plan Rengini Seç")
            if new_color.isValid():
                self.setBackgroundBrush(new_color)
                
        elif action == clear_all:
            self.scene.clear()

    def get_header_image(self):
        """
        Sahnenin o anki halini, ARKA PLAN RENGİYLE BİRLİKTE tek bir resim yapar.
        """
        # Tutamaçları gizlemek için seçimi kaldır
        self.scene.clearSelection()
        
        image = QPixmap(self.scene.sceneRect().size().toSize())
        
        # --- DÜZELTME: Şeffaf yerine sahnenin arka plan rengini al ---
        bg_brush = self.backgroundBrush()
        # Eğer bir renk atanmışsa o rengi kullan, yoksa beyaz yap
        bg_color = bg_brush.color() if bg_brush.style() != Qt.BrushStyle.NoBrush else QColor("white")
        image.fill(bg_color)
        # -------------------------------------------------------------
        
        painter = QPainter(image)
        self.scene.render(painter)
        painter.end()
        return image