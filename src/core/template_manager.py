# src/core/template_manager.py

import os
import json
from PyQt6.QtWidgets import QFileDialog, QMessageBox

# Taslakların kaydedileceği varsayılan klasör
TEMPLATE_DIR = r"C:\rapor\taslaklar" # Doğrudan mutlak yol # Ana dizindeki rapor/taslaklar

def _ensure_template_dir():
    """Taslak klasörünün var olduğundan emin olur, yoksa oluşturur."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

def save_template(template_name, template_data, parent_widget=None):
    """
    Verilen taslak verisini (bir sözlük olmalı) JSON dosyası olarak kaydeder.
    Args:
        template_name (str): Kaydedilecek dosyanın adı (uzantısız).
        template_data (dict): Kaydedilecek taslak ayarları (sütunlar, formüller vb.).
        parent_widget: Hata mesajları için QDialog gibi bir üst pencere.
    Returns:
        bool: Başarılıysa True, değilse False.
    """
    _ensure_template_dir()

    # Dosya adından geçersiz karakterleri temizler 
    safe_name = "".join(c for c in template_name if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_name:
        QMessageBox.warning(parent_widget, "Geçersiz Ad", "Lütfen geçerli bir taslak adı girin.")
        return False

    file_path = os.path.join(TEMPLATE_DIR, f"{safe_name}.json")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # json.dump ile sözlüğü dosyaya yaz (indent=4 okunabilirliği artırır)
            json.dump(template_data, f, ensure_ascii=False, indent=4)
        print(f"Taslak başarıyla kaydedildi: {file_path}")
        return True
    except Exception as e:
        print(f"HATA: Taslak kaydedilemedi: {e}")
        QMessageBox.critical(parent_widget, "Kayıt Hatası", f"Taslak kaydedilirken bir hata oluştu:\n{e}")
        return False

def load_template(template_name=None, parent_widget=None):
    """
    Belirtilen isimdeki taslak JSON dosyasını yükler ve içeriğini sözlük olarak döndürür.
    Eğer template_name verilmezse, dosya seçim diyaloğu açar.
    Args:
        template_name (str, optional): Yüklenecek dosyanın adı (uzantısız).
        parent_widget: Dosya diyaloğu veya hata mesajları için üst pencere.
    Returns:
        dict or None: Başarılıysa taslak verisi, değilse None.
    """
    _ensure_template_dir()
    file_path = ""

    if template_name:
         # Dosya adından geçersiz karakterleri temizle
        safe_name = "".join(c for c in template_name if c.isalnum() or c in ('_', '-')).rstrip()
        temp_path = os.path.join(TEMPLATE_DIR, f"{safe_name}.json")
        if os.path.exists(temp_path):
            file_path = temp_path
        else:
             QMessageBox.warning(parent_widget, "Bulunamadı", f"'{template_name}' adında bir taslak bulunamadı.")
             return None
    else:
        # İsim verilmediyse, kullanıcıya seçtir
        selected_path, _ = QFileDialog.getOpenFileName(
            parent_widget,
            "Rapor Taslağı Yükle",
            TEMPLATE_DIR, # Varsayılan klasör
            "JSON Dosyaları (*.json);;Tüm Dosyalar (*.*)"
        )
        if selected_path:
            file_path = selected_path
        else:
            return None # Kullanıcı iptal etti

    if not file_path:
         return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        print(f"Taslak başarıyla yüklendi: {file_path}")

        # Yüklenen dosyanın adını da (uzantısız) veriye ekleyebiliriz (isteğe bağlı)
        loaded_name = os.path.splitext(os.path.basename(file_path))[0]
        template_data['_template_name'] = loaded_name 

        return template_data
    except json.JSONDecodeError as e:
         print(f"HATA: Taslak dosyası bozuk (JSON): {e}")
         QMessageBox.critical(parent_widget, "Yükleme Hatası", f"Taslak dosyası okunamadı (Bozuk JSON):\n{file_path}\n{e}")
         return None
    except Exception as e:
        print(f"HATA: Taslak yüklenemedi: {e}")
        QMessageBox.critical(parent_widget, "Yükleme Hatası", f"Taslak yüklenirken bir hata oluştu:\n{e}")
        return None

def get_available_templates():
    """
    Taslak klasöründeki tüm .json dosyalarının adlarını (uzantısız) bir liste olarak döndürür.
    """
    _ensure_template_dir()
    try:
        templates = [
            os.path.splitext(f)[0] # Sadece dosya adını al (uzantısız)
            for f in os.listdir(TEMPLATE_DIR) 
            if f.endswith('.json') and os.path.isfile(os.path.join(TEMPLATE_DIR, f))
        ]
        templates.sort() # Alfabetik sırala
        return templates
    except Exception as e:
        print(f"HATA: Taslak listesi alınamadı: {e}")
        return []