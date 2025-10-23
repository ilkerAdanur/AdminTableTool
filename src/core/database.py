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

def create_db_engine(config):
    """
    Gelen 'config' sözlüğüne göre doğru SQLAlchemy motorunu (engine) oluşturur.
    """
    db_type = config.get('type')
    
    try:
        if db_type == "access":
            # Access (pyodbc)
            db_path = config.get('path')
            connection_string = (
                r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
                rf"Dbq={db_path};"
            )
            quoted_connection_string = urllib.parse.quote_plus(connection_string)
            engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
        
        elif db_type == "sql":
            # Microsoft SQL Server (pyodbc)
            driver = "ODBC Driver 17 for SQL Server" # veya {SQL Server}
            engine_url = (
                f"mssql+pyodbc://{config['user']}:{config['password']}@"
                f"{config['host']}:{config['port']}/{config['database']}"
                f"?driver={urllib.parse.quote_plus(driver)}"
            )
            engine = create_engine(engine_url)
            
        elif db_type == "postgres":
            # PostgreSQL (psycopg2)
            engine_url = (
                f"postgresql+psycopg2://{config['user']}:{config['password']}@"
                f"{config['host']}:{config['port']}/{config['database']}"
            )
            engine = create_engine(engine_url)

        # ... (Gelecekte MySQL, Oracle vb. buraya eklenebilir) ...
            
        else:
            raise ValueError(f"Desteklenmeyen veritabanı türü: {db_type}")
        
        # Bağlantıyı test etmek için motoru döndürmeden önce bir deneme yap
        with engine.connect() as conn:
            pass # Bağlantı başarılıysa devam et
        
        print(f"'{db_type}' veritabanına başarıyla bağlanıldı.")
        return engine

    except Exception as e:
        print(f"HATA: '{db_type}' veritabanına bağlanılamadı. Hata: {e}")
        # Hatanın ana arayüzde gösterilmesi için tekrar yükselt
        raise e

def get_database_tables(config):
    """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerinin listesini döndürür."""
    print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {config.get('type')}")
    
    # 1. Önce motoru (engine) oluştur
    engine = create_db_engine(config)
    
    # 2. Tablo listesini çek
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    # Access'in sistem tablolarını filtrele (diğerleri için gerekmeyebilir ama zararı yok)
    user_tables = [name for name in table_names if not name.startswith("MSys")]
    
    print(f"Çalışan iş parçacığı: Bulunan tablolar: {user_tables}")
    return user_tables, engine # <<< YENİ: Motoru (engine) da geri döndür!

def run_database_query(config, target_table, baslangic_tarihi, bitis_tarihi):
    """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""
    
    print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}")
    
    # 1. Motoru (engine) oluştur
    engine = create_db_engine(config)
    
    # 2. Sorguyu çalıştır
    # !!! ÖNEMLİ NOT !!!
    # Bu sorgu hala [TARIH] sütun adını varsayıyor.
    # Bir sonraki adımımız bu sütun adını da dinamik hale getirmek olmalı.
    
    # Farklı veritabanları farklı parametre stilleri kullanır:
    # SQL Server, PostgreSQL: %(param)s (isimlendirilmiş)
    # Access (pyodbc): ? (sıralı)
    
    if config.get('type') == 'access':
        sql_query = f"SELECT * FROM [{target_table}] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"
        params = (baslangic_tarihi, bitis_tarihi)
    else:
        # PostgreSQL, SQL Server vb. için standart isimlendirilmiş parametreler
        sql_query = f"SELECT * FROM \"{target_table}\" WHERE \"TARIH\" BETWEEN %(baslangic)s AND %(bitis)s ORDER BY \"TARIH\""
        params = {"baslangic": baslangic_tarihi, "bitis": bitis_tarihi}
        # Not: Sütun/tablo adlarını çift tırnak (") içine almak, PostgreSQL'de büyük/küçük harf
        # duyarlılığı için daha güvenlidir. Access bunu sevmez.

    df = pd.read_sql(sql_query, engine, params=params)
    
    print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
    return df

def load_excel_file(tam_yol):
    """(Worker Görevi) Excel okuma işi"""
    print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
    df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
    print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
    return df