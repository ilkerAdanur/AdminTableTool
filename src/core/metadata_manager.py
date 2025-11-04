# src/core/metadata_manager.py

import os
import json
import datetime

# Yorumların saklanacağı metaveri dosyasının adı
METADATA_FILENAME = "report_metadata.json"

def save_report_comment(file_path, comment, user="default_user"):
    """
    Bir rapor dosyasının (Excel/PDF) yanına, aynı klasördeki 
    metadata.json dosyasına bir yorum kaydeder.

    Args:
        file_path (str): Oluşturulan Excel/PDF dosyasının tam yolu.
        comment (str): Kullanıcının girdiği yorum metni.
        user (str): Yorumu yapan kullanıcı (gelecekteki admin paneli için).
    """
    try:
        folder_path = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        metadata_path = os.path.join(folder_path, METADATA_FILENAME)

        # 1. Mevcut metadata dosyasını oku (yoksa boş sözlük oluştur)
        data = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {} # Bozuksa veya boşsa sıfırla

        # 2. Bu dosyayla ilgili yorumlar listesi (yoksa oluştur)
        if file_name not in data:
            data[file_name] = []

        # 3. Yeni yorumu, zaman damgası ve kullanıcıyla birlikte ekle
        data[file_name].append({
            "user": user,
            "timestamp": datetime.datetime.now().isoformat(),
            "comment": comment
        })

        # 4. Metadata dosyasını geri yaz
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"Yorum '{file_name}' için başarıyla kaydedildi.")
        return True

    except Exception as e:
        print(f"HATA: Yorum kaydedilemedi: {e}")
        return False

def load_report_comments(file_path):
    """
    Bir rapor dosyasının yanındaki metadata.json dosyasından
    o dosyaya ait yorum listesini okur.
    """
    try:
        folder_path = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        metadata_path = os.path.join(folder_path, METADATA_FILENAME)

        if not os.path.exists(metadata_path):
            return [] 

        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data.get(file_name, [])

    except Exception as e:
        print(f"HATA: Yorumlar yüklenemedi: {e}")
        return []
   



