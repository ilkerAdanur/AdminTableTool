# src/core/tasks.py

"""
Arka plan (Worker) iş parçacıklarında çalıştırılacak olan 
uzun süreli görevleri (veri çekme, işleme) barındırır.
"""

import pandas as pd
import traceback
from .database import run_database_query, get_database_tables, load_excel_file, create_db_engine, inspect,run_preview_query
from .template_manager import load_template
from .data_processor import apply_template, process_daily_summary

def fetch_and_apply_task(config, target_table, start_date, end_date, template_name, date_column_name):
    """
    (Worker Görevi) Ham veriyi çeker, taslağı yükler ve uygular.
    """
    try:
        print(f"\n--- Görev Başladı: fetch_and_apply_task ---")
        print(f"Alınan Parametreler:")
        print(f"  config: {config.get('type')}, target_table: {target_table}")
        print(f"  dates: {start_date} -> {end_date}")
        print(f"  template_name: {template_name}, date_column_name: {date_column_name}")
        
        # 1. Ham veriyi çek
        print("Çalışan iş parçacığı: Ham veri çekiliyor...")
        raw_df = run_database_query(config, target_table, start_date, end_date, date_column_name)
        print(f"Çalışan iş parçacığı: Ham veri çekildi. Boyut: {raw_df.shape}")

        if not template_name:
            print("Çalışan iş parçacığı: Taslak adı yok, ham veri döndürülüyor.")
            print(f"--- Görev Bitti (Ham Veri) ---")
            return raw_df
            
        # 2. Taslağı yükle
        print(f"Çalışan iş parçacığı: '{template_name}' taslağı yükleniyor...")
        template_data = load_template(template_name=template_name)
        
        if not template_data:
            raise FileNotFoundError(f"'{template_name}' taslak dosyası bulunamadı veya yüklenemedi.")
            
        # 3. Taslağı uygula
        print("Çalışan iş parçacığı: Taslak uygulanıyor (apply_template çağrılıyor)...")
        processed_df = apply_template(raw_df, template_data)
        print(f"Çalışan iş parçacığı: Taslak uygulandı. Sonuç Boyutu: {processed_df.shape}")

        print(f"Çalışan iş parçacığı: İşlem tamamlandı, işlenmiş veri döndürülüyor.")
        print(f"--- Görev Bitti (İşlenmiş Veri) ---")
        return processed_df

    except Exception as e:
         print(f"!!! HATA (fetch_and_apply_task içinde): {e}")
         traceback.print_exc()
         raise e

def get_column_names_task(config, target_table):
    """
    (Worker Görevi) Sadece belirtilen tablonun sütun adlarını çeker.
    """
    try:
        print(f"Çalışan iş parçacığı: '{target_table}' tablosunun sütunları çekiliyor...")
        engine = create_db_engine(config)
        inspector = inspect(engine)
        
        schema_name = None
        table_only_name = target_table
        if config.get('type') != 'access' and '.' in target_table:
            schema_name, table_only_name = target_table.split('.', 1)
            
        columns_info = inspector.get_columns(table_only_name, schema=schema_name)
        column_names = [col['name'] for col in columns_info]
        
        print(f"Çalışan iş parçacığı: Sütunlar bulundu: {column_names}")
        return column_names
    except Exception as e:
        print(f"!!! HATA (get_column_names_task içinde): {e}")
        traceback.print_exc()
        raise e

def run_summary_task(config, target_table, start_date, end_date, date_col, settings):
    """
    (Worker Görevi) Önce ham veriyi çeker, sonra günlük özeti işler.
    """
    try:
        # 1. Ham Veriyi Çek
        print("Çalışan iş parçacığı (Özet): Ham veri çekiliyor...")
        raw_df = run_database_query(config, target_table, start_date, end_date, date_col)
        
        if raw_df.empty:
            return pd.DataFrame() 
            
        # 2. Veriyi İşle
        print("Çalışan iş parçacığı (Özet): Veri işleniyor (process_daily_summary)...")
        summary_df = process_daily_summary(raw_df, settings)
        
        return summary_df
    except Exception as e:
        print(f"!!! HATA (run_summary_task içinde): {e}")
        traceback.print_exc()
        raise e
    
def get_tables_task(config):
    """
    (Worker Görevi) Veritabanına bağlanır ve tablo isimlerini döndürür.
    (database.py'deki get_database_tables için bir sarmalayıcıdır)
    """
    try:
        print(f"Çalışan iş parçacığı (get_tables_task): Tablo listesi çekiliyor -> {config.get('type')}")
        # database.py'den import edilen asıl fonksiyonu çağır
        # Bu fonksiyon (table_list, engine) döndürür
        return get_database_tables(config) 
    except Exception as e:
        print(f"!!! HATA (get_tables_task içinde): {e}")
        traceback.print_exc()
        raise e
    
def fetch_full_schema_task(config, engine, table_list):
    """
    (Worker Görevi) Verilen tablo listesindeki TÜM tabloların
    sütunlarını çeker ve bir sözlük olarak döndürür.
    """
    print(f"Çalışan iş parçacığı: Tam veritabanı şeması çekiliyor...")
    inspector = inspect(engine) # inspect, ana import'ta olmalı
    full_schema = {}
    db_type = config.get('type')

    for table_name_full in table_list:
        try:
            schema_name = None
            table_only_name = table_name_full

            # Access dışındaki DB'ler için şema adını ayır (örn: "dbo.ogrenciler")
            if db_type != 'access' and '.' in table_name_full:
                schema_name, table_only_name = table_name_full.split('.', 1)

            columns_info = inspector.get_columns(table_only_name, schema=schema_name)
            column_names = [col['name'] for col in columns_info]
            full_schema[table_name_full] = column_names

        except Exception as e:
            # Bir tablo okunamasa bile devam et
            print(f"HATA: '{table_name_full}' tablosunun sütunları okunamadı: {e}")
            full_schema[table_name_full] = [] # Hata durumunda boş liste

    print(f"Çalışan iş parçacığı: Tam şema çekildi. {len(full_schema)} tablo bulundu.")
    return full_schema

def fetch_preview_data_task(config, table_name, column_name, limit=10):
    """
    (Worker Görevi) run_preview_query için bir sarmalayıcı (wrapper)
    """
    try:
        print(f"Worker: {table_name} için önizleme verisi çekiliyor...")
        df = run_preview_query(config, table_name, column_name, limit)
        return df
    except Exception as e:
        print(f"!!! HATA (fetch_preview_data_task içinde): {e}")
        traceback.print_exc()
        raise e

    