from sqlalchemy import create_engine, inspect
import pandas as pd

try:
    import python_calamine
    EXCEL_ENGINE = "calamine"
    print("Hızlı Excel motoru (python-calamine) bulundu.")
except ImportError:
    EXCEL_ENGINE = "openpyxl" # Calamine yoksa varsayılana dön
    print("UYARI: 'python-calamine' kütüphanesi bulunamadı. pip install python-calamine")
    print("Hızlı Excel okuma için varsayılan (yavaş) motor 'openpyxl' kullanılacak.")



# --- YENİ GÖREV: EXCEL OKUMA (Calamine ile) ---
def _task_run_excel_load(self, tam_yol):
    """(Worker) Excel okuma işi (Calamine motoruyla)"""
    print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
    df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
    print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
    return df
