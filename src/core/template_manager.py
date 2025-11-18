# src/core/template_manager.py

import os
import json
import json.decoder  # Hata yakalama için eklendi

# --- KALDIRILDI ---
# from PyQt6.QtWidgets import QFileDialog, QMessageBox

# Taslakların kaydedileceği varsayılan klasör
TEMPLATE_DIR = r"C:\rapor\taslaklar" # Doğrudan mutlak yol # Ana dizindeki rapor/taslaklar

def _ensure_template_dir():
    """Taslak klasörünün var olduğundan emin olur, yoksa oluşturur."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

def save_template(template_name, template_data):
    """
    Verilen taslak verisini (bir sözlük olmalı) JSON dosyası olarak kaydeder.
    
    Args:
        template_name (str): Kaydedilecek dosyanın adı (uzantısız).
        template_data (dict): Kaydedilecek taslak ayarları.
    
    Raises:
        ValueError: Taslak adı geçersizse.
        IOError: Dosya yazma sırasında bir hata oluşursa.
    """
    _ensure_template_dir()

    safe_name = "".join(c for c in template_name if c.isalnum() or c in ('_', '-')).rstrip()
    if not safe_name:
        # --- DEĞİŞİKLİK ---
        # QMessageBox göstermek yerine, bir hata fırlatıyoruz.
        raise ValueError("Geçersiz Ad: Lütfen geçerli bir taslak adı girin.")

    file_path = os.path.join(TEMPLATE_DIR, f"{safe_name}.json")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(template_data, f, ensure_ascii=False, indent=4)
        print(f"Taslak başarıyla kaydedildi: {file_path}")
        # Başarılı olunca return True'ye gerek yok, hatasız bitmesi yeterli.
    
    except Exception as e:
        print(f"HATA: Taslak kaydedilemedi: {e}")
        # --- DEĞİŞİKLİK ---
        # QMessageBox göstermek yerine, bir hata fırlatıyoruz.
        raise IOError(f"Kayıt Hatası: Taslak kaydedilirken bir hata oluştu: {e}")

def load_template(template_name):
    """
    Belirtilen isimdeki taslak JSON dosyasını yükler ve içeriğini sözlük olarak döndürür.
    
    Args:
        template_name (str): Yüklenecek dosyanın adı (uzantısız).
        
    Returns:
        dict: Başarılıysa taslak verisi.
        
    Raises:
        ValueError: Taslak adı sağlanmazsa.
        FileNotFoundError: Taslak dosyası bulunamazsa.
        json.JSONDecodeError: Dosya bozuksa (JSON hatası).
        IOError: Dosya okunurken başka bir hata olursa.
    """
    _ensure_template_dir()
    
    if not template_name:
        raise ValueError("load_template fonksiyonu için bir 'template_name' (taslak adı) sağlanmadı.")

    safe_name = "".join(c for c in template_name if c.isalnum() or c in ('_', '-')).rstrip()
    file_path = os.path.join(TEMPLATE_DIR, f"{safe_name}.json")

    if not os.path.exists(file_path):
        # --- DEĞİŞİKLİK ---
        raise FileNotFoundError(f"Bulunamadı: '{template_name}' adında bir taslak bulunamadı.")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        print(f"Taslak başarıyla yüklendi: {file_path}")

        loaded_name = os.path.splitext(os.path.basename(file_path))[0]
        template_data['_template_name'] = loaded_name 
        return template_data
    
    except json.JSONDecodeError as e:
        print(f"HATA: Taslak dosyası bozuk (JSON): {e}")
        # --- DEĞİŞİKLİK ---
        raise json.JSONDecodeError(f"Yükleme Hatası: Taslak dosyası okunamadı (Bozuk JSON):\n{file_path}\n{e.msg}", e.doc, e.pos)
    
    except Exception as e:
        print(f"HATA: Taslak yüklenemedi: {e}")
        # --- DEĞİŞİKLİK ---
        raise IOError(f"Yükleme Hatası: Taslak yüklenirken bilinmeyen bir hata oluştu: {e}")

def load_template_from_path(file_path):
    """
    (YENİ YARDIMCI FONKSİYON)
    QFileDialog'dan gelen, tam dosya yoluna sahip bir taslağı yükler.
    """
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Dosya yolu bulunamadı veya geçersiz: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        print(f"Taslak başarıyla yüklendi: {file_path}")

        loaded_name = os.path.splitext(os.path.basename(file_path))[0]
        template_data['_template_name'] = loaded_name 
        return template_data
    
    except json.JSONDecodeError as e:
        print(f"HATA: Taslak dosyası bozuk (JSON): {e}")
        raise json.JSONDecodeError(f"Yükleme Hatası: Taslak dosyası okunamadı (Bozuk JSON):\n{file_path}\n{e.msg}", e.doc, e.pos)
    
    except Exception as e:
        print(f"HATA: Taslak yüklenemedi: {e}")
        raise IOError(f"Yükleme Hatası: Taslak yüklenirken bilinmeyen bir hata oluştu: {e}")


def get_available_templates():
    """
    Taslak klasöründeki tüm .json dosyalarının adlarını (uzantısız) bir liste olarak döndürür.
    (Bu fonksiyonda değişiklik gerekmiyor, UI bağımlılığı yoktu.)
    """
    _ensure_template_dir()
    try:
        templates = [
            os.path.splitext(f)[0] 
            for f in os.listdir(TEMPLATE_DIR) 
            if f.endswith('.json') and os.path.isfile(os.path.join(TEMPLATE_DIR, f))
        ]
        templates.sort() 
        return templates
    except Exception as e:
        print(f"HATA: Taslak listesi alınamadı: {e}")
        return []