# src/core/database.py

import urllib.parse
from sqlalchemy import create_engine, inspect
import pandas as pd

# Calamine motorunu kontrol et
try:
    import python_calamine
    EXCEL_ENGINE = "calamine"
except ImportError:
    EXCEL_ENGINE = "openpyxl"

def get_database_tables(db_path):
    """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerinin listesini döndürür."""
    print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {db_path}")

    connection_string = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"Dbq={db_path};"
    )
    quoted_connection_string = urllib.parse.quote_plus(connection_string)
    engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")

    # SQLAlchemy'nin 'inspect' özelliğini kullanarak tablo listesini al
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # Access'in sistem tablolarını ("MSys...") filtrele
    user_tables = [name for name in table_names if not name.startswith("MSys")]

    print(f"Çalışan iş parçacığı: Bulunan tablolar: {user_tables}")
    return user_tables

def run_database_query(db_path, target_table, baslangic_tarihi, bitis_tarihi):
    """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""

    print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}, Tarih: {baslangic_tarihi} - {bitis_tarihi}")

    connection_string = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"Dbq={db_path};"
    )
    quoted_connection_string = urllib.parse.quote_plus(connection_string)
    engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")

    sql_query = f"SELECT * FROM [{target_table}] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"

    df = pd.read_sql(sql_query, engine, params=(baslangic_tarihi, bitis_tarihi))

    print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
    return df

def load_excel_file(tam_yol):
    """(Worker Görevi) Excel okuma işi (Calamine motoruyla)"""
    print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
    df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
    print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
    return df