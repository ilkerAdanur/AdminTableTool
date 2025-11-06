# src/core/database.py

import urllib.parse
from sqlalchemy import create_engine, inspect
import pandas as pd

# Calamine motorunu kontrol et
try:
    import python_calamine
    EXCEL_ENGINE = "calamine"
    print("Hızlı Excel motoru (python-calamine) bulundu.")
except ImportError:
    EXCEL_ENGINE = "openpyxl"
    print("UYARI: 'python-calamine' kütüphanesi bulunamadı. Hızlı Excel okuma için 'openpyxl' kullanılacak.")

def create_db_engine(config):
    """
    Gelen 'config' sözlüğüne göre doğru SQLAlchemy motorunu (engine) oluşturur.
    """
    db_type = config.get('type')
    
    try:
        if db_type == "access":
            db_path = config.get('path')
            if not db_path:
                raise ValueError("Access veritabanı için dosya yolu ('path') sağlanmadı.")
            
            connection_string = (
                r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
                rf"Dbq={db_path};"
            )
            quoted_connection_string = urllib.parse.quote_plus(connection_string)
            engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
        
        elif db_type == "sql":
            driver = "ODBC Driver 17 for SQL Server"
            server_name = config.get('host')
            database_name = config.get('database')
            if not server_name or not database_name:
                raise ValueError("SQL Server için 'host' (Sunucu) ve 'database' (Veritabanı Adı) sağlanmadı.")
            
            # Windows Authentication mantığı
            engine_url = (
                f"mssql+pyodbc://{server_name}/{database_name}"
                f"?driver={urllib.parse.quote_plus(driver)}"
                "&trusted_connection=yes"       
                "&encrypt=yes"                  
                "&trust_server_certificate=yes" 
            )
            engine = create_engine(engine_url)
            
        elif db_type == "postgres":
            # PostgreSQL User/Pass mantığı
            engine_url = (
                f"postgresql+psycopg2://{config.get('user')}:{config.get('password')}@"
                f"{config.get('host')}:{config.get('port')}/{config.get('database')}"
            )
            engine = create_engine(engine_url)

        else:
            raise ValueError(f"Desteklenmeyen veritabanı türü: {db_type}")
        
        # Bağlantıyı test et
        with engine.connect() as conn:
            pass 
        
        print(f"'{db_type}' veritabanına başarıyla bağlanıldı.")
        return engine

    except Exception as e:
        print(f"HATA: '{db_type}' veritabanına bağlanılamadı. Hata: {e}")
        raise e

def get_database_tables(config):
    """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerini döndürür."""
    print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {config.get('type')}")
    
    engine = create_db_engine(config)
    inspector = inspect(engine)
    
    all_tables = []
    db_type = config.get('type')
    
    if db_type == 'access':
        # Access: Basit liste
        table_names = inspector.get_table_names()
        user_tables = [name for name in table_names if not name.startswith("MSys")]
        all_tables = user_tables
    else:
        # SQL Server / PostgreSQL: Şemalı liste
        schema_names = inspector.get_schema_names()
        
        system_schemas = [
            'pg_catalog', 'information_schema', # PostgreSQL
            'guest', 'INFORMATION_SCHEMA', 'sys', # SQL Server
            'db_owner', 'db_accessadmin', 'db_securityadmin', 'db_ddladmin', 
            'db_backupoperator', 'db_datareader', 'db_datawriter', 
            'db_denydatareader', 'db_denydatawriter'
        ]
        
        for schema_name in schema_names:
            if schema_name not in system_schemas and not schema_name.startswith('pg_'):
                tables_in_schema = inspector.get_table_names(schema=schema_name)
                for table_name in tables_in_schema:
                    all_tables.append(f"{schema_name}.{table_name}")

    print(f"Çalışan iş parçacığı: Bulunan tablolar: {all_tables}")
    return all_tables, engine

def run_database_query(config, target_table, baslangic_tarihi, bitis_tarihi, date_column_name):
    """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""
    
    print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}, Tarih Sütunu: {date_column_name}")
    
    engine = create_db_engine(config)
    db_type = config.get('type')
    
    if db_type == 'access':
        # Access: [Tablo] [Sütun] ve ? parametre stili
        formatted_table_name = f"[{target_table}]"
        formatted_date_column = f"[{date_column_name}]" 
        sql_query = f"SELECT * FROM {formatted_table_name} WHERE {formatted_date_column} BETWEEN ? AND ? ORDER BY {formatted_date_column}"
        params = (baslangic_tarihi, bitis_tarihi)
        
    elif db_type == 'sql':
        # SQL Server: "Şema"."Tablo" "Sütun" ve ? parametre stili
        if '.' in target_table:
            schema_name, table_name = target_table.split('.', 1)
            formatted_table_name = f'"{schema_name}"."{table_name}"'
        else:
            formatted_table_name = f'"{target_table}"' 
            
        formatted_date_column = f'"{date_column_name}"' 
        sql_query = f"SELECT * FROM {formatted_table_name} WHERE {formatted_date_column} BETWEEN ? AND ? ORDER BY {formatted_date_column}"
        params = (baslangic_tarihi, bitis_tarihi)
        
    elif db_type == 'postgres':
        # PostgreSQL: "Şema"."Tablo" "Sütun" ve %(isim)s parametre stili
        if '.' in target_table:
            schema_name, table_name = target_table.split('.', 1)
            formatted_table_name = f'"{schema_name}"."{table_name}"'
        else:
            formatted_table_name = f'"{target_table}"'
            
        formatted_date_column = f'"{date_column_name}"' 
        sql_query = f"SELECT * FROM {formatted_table_name} WHERE {formatted_date_column} BETWEEN %(baslangic)s AND %(bitis)s ORDER BY {formatted_date_column}"
        params = {"baslangic": baslangic_tarihi, "bitis": bitis_tarihi}
        
    else:
         raise ValueError(f"Sorgu için desteklenmeyen veritabanı türü: {db_type}")
            
    df = pd.read_sql(sql_query, engine, params=params)
    
    print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
    return df

def load_excel_file(tam_yol):
    """(Worker Görevi) Excel okuma işi"""
    print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
    df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
    print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
    return df
def run_preview_query(config, table_name, column_name=None, limit=10):
    """
    Bir tablo veya sütunun ilk 'limit' satırını çeker.
    column_name None ise, tüm sütunları (SELECT *) çeker.
    """
    print(f"Çalışan iş parçacığı: Önizleme sorgusu başlatıldı. Tablo: {table_name}, Sütun: {column_name}")

    engine = create_db_engine(config)
    db_type = config.get('type')

    # Sütun adını ve tablo adını veritabanına göre formatla
    select_col = ""
    if db_type == 'access':
        formatted_table_name = f"[{table_name}]"
        select_col = f"[{column_name}]" if column_name else "*"
    else: # SQL Server, PostgreSQL
        if '.' in table_name:
            schema, table = table_name.split('.', 1)
            formatted_table_name = f'"{schema}"."{table}"'
        else:
            formatted_table_name = f'"{table_name}"'
        select_col = f'"{column_name}"' if column_name else "*"

    # Veritabanına göre LIMIT/TOP N sorgusunu oluştur
    sql_query = ""
    if db_type == 'access' or db_type == 'sql': # Access ve SQL Server
        sql_query = f"SELECT TOP {limit} {select_col} FROM {formatted_table_name}"
    elif db_type == 'postgres': # PostgreSQL
        sql_query = f"SELECT {select_col} FROM {formatted_table_name} LIMIT {limit}"
    else:
        raise ValueError(f"Önizleme sorgusu için desteklenmeyen veritabanı türü: {db_type}")

    df = pd.read_sql(sql_query, engine)

    print(f"Çalışan iş parçacığı: Önizleme sorgusu bitti. {len(df)} satır bulundu.")
    return df
