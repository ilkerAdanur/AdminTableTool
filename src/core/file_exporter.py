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
    """(Worker Görevi) Excel kaydetme işi. Özetleri ve resmi ekler."""
    logger.info(f"Çalışan iş parçacığı: Excel kaydetme başlatıldı -> {kayit_yolu}")
    
    # 1. MultiIndex Sütunları Düzleştir
    df_export = df_to_save.copy()
    if isinstance(df_export.columns, pd.MultiIndex):
        df_export.columns = ['_'.join(map(str, col)).strip() for col in df_export.columns.values]
    
    # 2. Özet Verilerini Hesapla (LİSTE YÖNTEMİYLE)
    summary_data = []
    summary_index = ["TOPLAM", "ORTALAMA", "MAKSİMUM", "MİNİMUM"]
    funcs = ['sum', 'mean', 'max', 'min']
    
    for func in funcs:
        row_values = [] 
        
        for j in range(len(df_export.columns)):
            series = df_export.iloc[:, j]

            # --- DÜZELTME: İlk sütun (Genelde Tarih) ise ve tipi tarih/obje ise atla ---
            # Sadece 0. sütun (Tarih) için kontrol etmek en güvenlisidir.
            if j == 0: 
                row_values.append(None)
                continue
            
            # Ayrıca tip kontrolü de yapalım (Her ihtimale karşı)
            if pd.api.types.is_datetime64_any_dtype(series):
                row_values.append(None)
                continue

            # Güvenli dönüşüm ve hesaplama
            try:
                numeric_values = pd.to_numeric(series.values, errors='coerce')
                
                if pd.isna(numeric_values).all():
                    row_values.append(None)
                else:
                    temp_series = pd.Series(numeric_values)
                    if func == 'sum': val = temp_series.sum()
                    elif func == 'mean': val = temp_series.mean()
                    elif func == 'max': val = temp_series.max()
                    elif func == 'min': val = temp_series.min()
                    else: val = None
                    row_values.append(val)
            except:
                row_values.append(None)

        summary_data.append(row_values)
        
    # Özet DataFrame'i oluştur (Sütunlar df_export ile aynı)
    df_summary = pd.DataFrame(summary_data, columns=df_export.columns, index=summary_index)
    
    # 3. Excel Yazıcıyı Başlat
    with pd.ExcelWriter(kayit_yolu, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Rapor')
        
        # --- RESİM YERLEŞTİRME VE SATIR KAYDIRMA ---
        start_row_offset = 0
        if header_image_path and os.path.exists(header_image_path):
            try:
                worksheet.insert_image('A1', header_image_path, {'x_scale': 0.8, 'y_scale': 0.8})
                start_row_offset = 8 
            except Exception as e:
                logger.error(f"Excel'e resim eklenirken hata: {e}")
        
        # A. Özet Tablosunu Yaz
        # header=False (Sütun başlıklarını yazma, çünkü asıl tabloda yazacağız)
        df_summary.to_excel(writer, sheet_name='Rapor', startrow=start_row_offset, header=False)
        
        # B. Asıl Veriyi Yaz (Özet + 1 satır boşluk sonrasına)
        data_start_row = start_row_offset + 5 
        df_export.to_excel(writer, sheet_name='Rapor', startrow=data_start_row, index=False) # index=False ÖNEMLİ
        
        # Sütun Genişliği
        worksheet.set_column(0, 0, 20) 
        
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