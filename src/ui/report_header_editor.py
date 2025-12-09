# src/ui/report_header_editor.py

import os
import base64
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem,
    QGraphicsItem, QMenu, QInputDialog, QFileDialog, QGraphicsRectItem,
    QFontDialog, QColorDialog
)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QAction, QCursor

class ResizablePixmapSizeHandle(QGraphicsRectItem):
    """Resimlerin köşelerindeki boyutlandırma tutamaçları."""
    def __init__(self, parent):
        super().__init__(0, 0, 10, 10, parent)
        self.setBrush(QColor("black"))
        self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        self.parent_item = parent
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, event):
        pass # Tıklamayı yut, parent'a gitmesin

    def mouseMoveEvent(self, event):
        new_pos = self.mapToParent(event.pos())
        self.parent_item.resize_image(new_pos.x(), new_pos.y())

class DraggableImageItem(QGraphicsPixmapItem):
    """Hareket ettirilebilir ve boyutlandırılabilir resim nesnesi."""
    def __init__(self, pixmap, on_change=None):
        super().__init__(pixmap)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.original_pixmap = pixmap 
        self.handle = ResizablePixmapSizeHandle(self)
        self._update_handle_position()
        
        self.on_change = on_change # Değişiklik olduğunda çağrılacak fonksiyon
        self._start_pos = None
        self._did_resize = False

    def _update_handle_position(self):
        rect = self.boundingRect()
        self.handle.setPos(rect.width() - 10, rect.height() - 10)

    def resize_image(self, width, height):
        if width < 20: width = 20
        if height < 20: height = 20
        
        scaled_pixmap = self.original_pixmap.scaled(
            int(width), int(height), 
            Qt.AspectRatioMode.IgnoreAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled_pixmap)
        self._update_handle_position()
        self._did_resize = True

    def mousePressEvent(self, event):
        self._start_pos = self.pos() # Başlangıç pozisyonunu kaydet
        self._did_resize = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Eğer pozisyon değiştiyse veya boyut değiştiyse sinyal ver
        if self.on_change:
            if self.pos() != self._start_pos or self._did_resize:
                self.on_change()

    def contextMenuEvent(self, event):
        menu = QMenu()
        delete_action = menu.addAction("Sil")
        action = menu.exec(event.screenPos())
        if action == delete_action:
            self.scene().removeItem(self)
            if self.on_change: self.on_change()

    def to_dict(self):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.original_pixmap.save(buffer, "PNG")
        base64_data = buffer.data().toBase64().data().decode()
        return {
            "type": "image",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "width": self.pixmap().width(),
            "height": self.pixmap().height(),
            "image_data": base64_data
        }

class DraggableTextItem(QGraphicsTextItem):
    """Hareket ettirilebilir metin."""
    def __init__(self, text, on_change=None):
        super().__init__(text)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setDefaultTextColor(QColor("black"))
        self.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        
        self.on_change = on_change
        self._start_pos = None

    def mousePressEvent(self, event):
        self._start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.on_change and self.pos() != self._start_pos:
            self.on_change()

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFocus()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        super().focusOutEvent(event)
        if self.on_change: self.on_change()

    def contextMenuEvent(self, event):
        menu = QMenu()
        font_action = menu.addAction("Yazı Tipi ve Boyutu...") 
        color_action = menu.addAction("Yazı Rengi...")         
        delete_action = menu.addAction("Sil")
        
        action = menu.exec(event.screenPos())
        
        changed = False
        if action == delete_action:
            self.scene().removeItem(self)
            changed = True
        elif action == font_action:
            current_font = self.font()
            font, ok = QFontDialog.getFont(current_font)
            if ok: 
                self.setFont(font)
                changed = True
        elif action == color_action:
            current_color = self.defaultTextColor()
            new_color = QColorDialog.getColor(current_color, title="Yazı Rengini Seç")
            if new_color.isValid(): 
                self.setDefaultTextColor(new_color)
                changed = True
        
        if changed and self.on_change:
            self.on_change()

    def to_dict(self):
        return {
            "type": "text",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "text": self.toPlainText(),
            "color": self.defaultTextColor().name(),
            "font_family": self.font().family(),
            "font_size": self.font().pointSize(),
            "font_bold": self.font().bold(),
            "font_italic": self.font().italic()
        }

class HeaderEditorView(QGraphicsView):
    """Rapor başlığı için düzenleme alanı (Canvas)."""
    
    # --- YENİ: Sadece gerçek değişikliklerde tetiklenecek sinyal ---
    headerChanged = pyqtSignal() 
    
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
        self.placeholder.setFont(QFont("Arial", 10))

    def _on_item_changed(self):
        """Öğelerden gelen değişiklik sinyalini dışarı ilet."""
        self.headerChanged.emit()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event): event.accept()

    def dropEvent(self, event):
        if self.placeholder:
            self.scene.removeItem(self.placeholder)
            self.placeholder = None

        urls = event.mimeData().urls()
        changed = False
        for url in urls:
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                pixmap = QPixmap(file_path)
                pixmap = pixmap.scaledToHeight(100, Qt.TransformationMode.SmoothTransformation)
                
                # Değişiklik bildirimini (self._on_item_changed) öğeye veriyoruz
                item = DraggableImageItem(pixmap, on_change=self._on_item_changed)
                item.setPos(event.position().x(), event.position().y())
                self.scene.addItem(item)
                changed = True
        
        if changed:
            self.headerChanged.emit()

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
                # Değişiklik bildirimini veriyoruz
                t_item = DraggableTextItem(text, on_change=self._on_item_changed)
                t_item.setPos(event.pos().x(), event.pos().y())
                self.scene.addItem(t_item)
                self.headerChanged.emit()
                
        elif action == change_bg:
            current_color = self.backgroundBrush().color()
            new_color = QColorDialog.getColor(current_color, title="Arka Plan Rengini Seç")
            if new_color.isValid(): 
                self.setBackgroundBrush(new_color)
                self.headerChanged.emit()
                
        elif action == clear_all:
            self.scene.clear()
            self.headerChanged.emit()

    def get_header_image(self):
        self.scene.clearSelection()
        image = QPixmap(self.scene.sceneRect().size().toSize())
        bg_brush = self.backgroundBrush()
        bg_color = bg_brush.color() if bg_brush.style() != Qt.BrushStyle.NoBrush else QColor("white")
        image.fill(bg_color)
        painter = QPainter(image)
        self.scene.render(painter)
        painter.end()
        return image

    def get_scene_data(self):
        data = {
            "background_color": self.backgroundBrush().color().name(),
            "items": []
        }
        for item in self.scene.items(Qt.SortOrder.AscendingOrder):
            if isinstance(item, DraggableImageItem):
                data["items"].append(item.to_dict())
            elif isinstance(item, DraggableTextItem):
                data["items"].append(item.to_dict())
        return data

    def load_scene_data(self, data):
        self.scene.clear()
        self.placeholder = None 

        bg_color_name = data.get("background_color", "#FFFFFF")
        self.setBackgroundBrush(QColor(bg_color_name))

        items = data.get("items", [])
        for item_data in items:
            item_type = item_data.get("type")
            
            if item_type == "text":
                # Değişiklik bildirimini veriyoruz
                text_item = DraggableTextItem(item_data.get("text", ""), on_change=self._on_item_changed)
                text_item.setPos(item_data.get("x", 0), item_data.get("y", 0))
                
                color = QColor(item_data.get("color", "black"))
                text_item.setDefaultTextColor(color)
                
                font_family = item_data.get("font_family", "Arial")
                if "8514oem" in font_family.lower() or not font_family:
                    font_family = "Arial"
                
                font = QFont()
                font.setFamily(font_family)
                font.setPointSize(item_data.get("font_size", 14))
                font.setBold(item_data.get("font_bold", False))
                font.setItalic(item_data.get("font_italic", False))
                text_item.setFont(font)
                
                self.scene.addItem(text_item)

            elif item_type == "image":
                b64_data = item_data.get("image_data", "")
                if b64_data:
                    byte_data = QByteArray.fromBase64(b64_data.encode())
                    pixmap = QPixmap()
                    pixmap.loadFromData(byte_data)
                    
                    target_w = item_data.get("width", 100)
                    target_h = item_data.get("height", 100)
                    
                    # Değişiklik bildirimini veriyoruz
                    img_item = DraggableImageItem(pixmap, on_change=self._on_item_changed) 
                    img_item.resize_image(target_w, target_h)
                    img_item.setPos(item_data.get("x", 0), item_data.get("y", 0))
                    
                    self.scene.addItem(img_item)