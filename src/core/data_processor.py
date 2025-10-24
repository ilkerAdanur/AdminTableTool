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