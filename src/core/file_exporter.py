# src/core/file_exporter.py

import os
import pandas as pd
import logging

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors

logger = logging.getLogger(__name__)

def get_yeni_kayit_yolu(format, start_date_obj, end_date_obj, target_table, template_name=None):
    """
    Dinamik kayıt yolu ve 'TABLO(BAŞLANGIÇ-BİTİŞ)[-TASLAK_ADI]' formatında dosya adı oluşturur.
    """
    try:
        base_folder = r"C:\rapor" 
        format_folder = os.path.join(base_folder, format)

        # Tarihleri al ve 'DD.MM.YYYY' formatına çevir
        start_str = start_date_obj.strftime("%d.%m.%Y")
        end_str = end_date_obj.strftime("%d.%m.%Y")

        # Klasör yolu için tarihleri al (YIL\GUN_AY)
        yil = start_date_obj.strftime("%Y")
        gun_ay = start_date_obj.strftime("%d_%m")
        
        table_name = target_table if target_table else "Rapor"

        base_filename = f"{table_name}({start_str}-{end_str})"

        # Eğer bir taslak adı verilmişse ve bu ilk seçenek değilse ("Ham Veri")
        if template_name and template_name != "Taslak Uygulama (Varsayılan: Ham Veri)":
             # Taslak adından dosya adı için güvenli bir versiyon oluştur
             safe_template_name = "".join(c for c in template_name if c.isalnum() or c in ('_', '-')).rstrip()
             if safe_template_name:
                  base_filename += f"-{safe_template_name}" # Örn: DEBILER(....)-ToplamDebi

        tam_klasor_yolu = os.path.join(format_folder, yil, gun_ay)
        os.makedirs(tam_klasor_yolu, exist_ok=True)

        uzanti = "xlsx" if format == "excel" else "pdf"
        dosya_adi = f"{base_filename}.{uzanti}"
        tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)

        sayac = 1
        while os.path.exists(tam_dosya_yolu):
            dosya_adi = f"{base_filename} ({sayac}).{uzanti}"
            tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
            sayac += 1

        return tam_dosya_yolu
    except Exception as e:
        logger.error(f"Kayıt yolu oluşturulurken hata: {e}", exc_info=True)
        return None # Hata durumunda None döndür


# src/core/file_exporter.py

def task_run_excel(kayit_yolu, df_to_save, header_image_path=None):
    """(Worker Görevi) Excel kaydetme işi. Hizalama ve birleştirme eklendi."""
    logger.info(f"Çalışan iş parçacığı: Excel kaydetme başlatıldı -> {kayit_yolu}")
    
    # 1. MultiIndex Sütunları Düzleştir
    df_export = df_to_save.copy()
    if isinstance(df_export.columns, pd.MultiIndex):
        df_export.columns = ['_'.join(map(str, col)).strip() for col in df_export.columns.values]
    
    # 2. Özet DataFrame'ini Hazırla
    summary_index = ["TOPLAM", "ORTALAMA", "MAKSİMUM", "MİNİMUM"]
    df_summary = pd.DataFrame(index=summary_index, columns=df_export.columns)
    
    # 3. Hesaplamaları Yap ve Yerlerine Koy
    for col in df_export.columns:
        if col == df_export.columns[0]: continue # İlk sütun (Tarih) hesaplanmaz
        
        series = df_export[col]
        if pd.api.types.is_datetime64_any_dtype(series): continue

        try:
            numeric_values = pd.to_numeric(series.values, errors='coerce')
            if pd.isna(numeric_values).all(): continue
            
            temp_series = pd.Series(numeric_values)
            df_summary.at["TOPLAM", col] = temp_series.sum()
            df_summary.at["ORTALAMA", col] = temp_series.mean()
            df_summary.at["MAKSİMUM", col] = temp_series.max()
            df_summary.at["MİNİMUM", col] = temp_series.min()
        except Exception:
            continue

    # 4. Excel Yazıcıyı Başlat
    with pd.ExcelWriter(kayit_yolu, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Rapor')
        
        # Formatlar
        merge_format = workbook.add_format({
            'bold': True, 
            'border': 1, 
            'align': 'center', 
            'valign': 'vcenter',
            'bg_color': '#FFFFFF' # Beyaz arka plan
        })
        
        # --- RESİM YERLEŞTİRME (A Sütunu boş kalacak şekilde B'ye) ---
        start_row_offset = 0
        if header_image_path and os.path.exists(header_image_path):
            try:
                # 1. satır, 1. sütun (B1 hücresi)
                worksheet.insert_image(0, 1, header_image_path, {'x_scale': 0.8, 'y_scale': 0.8})
                start_row_offset = 8 
            except Exception as e:
                logger.error(f"Excel'e resim eklenirken hata: {e}")
        
        # --- A. ÖZET TABLOSUNU YAZ ---
        # Özet tablosu C sütunundan (Column 2) başlamalı.
        # A ve B sütunları (Sıra ve Tarih) başlıklar için ayrılacak.
        
        # Ancak df_summary içinde Tarih sütunu (boş olsa da) var. 
        # Onu yazdırmamak için sadece veri sütunlarını alıyoruz.
        summary_data_only = df_summary.iloc[:, 1:] # İlk sütunu (Tarih) atla
        
        summary_start_col = 3 # C sütunu (0=A, 1=B, 2=C)
        
        summary_data_only.to_excel(
            writer, 
            sheet_name='Rapor', 
            startrow=start_row_offset, 
            startcol=summary_start_col, 
            header=False,
            index=False # Sol başlıkları (TOPLAM vb.) biz elle yazacağız
        )
        
        # --- B. SOL TARAFI BİRLEŞTİR VE YAZ (TOPLAM, ORTALAMA...) ---
        # A ve B sütunlarını birleştirip başlıkları yaz
        titles = ["TOPLAM", "ORTALAMA", "MAKSİMUM", "MİNİMUM"]
        for i, title in enumerate(titles):
            row = start_row_offset + i
            # A ve B sütunlarını birleştir (0 ve 1)
            worksheet.merge_range(row, 1, row, 2, title, merge_format)

        # --- C. ASIL VERİ TABLOSUNU YAZ ---
        data_start_row = start_row_offset + 5 
        
        # index=True -> "Sıra" sütunu A sütununa (0) gelir.
        # df_export'un ilk sütunu (Tarih) B sütununa (1) gelir.
        # Veri sütunları C sütununa (2) gelir.
        # Bu, yukarıdaki özet tablosuyla (C'den başlayan) tam hizalanır.
        
        df_export.to_excel(
            writer, 
            sheet_name='Rapor', 
            startrow=data_start_row, 
            startcol=1, 
            index=True, 
            index_label="Sıra"
        )
        
        # Sütun Genişliği
        worksheet.set_column(0, 0, 8)  # A (Sıra) dar
        worksheet.set_column(1, 1, 20) # B (Tarih) geniş
        worksheet.set_column(2, len(df_export.columns)+1, 15) # Veriler orta
        
    logger.info("Çalışan iş parçacığı: Excel kaydetme bitti.")
    return kayit_yolu

def task_run_pdf(kayit_yolu, df_to_save):
    """(Worker Görevi) ARKA PLANDA çalışacak PDF kaydetme işi."""
    logger.info(f"Çalışan iş parçacığı: PDF kaydetme başlatıldı -> {kayit_yolu}")

    doc = SimpleDocTemplate(kayit_yolu, pagesize=landscape(A4))
    data = [list(df_to_save.columns)] + df_to_save.values.tolist()
    table = Table(data)

    # Fontların ana uygulamada (register_pdf_fonts) yüklendiğini varsayar
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Arial_Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Arial'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    doc.build([table])
    logger.info("Çalışan iş parçacığı: PDF kaydetme bitti.")
    return kayit_yolu