# src/core/data_processor.py

import pandas as pd
import re

def _prepare_formula(formula, source_columns):
    """
    Kullanıcının yazdığı formülü '[Column]' -> '`Column`' formatına çevirir.
    Pandas eval() bu formatı sever ve boşluklu isimlerle başa çıkar.
    Ayrıca formülde olmayan sütunları kontrol eder.
    """

    # Formüldeki [SutunAdi] kısımlarını bul
    used_columns = set(re.findall(r"\[(.*?)\]", formula))

    missing_columns = used_columns - set(source_columns)
    if missing_columns:
        raise ValueError(f"Formülde kullanılan şu sütunlar kaynak veride bulunamadı: {', '.join(missing_columns)}")

    # [Column Name] -> `Column Name` çevirisi
    processed_formula = formula
    for col in used_columns:
         processed_formula = processed_formula.replace(f'[{col}]', f'`{col}`') # ` ` (backtick) kullan

    return processed_formula

def apply_template(raw_df: pd.DataFrame, template_data: dict):
    """
    Ham DataFrame'e verilen taslak verisindeki formülleri uygular,
    sütunları seçer ve sıralar.
    Args:
        raw_df (pd.DataFrame): Veritabanından gelen ham veri.
        template_data (dict): Yüklenmiş taslak verisi (columns, formulas içerir).
    Returns:
        pd.DataFrame: İşlenmiş ve rapor için hazır DataFrame.
    """
    if raw_df.empty:
        print("apply_template: Ham veri boş, işlem yapılmadı.")
        return raw_df

    if not template_data or not template_data.get("columns"):
        print("apply_template: Geçerli taslak verisi yok, ham veri döndürülüyor.")
        return raw_df

    print("Taslak uygulanıyor...")
    processed_df = raw_df.copy() # Orijinal veriyi bozmamak için kopyala
    source_columns = list(processed_df.columns) # Ham sütun adları

    # 1. Hesaplanan Sütunları Oluştur
    formulas = template_data.get("formulas", {})
    calculated_columns = {} # Hesaplanan sütunları geçici olarak sakla

    for new_col_name, formula in formulas.items():
        try:
            # Formülü eval için hazırla (`[Col]` -> `` `Col` ``) ve kontrol et
            eval_formula = _prepare_formula(formula, source_columns)

            # Pandas eval() ile hesaplamayı yap ve yeni DataFrame'e ekle
            # engine='python' daha esnek formüllere izin verir
            calculated_values = processed_df.eval(eval_formula, engine='python')
            calculated_columns[new_col_name] = calculated_values
            print(f"Hesaplanan sütun '{new_col_name}' oluşturuldu.")

        except Exception as e:
            # Hata durumunda kullanıcıyı bilgilendir ama programı çökertme
            print(f"HATA: '{new_col_name}' sütunu için formül '{formula}' uygulanamadı: {e}")
            # Hatalı sütunu NaN (Not a Number) ile doldurabiliriz
            calculated_columns[new_col_name] = pd.NA 

    for col_name, values in calculated_columns.items():
         processed_df[col_name] = values

         if col_name not in source_columns:
              source_columns.append(col_name)


    # 2. Sütunları Seç ve Sırala
    final_columns_order = []
    rename_map = {} 

    template_columns = template_data.get("columns", [])
    for col_info in template_columns:
        display_name = col_info.get("display_name")
        col_type = col_info.get("type")
        source_or_formula = col_info.get("source_or_formula")

        actual_col_name = None
        if col_type == "Ham":
            actual_col_name = source_or_formula
        elif col_type == "Hesaplanmış":
            actual_col_name = display_name 

        if actual_col_name and actual_col_name in processed_df.columns:
             final_columns_order.append(actual_col_name)
             if actual_col_name != display_name:
                  rename_map[actual_col_name] = display_name
        else:
             print(f"UYARI: Taslaktaki '{display_name}' sütunu ({actual_col_name}) işlenmiş veride bulunamadı, atlanıyor.")

    if final_columns_order:
        final_df = processed_df[final_columns_order]
        if rename_map:
            final_df = final_df.rename(columns=rename_map)
    else:
        print("UYARI: Taslakta geçerli sütun bulunamadı, ham veri döndürülüyor.")
        return pd.DataFrame() 

    print("Taslak başarıyla uygulandı.")
    return final_df

def process_daily_summary(raw_df: pd.DataFrame, settings: dict):
    """
    Ham DataFrame'i alır ve ayarlara göre günlük olarak özetler.
    TARIH ve SAAT sütunlarını GÜVENLİ bir şekilde birleştirmeyi dener.
    """
    
    date_col = settings["date_col"]
    data_col = settings["data_col"]
    agg_type_str = settings["agg_type"]
    
    if raw_df.empty:
        return pd.DataFrame()
        
    df = raw_df.copy()

    # 1. Veri Sütununu Sayısala Dönüştür
    try:
        df[data_col] = pd.to_numeric(df[data_col], errors='coerce')
    except Exception as e:
        raise ValueError(f"'{data_col}' sütunu sayıya dönüştürülemedi: {e}")

    # 2. Tarih Sütununu Ayarla (DÜZELTİLMİŞ BLOK)
    try:
        # TARIH ve SAAT sütunları varsa (Access senaryosu)
        if "SAAT" in df.columns and date_col == "TARIH":
            print("TARIH ve SAAT sütunları birleştiriliyor...")
            
            # Önce her iki sütunun da datetime olduğundan emin ol
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df['SAAT'] = pd.to_datetime(df['SAAT'], errors='coerce')
            
            # NaT (Not a Time) olanları (bozuk verileri) at
            df.dropna(subset=[date_col, 'SAAT'], inplace=True)

            # 1. TARIH'in SADECE gün kısmını al (örn: "2023-09-30")
            date_str = df[date_col].dt.date.astype(str)
            
            # 2. SAAT'in SADECE zaman kısmını al (örn: "15:52:00")
            time_str = df['SAAT'].dt.time.astype(str)
            
            # 3. İkisini birleştir ve 'datetime_index' olarak ayarla
            df['datetime_index'] = pd.to_datetime(date_str + ' ' + time_str, errors='coerce')
            
            # Eğer birleştirme sonucu hata oluşmuşsa (NaT) o satırları da at
            df.dropna(subset=['datetime_index'], inplace=True)
            
        else:
             # Sadece tek bir tarih sütunu varsa (örn: PostgreSQL)
             print(f"'{date_col}' sütunu datetime index olarak ayarlanıyor...")
             df['datetime_index'] = pd.to_datetime(df[date_col], errors='coerce')
             df.dropna(subset=['datetime_index'], inplace=True)
             
        df.set_index('datetime_index', inplace=True)
        print("Datetime index başarıyla oluşturuldu.")
        
    except Exception as e:
        # Hata mesajına hangi sütunla ilgili olduğunu ekle
        raise ValueError(f"'{date_col}' veya 'SAAT' sütunu geçerli bir tarihe/zamana dönüştürülemedi: {e}")

    # 3. İşlem Türüne Göre Toplama (Aggregation)
    print(f"'{agg_type_str}' işlemi uygulanıyor...")
    
    # 'D' = Günlük (Daily) frekans
    grouper = df.groupby(pd.Grouper(freq='D'))[data_col]
    
    if "Toplam (Sum)" in agg_type_str:
        summary_df = grouper.sum().to_frame()
        summary_df.columns = [f"Günlük Toplam ({data_col})"]
        
    elif "Ortalama (Average)" in agg_type_str:
        summary_df = grouper.mean().to_frame()
        summary_df.columns = [f"Günlük Ortalama ({data_col})"]
        
    elif "Fark (Maksimum - Minimum)" in agg_type_str:
        summary_df = grouper.apply(lambda x: x.max() - x.min() if x.count() > 0 else None).to_frame()
        summary_df.columns = [f"Günlük Fark ({data_col})"]
        
    else:
        raise ValueError(f"Bilinmeyen işlem türü: {agg_type_str}")

    # Tarih aralığına göre son bir filtreleme yap
    summary_df = summary_df.loc[settings["start_date"]:settings["end_date"]]
    summary_df.index.name = "Tarih"
    
    print("Günlük özetleme tamamlandı.")
    return summary_df