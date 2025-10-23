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
    Her veritabanı türü kendi 'try-except' bloğu içinde güvenli bir şekilde ele alınır.
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
            
            # Windows Authentication mantığı (Port'a veya User/Pass'a ihtiyaç duymaz)
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
        # Hatanın ana arayüzde gösterilmesi için orijinal hatayı (e) yükselt
        raise e

def get_database_tables(config):
    """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerini döndürür."""
    print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {config.get('type')}")
    
    engine = create_db_engine(config)
    inspector = inspect(engine)
    
    all_tables = []
    db_type = config.get('type')
    
    if db_type == 'access':
        # --- ACCESS MANTIĞI (Basit) ---
        table_names = inspector.get_table_names()
        # Access'in sistem tablolarını filtrele
        user_tables = [name for name in table_names if not name.startswith("MSys")]
        all_tables = user_tables
    else:
        # --- SQL SERVER / POSTGRESQL MANTIĞI (Şemalı) ---
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
                    # Tablo adını "şema.tablo" formatında ekle
                    all_tables.append(f"{schema_name}.{table_name}")

    print(f"Çalışan iş parçacığı: Bulunan tablolar: {all_tables}")
    return all_tables, engine

def run_database_query(config, target_table, baslangic_tarihi, bitis_tarihi):
    """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""
    
    print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}")
    
    engine = create_db_engine(config)
    db_type = config.get('type')
    
    # [TARIH] sütun adını hala sabit olarak varsayıyoruz. 
    # BU BİR SONRAKİ ADIMDA DÜZELTİLMELİ.
    date_column_name = "TARIH" 
    
    if db_type == 'access':
        # Access: [Tablo] [Sütun] ve ? parametre stili
        formatted_table_name = f"[{target_table}]"
        formatted_date_column = f"[{date_column_name}]"
        sql_query = f"SELECT * FROM {formatted_table_name} WHERE {formatted_date_column} BETWEEN ? AND ? ORDER BY {formatted_date_column}"
        params = (baslangic_tarihi, bitis_tarihi)
    else:
        # PostgreSQL/SQL Server: "şema"."tablo" "Sütun" ve %(param)s stili
        if '.' in target_table:
            schema_name, table_name = target_table.split('.', 1)
            formatted_table_name = f'"{schema_name}"."{table_name}"'
        else:
            formatted_table_name = f'"{target_table}"'
            
        formatted_date_column = f'"{date_column_name}"'
        sql_query = f"SELECT * FROM {formatted_table_name} WHERE {formatted_date_column} BETWEEN %(baslangic)s AND %(bitis)s ORDER BY {formatted_date_column}"
        params = {"baslangic": baslangic_tarihi, "bitis": bitis_tarihi}
        
    df = pd.read_sql(sql_query, engine, params=params)
    
    print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
    return df

def load_excel_file(tam_yol):
    """(Worker Görevi) Excel okuma işi"""
    print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
    df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
    print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
    return df



















# # src/core/database.py

# import urllib.parse
# from sqlalchemy import create_engine, inspect
# import pandas as pd

# # Calamine motorunu kontrol et
# try:
#     import python_calamine
#     EXCEL_ENGINE = "calamine"
# except ImportError:
#     EXCEL_ENGINE = "openpyxl"

# def create_db_engine(config):
#     """
#     Gelen 'config' sözlüğüne göre doğru SQLAlchemy motorunu (engine) oluşturur.
#     """
#     db_type = config.get('type')
    
#     try:
#         if db_type == "access":
#             # Access (pyodbc)
#             driver = "ODBC Driver 17 for SQL Server" # Hata mesajından biliyoruz
            
#             # Kullanıcının girdiği 'Sunucu' ve 'Veritabanı' adlarını al
#             server_name = config['host'] # Bu 'localhost\User' olmalı
#             database_name = config['database'] # Bu 'DbAhiotam' olmalı
            
#             # Bağlantı dizesini 'Trusted Connection' kullanacak şekilde oluştur
#             engine_url = (
#                 f"mssql+pyodbc://{server_name}/{database_name}"
#                 f"?driver={urllib.parse.quote_plus(driver)}"
#                 "&trusted_connection=yes"       # Windows Auth için bu şart
#                 "&encrypt=yes"                  # 'Mandatory' seçeneği için
#                 "&trust_server_certificate=yes" # Sertifikaya güven
#             )
#             engine = create_engine(engine_url)
        
#         elif db_type == "sql":
#             # Microsoft SQL Server (pyodbc)
#             driver = "ODBC Driver 17 for SQL Server" # veya {SQL Server}
            
#             server_name = config['host'] 
#             database_name = config['database'] 
            
#             engine_url = (
#                 f"mssql+pyodbc://{server_name}/{database_name}"
#                 f"?driver={urllib.parse.quote_plus(driver)}"
#                 "&trusted_connection=yes"       # Windows Auth için bu şart
#                 "&encrypt=yes"                  # Görüntüdeki 'Mandatory' seçeneği için
#                 "&trust_server_certificate=yes" # Sertifikaya güven
#             )
#             engine = create_engine(engine_url)
            
#         elif db_type == "postgres":
#             # PostgreSQL (psycopg2)
#             engine_url = (
#                 f"postgresql+psycopg2://{config['user']}:{config['password']}@"
#                 f"{config['host']}:{config['port']}/{config['database']}"
#             )
#             engine = create_engine(engine_url)

#         # ... (Gelecekte MySQL, Oracle vb. buraya eklenebilir) ...
            
#         else:
#             raise ValueError(f"Desteklenmeyen veritabanı türü: {db_type}")
        
#         # Bağlantıyı test etmek için motoru döndürmeden önce bir deneme yap
#         with engine.connect() as conn:
#             pass # Bağlantı başarılıysa devam et
        
#         print(f"'{db_type}' veritabanına başarıyla bağlanıldı.")
#         return engine

#     except Exception as e:
#         print(f"HATA: '{db_type}' veritabanına bağlanılamadı. Hata: {e}")
#         # Hatanın ana arayüzde gösterilmesi için tekrar yükselt
#         raise e

# # src/core/database.py içine

# def get_database_tables(config):
#     """(Worker Görevi) Veritabanına bağlanır ve TÜM şemalardaki tablo isimlerini döndürür."""
#     print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {config.get('type')}")
    
#     engine = create_db_engine(config)
#     inspector = inspect(engine)
    
#     all_tables = []
#     db_type = config.get('type')
    
#     if db_type == 'access':
#         # Access'te şema (schema) konsepti yok, eski yöntem devam
#         table_names = inspector.get_table_names()
#         user_tables = [name for name in table_names if not name.startswith("MSys")]
#         all_tables = user_tables
#     else:
#         # PostgreSQL, SQL Server vb. için tüm şemaları tara
        
#         # 1. Tüm şema adlarını al
#         schema_names = inspector.get_schema_names()
        
#         # 2. Sistem şemalarını filtrele
#         system_schemas = [
#             'pg_catalog', 'information_schema', # PostgreSQL
#             'guest', 'INFORMATION_SCHEMA', 'sys', # SQL Server
#             'db_owner', 'db_accessadmin', 'db_securityadmin', 'db_ddladmin', 
#             'db_backupoperator', 'db_datareader', 'db_datawriter', 
#             'db_denydatareader', 'db_denydatawriter'
#         ]
        
#         for schema_name in schema_names:
#             # Sistem şeması değilse veya pg_ ile başlamıyorsa
#             if schema_name not in system_schemas and not schema_name.startswith('pg_'):
#                 tables_in_schema = inspector.get_table_names(schema=schema_name)
#                 for table_name in tables_in_schema:
#                     # Tablo adını "şema.tablo" formatında ekle
#                     # Örn: "student.student" veya "public.users"
#                     all_tables.append(f"{schema_name}.{table_name}")

#     print(f"Çalışan iş parçacığı: Bulunan tablolar: {all_tables}")
#     return all_tables, engine # Motoru (engine) da geri döndür

# # def get_database_tables(config):
# #     """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerinin listesini döndürür."""
# #     print(f"Çalışan iş parçacığı: Tablo listesi çekiliyor -> {config.get('type')}")
    
# #     # 1. Önce motoru (engine) oluştur
# #     engine = create_db_engine(config)
    
# #     # 2. Tablo listesini çek
# #     inspector = inspect(engine)
# #     table_names = inspector.get_table_names()
    
# #     # Access'in sistem tablolarını filtrele (diğerleri için gerekmeyebilir ama zararı yok)
# #     user_tables = [name for name in table_names if not name.startswith("MSys")]
    
# #     print(f"Çalışan iş parçacığı: Bulunan tablolar: {user_tables}")
# #     return user_tables, engine # <<< YENİ: Motoru (engine) da geri döndür!

# # src/core/database.py içine

# def run_database_query(config, target_table, baslangic_tarihi, bitis_tarihi):
#     """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""
    
#     print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}")
    
#     engine = create_db_engine(config)
#     db_type = config.get('type')
    
#     # Hedef tabloyu ve şemayı (varsa) ayır
#     if db_type == 'access':
#         # Access'te şema.tablo formatı yok, tablo adı [Tablo Adı] olmalı
#         formatted_table_name = f"[{target_table}]"
#         # Access '?' parametre stili kullanır
#         # [TARIH] varsayımını (şimdilik) koruyoruz.
#         sql_query = f"SELECT * FROM {formatted_table_name} WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"
#         params = (baslangic_tarihi, bitis_tarihi)
#     else:
#         # PostgreSQL, SQL Server vb.
#         # Gelen target_table "şema.tablo" formatında mı?
#         if '.' in target_table:
#             schema_name, table_name = target_table.split('.', 1)
#             # Doğru SQL formatı: "şema"."tablo"
#             formatted_table_name = f'"{schema_name}"."{table_name}"'
#         else:
#             # Şema belirtilmemişse, varsayılan şema (örn: public)
#             formatted_table_name = f'"{target_table}"'
            
#         # PostgreSQL/SQL Server isimlendirilmiş parametre kullanır
#         # "TARIH" varsayımını (şimdilik) koruyoruz, ancak doğru tırnaklama (") ile
#         # (NOT: SQL Server [TARIH] tercih edebilir, ancak "TARIH" de genellikle çalışır)
#         sql_query = f"SELECT * FROM {formatted_table_name} WHERE \"TARIH\" BETWEEN %(baslangic)s AND %(bitis)s ORDER BY \"TARIH\""
#         params = {"baslangic": baslangic_tarihi, "bitis": bitis_tarihi}
        
#         # --- BİR SONRAKİ ADIM İÇİN NOT ---
#         # Bir sonraki adımımız, kullanıcıya [TARIH] sütununu da seçtirmek olmalı.
#         # Şimdilik "TARIH" adında bir sütun olduğunu varsayıyoruz.
        
#     df = pd.read_sql(sql_query, engine, params=params)
    
#     print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
#     return df

# # def run_database_query(config, target_table, baslangic_tarihi, bitis_tarihi):
# #     """(Worker Görevi) Veritabanında tarih aralığı sorgusu çalıştırır."""
    
# #     print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}")
    
# #     # 1. Motoru (engine) oluştur
# #     engine = create_db_engine(config)
    
# #     # 2. Sorguyu çalıştır
# #     # !!! ÖNEMLİ NOT !!!
# #     # Bu sorgu hala [TARIH] sütun adını varsayıyor.
# #     # Bir sonraki adımımız bu sütun adını da dinamik hale getirmek olmalı.
    
# #     # Farklı veritabanları farklı parametre stilleri kullanır:
# #     # SQL Server, PostgreSQL: %(param)s (isimlendirilmiş)
# #     # Access (pyodbc): ? (sıralı)
    
# #     if config.get('type') == 'access':
# #         sql_query = f"SELECT * FROM [{target_table}] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"
# #         params = (baslangic_tarihi, bitis_tarihi)
# #     else:
# #         # PostgreSQL, SQL Server vb. için standart isimlendirilmiş parametreler
# #         sql_query = f"SELECT * FROM \"{target_table}\" WHERE \"TARIH\" BETWEEN %(baslangic)s AND %(bitis)s ORDER BY \"TARIH\""
# #         params = {"baslangic": baslangic_tarihi, "bitis": bitis_tarihi}
# #         # Not: Sütun/tablo adlarını çift tırnak (") içine almak, PostgreSQL'de büyük/küçük harf
# #         # duyarlılığı için daha güvenlidir. Access bunu sevmez.

# #     df = pd.read_sql(sql_query, engine, params=params)
    
# #     print(f"Çalışan iş parçacığı: Sorgulama bitti. {len(df)} satır bulundu.")
# #     return df


# def load_excel_file(tam_yol):
#     """(Worker Görevi) Excel okuma işi"""
#     print(f"Çalışan iş parçacığı: Excel okuma başlatıldı -> {tam_yol}")
#     df = pd.read_excel(tam_yol, engine=EXCEL_ENGINE)
#     print(f"Çalışan iş parçacığı: Excel okuma bitti. {len(df)} satır bulundu.")
#     return df