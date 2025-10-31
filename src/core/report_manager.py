# src/core/report_manager.py

"""
Kaydedilmiş (Excel) raporları yönetmek için yardımcı fonksiyonlar.
"""

import os
from datetime import datetime

REPORT_DIR = r"C:\rapor\excel"

def get_saved_report_dates():
    """
    C:\rapor\excel klasörünü tarar ve bulunan YIL\GUN_AY klasörlerini
    sözlük olarak (ComboBox metni -> Klasör yolu) döndürür.
    """
    print("Kaydedilmiş Excel raporları taranıyor...")
    
    report_folders = {} # "GUN_AY_YIL" -> "tam_klasor_yolu"
    
    if not os.path.exists(REPORT_DIR):
        print(f"Rapor klasörü bulunamadı: {REPORT_DIR}")
        return {}

    try:
        for yil_klasor in os.listdir(REPORT_DIR):
            yil_yolu = os.path.join(REPORT_DIR, yil_klasor)
            if os.path.isdir(yil_yolu) and yil_klasor.isdigit():
                
                for gun_ay_klasor in os.listdir(yil_yolu):
                    gun_ay_yolu = os.path.join(yil_yolu, gun_ay_klasor)
                    if os.path.isdir(gun_ay_yolu) and '_' in gun_ay_klasor:
                        
                        # Klasörün içinde en az bir .xlsx dosyası varsa
                        if any(f.endswith('.xlsx') for f in os.listdir(gun_ay_yolu)):
                            combo_text = f"{gun_ay_klasor}_{yil_klasor}"
                            report_folders[combo_text] = gun_ay_yolu
                            
        return report_folders
        
    except Exception as e:
        print(f"HATA: Kayıtlı raporlar taranırken hata: {e}")
        return {}