# src/core/tasks.py
"""
Arka plan (Worker) iş parçacıklarında çalıştırılacak olan 
uzun süreli görevleri (veri çekme, işleme) barındırır.
"""
import logging
import traceback
import pandas as pd
import re 

# --- TEMİZLENMİŞ IMPORTLAR ---
from .database import (
    run_database_query, 
    get_database_tables, 
    load_excel_file, 
    create_db_engine, 
    inspect, 
    run_preview_query
)
from .template_manager import load_template
from .data_processor import apply_template, process_daily_summary

# --- ANA LOGGER ---
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# --- 'report_tab.py' İÇİN GEREKLİ OLAN ESKİ GÖREVLER (LOG EKLENDİ) ---
# ---------------------------------------------------------------------

def fetch_and_apply_task(config, target_table, start_date, end_date, template_name, date_column_name):
    """
    (Worker Görevi) Ham veriyi çeker, taslağı yükler ve uygular.
    ('Eski' ReportTabWidget tarafından kullanılır)
    """
    try:
        logger.info(f"--- Görev Başladı: fetch_and_apply_task ---")
        logger.info(f"  Parametreler: {config.get('type')}, {target_table}, {start_date} -> {end_date}")
        logger.info(f"  Taslak: {template_name}, Tarih Sütunu: {date_column_name}")
        
        # 1. Ham veriyi çek
        logger.info("Çalışan iş parçacığı: Ham veri çekiliyor...")
        raw_df = run_database_query(config, target_table, start_date, end_date, date_column_name)
        logger.info(f"Çalışan iş parçacığı: Ham veri çekildi. Boyut: {raw_df.shape}")

        if not template_name:
            logger.info("Çalışan iş parçacığı: Taslak adı yok, ham veri döndürülüyor.")
            return raw_df
            
        # 2. Taslağı yükle
        logger.info(f"Çalışan iş parçacığı: '{template_name}' taslağı yükleniyor...")
        # (Sorumluluk ayrımı sonrası 'parent_widget' kaldırıldı)
        template_data = load_template(template_name=template_name) 
        
        if not template_data:
            # (Hata artık load_template içinde fırlatılıyor, ancak yine de kontrol edelim)
            raise FileNotFoundError(f"'{template_name}' taslak dosyası bulunamadı veya yüklenemedi.")
            
        # 3. Taslağı uygula
        logger.info("Çalışan iş parçacığı: Taslak uygulanıyor (apply_template çağrılıyor)...")
        processed_df = apply_template(raw_df, template_data)
        logger.info(f"Çalışan iş parçacığı: Taslak uygulandı. Sonuç Boyutu: {processed_df.shape}")

        logger.info(f"--- Görev Bitti (fetch_and_apply_task) ---")
        return processed_df

    except Exception as e:
         logger.error(f"!!! HATA (fetch_and_apply_task içinde): {e}", exc_info=True)
         raise e

def run_summary_task(config, target_table, start_date, end_date, date_col, settings):
    """
    (Worker Görevi) Önce ham veriyi çeker, sonra günlük özeti işler.
    ('DailySummaryDialog' tarafından kullanılır)
    """
    try:
        # 1. Ham Veriyi Çek
        logger.info("Çalışan iş parçacığı (Özet): Ham veri çekiliyor...")
        raw_df = run_database_query(config, target_table, start_date, end_date, date_col)
        
        if raw_df.empty:
            logger.warning("Çalışan iş parçacığı (Özet): Veri bulunamadı.")
            return pd.DataFrame() 
            
        # 2. Veriyi İşle
        logger.info("Çalışan iş parçacığı (Özet): Veri işleniyor (process_daily_summary)...")
        summary_df = process_daily_summary(raw_df, settings)
        
        return summary_df
    except Exception as e:
        logger.error(f"!!! HATA (run_summary_task içinde): {e}", exc_info=True)
        raise e

# ---------------------------------------------------------------------
# --- 'main_window.py' İÇİN GEREKLİ OLAN GÖREVLER (LOG EKLENDİ) ---
# ---------------------------------------------------------------------

def get_column_names_task(config, target_table):
    """(Worker Görevi) Sadece belirtilen tablonun sütun adlarını çeker."""
    try:
        logger.info(f"Çalışan iş parçacığı: '{target_table}' tablosunun sütunları çekiliyor...")
        engine = create_db_engine(config)
        inspector = inspect(engine)
        
        schema_name = None
        table_only_name = target_table
        if config.get('type') != 'access' and '.' in target_table:
            schema_name, table_only_name = target_table.split('.', 1)
            
        columns_info = inspector.get_columns(table_only_name, schema=schema_name)
        column_names = [col['name'] for col in columns_info]
        
        logger.info(f"Çalışan iş parçacığı: Sütunlar bulundu: {column_names}")
        return column_names
    except Exception as e:
        logger.error(f"!!! HATA (get_column_names_task içinde): {e}", exc_info=True)
        raise e
    
def get_tables_task(config):
    """(Worker Görevi) Veritabanına bağlanır ve tablo isimlerini döndürür."""
    try:
        logger.info(f"Çalışan iş parçacığı (get_tables_task): Tablo listesi çekiliyor -> {config.get('type')}")
        return get_database_tables(config) 
    except Exception as e:
        logger.error(f"!!! HATA (get_tables_task içinde): {e}", exc_info=True)
        raise e
    
def fetch_full_schema_task(config, engine, table_list):
    """(Worker Görevi) Verilen tablo listesindeki TÜM tabloların sütunlarını çeker."""
    logger.info(f"Çalışan iş parçacığı: Tam veritabanı şeması çekiliyor...")
    inspector = inspect(engine)
    full_schema = {}
    db_type = config.get('type')

    for table_name_full in table_list:
        try:
            schema_name = None
            table_only_name = table_name_full
            if db_type != 'access' and '.' in table_name_full:
                schema_name, table_only_name = table_name_full.split('.', 1)

            columns_info = inspector.get_columns(table_only_name, schema=schema_name)
            column_names = [col['name'] for col in columns_info]
            full_schema[table_name_full] = column_names

        except Exception as e:
            logger.warning(f"HATA: '{table_name_full}' tablosunun sütunları okunamadı: {e}")
            full_schema[table_name_full] = [] 

    logger.info(f"Çalışan iş parçacığı: Tam şema çekildi. {len(full_schema)} tablo bulundu.")
    return full_schema

# ---------------------------------------------------------------------
# --- 'report_designer.py' İÇİN GEREKLİ OLAN GÖREV (LOG EKLENDİ) ---
# ---------------------------------------------------------------------

def fetch_preview_data_task(config, table_name, column_name, limit=10):
    """(Worker Görevi) run_preview_query için bir sarmalayıcı (wrapper)"""
    try:
        logger.info(f"Worker: {table_name} için önizleme verisi çekiliyor...")
        df = run_preview_query(config, table_name, column_name, limit)
        return df
    except Exception as e:
        logger.error(f"!!! HATA (fetch_preview_data_task içinde): {e}", exc_info=True)
        raise e

# ---------------------------------------------------------------------
# --- YARDIMCI FONKSİYONLAR (run_dynamic_report_task için) ---
# ---------------------------------------------------------------------

def _convert_agg_string_to_func(agg_str):
    """(Yardımcı Fonksiyon) Kullanıcı seçimini pandas fonksiyonuna çevirir."""
    
    if "Toplam (Sum)" in agg_str:
        return 'sum'
    elif "Ortalama (Average)" in agg_str:
        return 'mean'
    elif "Fark (Maks-Min)" in agg_str:
        return lambda x: x.max() - x.min() if x.count() > 0 else pd.NA
    elif "Maksimum (Max)" in agg_str:
        return 'max'
    elif "Minimum (Min)" in agg_str:
        return 'min'
    elif "İlk Değer (First)" in agg_str:
        return 'first'
    elif "Son Değer (Last)" in agg_str:
        return 'last'
    elif "Sayı (Count)" in agg_str:
        return 'count'
    else:
        # "Yok (Özette Gösterme)"
        return None

# ---------------------------------------------------------------------
# --- 'dynamic_table_tab.py' İÇİN GEREKLİ OLAN ANA GÖREV (DÜZELTİLMİŞ) ---
# ---------------------------------------------------------------------

def run_dynamic_report_task(config, defined_columns, full_date_column, start_date, end_date, agg_type_str="Ham Veri (Grup Yok)"):
    """
    (Worker Görevi) Yeni "Veri Tablosu" sekmesi için çalışır.
    (GÜNCELLENMİŞ MANTIK: Her iki modda da çoklu tabloyu destekler.
     Hata 1 (Günlük Özet) ve Hata 2 (Ham Veri) düzeltildi.)
    """
    logger.info(f"Dinamik rapor görevi başlatıldı. İşlem: {agg_type_str}")
    
    if not defined_columns:
        return pd.DataFrame() 

    try:
        # --- 1. Gerekli Ham Sütunları ve Formülleri Ayır (Her İki Mod için Ortak) ---
        
        required_aggs = {}
        formula_definitions = []
        source_columns_full = set() 
        
        if not full_date_column or full_date_column == "Tarih Sütunu Seçin...":
             raise ValueError("Birincil tarih sütunu seçilmedi.")
             
        date_col_base = full_date_column.split('.')[-1] # Örn: "TARIH"

        for col_def in defined_columns:
            col_name = col_def['name']
            formula = col_def['formula']
            agg_str = col_def.get('agg', 'Yok (Özette Gösterme)')
            
            if 'sources' not in col_def:
                 raise ValueError(f"'{col_name}' sütunu için 'sources' listesi bulunamadı.")
                 
            parsed_formula = formula
            is_simple_source = (len(col_def['sources']) == 1 and formula == f"[{col_def['sources'][0]}]")
            
            for src in col_def['sources']:
                source_columns_full.add(src) 
                safe_src_name = src.replace('.', '_') 
                parsed_formula = parsed_formula.replace(f'[{src}]', f'`{safe_src_name}`')
                
                # --- DÜZELTME (GÜNLÜK ÖZET HATASI) ---
                pd_agg_func = _convert_agg_string_to_func(agg_str)
                if pd_agg_func:
                    if is_simple_source:
                        required_aggs[src] = pd_agg_func
                    elif src not in required_aggs:
                        required_aggs[src] = pd_agg_func
                # --- DÜZELTME SONU ---

            if not is_simple_source:
                 formula_definitions.append((col_name, parsed_formula, agg_str))
            
        tables = set(c.split('.')[0] for c in source_columns_full)
        if not tables:
             raise ValueError("Formüllerde hiçbir kaynak tablo bulunamadı.")
        
        logger.info(f"Kaynak tablolar algılandı: {tables}")

        # --- 2. Veri Çekme ve İşleme (Moda Göre) ---
        
        final_df = pd.DataFrame()

        # --- MOD A: GÜNLÜK ÖZET (ÇOKLU TABLO DESTEKLİ) ---
        if agg_type_str != "Ham Veri (Grup Yok)":
            logger.info("Günlük Özet modu: Tablolar ayrı ayrı özetlenecek ve birleştirilecek (JOIN).")
            
            final_df = pd.DataFrame(index=pd.date_range(start_date, end_date, freq='D'))
            final_df.index.name = "Tarih"

            for table_name in tables:
                logger.debug(f"İşleniyor: Tablo '{table_name}'")
                agg_dict = {} 
                rename_map = {}
                
                for full_col_name, pd_agg_func in required_aggs.items():
                    if full_col_name.startswith(table_name):
                        base_col_name = full_col_name.split('.')[-1]
                        
                        if base_col_name == date_col_base or base_col_name == "SAAT":
                            continue

                        agg_dict[base_col_name] = pd_agg_func
                        safe_full_name = full_col_name.replace('.', '_')
                        rename_map[base_col_name] = safe_full_name
                
                if not agg_dict:
                    # 'required_aggs' artık formüllerden de beslendiği için,
                    # eğer agg_dict *hala* boşsa, kullanıcı gerçekten sadece 'Yok'
                    # olarak işaretli sütunları veya sadece formülleri seçmiştir.
                    logger.warning(f"'{table_name}' için özetlenecek ham sütun bulunamadı, atlanıyor.")
                    # (Formül hesaplaması için 'required_aggs'in dolu olması yeterli,
                    #  bu yüzden 'continue' DEMİYORUZ, sorguya devam ediyoruz)
                    pass 
                
                # Sorguya eklenecek sütunlar: Gerekli ham sütunlar (kaynaklar) + ana tarih sütunu
                cols_for_this_table_base = set(src.split('.')[-1] for src in source_columns_full if src.startswith(table_name))
                cols_for_this_table_base.add(date_col_base) 
                
                # --- DÜZELTME (HAM VERİ KAYMASI - Günlük Özet için de): "SAAT"i otomatik ekleme ---
                # cols_for_this_table_base.add("SAAT") # <-- BU SATIR SİLİNDİ
                
                logger.debug(f"'{table_name}' için SQL sorgusu sütunları: {list(cols_for_this_table_base)}")
                
                df_table_raw = run_database_query(
                    config, target_table=table_name, date_column_name=date_col_base,
                    baslangic_tarihi=start_date, bitis_tarihi=end_date,      
                    columns_to_select=list(cols_for_this_table_base) 
                )
                
                if df_table_raw.empty:
                    logger.warning(f"'{table_name}' için veri bulunamadı, atlanıyor.")
                    continue

                try:
                    datetime_index_col = 'datetime_index_for_agg'
                    # 'SAAT' sütunu SADECE kullanıcı manuel sürüklediyse (veya TARIH ise) birleştirilir
                    if "SAAT" in df_table_raw.columns and date_col_base == "TARIH":
                        logger.debug(f"'{table_name}': TARIH ve SAAT birleştiriliyor...")
                        temp_tarih = pd.to_datetime(df_table_raw[date_col_base], errors='coerce')
                        temp_saat = pd.to_datetime(df_table_raw['SAAT'], errors='coerce')
                        date_str = temp_tarih.dt.date.astype(str)
                        time_str = temp_saat.dt.time.astype(str)
                        df_table_raw[datetime_index_col] = pd.to_datetime(date_str + ' ' + time_str, errors='coerce')
                    else: 
                        logger.debug(f"'{table_name}': '{date_col_base}' datetime index olarak kullanılıyor...")
                        df_table_raw[datetime_index_col] = pd.to_datetime(df_table_raw[date_col_base], errors='coerce')
                    
                    df_table_raw.dropna(subset=[datetime_index_col], inplace=True) 
                    df_table_raw.set_index(datetime_index_col, inplace=True)
                except Exception as e:
                    raise ValueError(f"Agregasyon için tarih index'i oluşturulamadı ({table_name}): {e}")

                if agg_dict: # Özetlenecek bir şey varsa
                    logger.debug(f"'{table_name}' için agregasyon uygulanıyor: {agg_dict}")
                    df_table_agg = df_table_raw.groupby(pd.Grouper(freq='D')).agg(agg_dict)
                    df_table_agg.rename(columns=rename_map, inplace=True)
                    final_df = final_df.join(df_table_agg, how='outer')
                else:
                    # Formüller için ham veriyi (günlük gruplanmış) sakla (örn: 'first')
                    # Bu senaryo şu anda tam desteklenmiyor, ancak en azından çökmemeli.
                     logger.warning(f"'{table_name}' için özetleme fonksiyonu bulunamadı, formüller çalışmayabilir.")

            logger.info("Tüm tablolar birleştirildi. Şimdi formüller uygulanıyor...")
            
            for col_name, parsed_formula, agg_str in formula_definitions:
                if agg_str == "Yok (Özette Gösterme)": 
                    continue
                try:
                    logger.debug(f"Özet formülü uygulanıyor: {col_name} = {parsed_formula}")
                    final_df[col_name] = final_df.eval(parsed_formula, engine='python')
                except Exception as e:
                    logger.error(f"Özet formül hatası ({col_name}): {e}", exc_info=True)
                    final_df[col_name] = f"Formül Hatası: {e}"

        # --- MOD B: HAM VERİ (ÇOKLU TABLO DESTEKLİ) ---
        else: 
            logger.info("Ham Veri modu: Tablolar çekilecek ve alt alta birleştirilecek (CONCAT).")
            list_of_raw_dfs = []

            for table_name in tables:
                cols_for_this_table_base = set()
                rename_map = {} 
                
                for src in source_columns_full:
                    if src.startswith(table_name):
                        base_name = src.split('.')[-1]
                        cols_for_this_table_base.add(base_name)
                        # TARIH DIŞINDAKİLERİ yeniden adlandır
                        if base_name != date_col_base:
                            safe_full_name = src.replace('.', '_')
                            rename_map[base_name] = safe_full_name
                
                # Sorguya eklenecek sütunlar: Gerekli ham sütunlar + ana tarih sütunu
                cols_to_query = set(cols_for_this_table_base)
                cols_to_query.add(date_col_base)
                
                # --- DÜZELTME (HAM VERİ KAYMASI): "SAAT"i otomatik ekleme ---
                # cols_to_query.add("SAAT") # <-- BU SATIR SİLİNDİ
                
                logger.debug(f"'{table_name}' için ham veri çekiliyor. Sütunlar: {list(cols_to_query)}")
                raw_df = run_database_query(
                    config, target_table=table_name, date_column_name=date_col_base,
                    baslangic_tarihi=start_date, bitis_tarihi=end_date,      
                    columns_to_select=list(cols_to_query) 
                )
                
                if raw_df.empty:
                    logger.warning(f"'{table_name}' için ham veri bulunamadı, atlanıyor.")
                    continue
                    
                raw_df.rename(columns=rename_map, inplace=True)
                list_of_raw_dfs.append(raw_df)

            if not list_of_raw_dfs:
                logger.warning("Ham Veri modu: Hiçbir tabloda veri bulunamadı.")
                return pd.DataFrame(columns=[c['name'] for c in defined_columns])

            final_df = pd.concat(list_of_raw_dfs, ignore_index=True, sort=False)
            
            # Ana TARIH sütununu güvenli ada (DEBILER_TARIH) çevir
            safe_date_col = full_date_column.replace('.', '_')
            if date_col_base in final_df.columns:
                 final_df.rename(columns={date_col_base: safe_date_col}, inplace=True)
            
            logger.info(f"Ham veriler birleştirildi ({len(final_df)} satır). Formüller uygulanıyor...")
            
            for col_name, parsed_formula, agg_str in formula_definitions:
                try:
                    logger.debug(f"Ham formül uygulanıyor: {col_name} = {parsed_formula}")
                    final_df[col_name] = final_df.eval(parsed_formula, engine='python')
                except Exception as e:
                    logger.error(f"Ham formül hatası ({col_name}): {e}", exc_info=True)
                    final_df[col_name] = f"Formül Hatası: {e}"

        # --- 4. Sonuçları Filtrele ve Yeniden Adlandır (Her İki Mod için Ortak) ---
        
        ordered_safe_names = []
        rename_map_final = {} 
        
        if agg_type_str != "Ham Veri (Grup Yok)":
            # Özet Modu:
            for c in defined_columns:
                if c.get('agg', 'Yok') == "Yok (Özette Gösterme)":
                    continue
                is_simple = (len(c['sources']) == 1 and c['formula'] == f"[{c['sources'][0]}]")
                if is_simple and c['sources'][0] == full_date_column:
                    continue
                safe_name = c['sources'][0].replace('.', '_') if is_simple else c['name']
                if safe_name in final_df.columns:
                    ordered_safe_names.append(safe_name)
                    rename_map_final[safe_name] = c['name']
                else:
                     logger.warning(f"[Özet] Tanımlı sütun '{c['name']}' (güvenli ad: '{safe_name}') son DataFrame'de bulunamadı.")
        else:
            # Ham Veri Modu:
             for c in defined_columns:
                 is_simple = (len(c['sources']) == 1 and c['formula'] == f"[{c['sources'][0]}]")
                 safe_name = c['sources'][0].replace('.', '_') if is_simple else c['name']
                 
                 if safe_name in final_df.columns:
                     ordered_safe_names.append(safe_name)
                     rename_map_final[safe_name] = c['name']
                 else:
                      logger.warning(f"[Ham] Tanımlı sütun '{c['name']}' (güvenli ad: '{safe_name}') son DataFrame'de bulunamadı.")
        
        if not ordered_safe_names:
             logger.warning("Sonuç filtresi: Gösterilecek hiçbir sütun bulunamadı.")
             if agg_type_str != "Ham Veri (Grup Yok)":
                 return final_df[[]] 
             else:
                 return pd.DataFrame() 

        # --- DÜZELTME (HAM VERİ KAYMASI): Otomatik TARIH/SAAT ekleyen blok SİLİNDİ ---

        final_df = final_df[ordered_safe_names].rename(columns=rename_map_final)
        
        if agg_type_str != "Ham Veri (Grup Yok)":
            final_df = final_df.loc[start_date:end_date]
            final_df.dropna(how='all', inplace=True) 

        logger.info("Dinamik rapor görevi başarıyla tamamlandı.")
        return final_df
            
    except Exception as e:
        logger.critical(f"!!! HATA (run_dynamic_report_task içinde): {e}", exc_info=True)
        raise e

