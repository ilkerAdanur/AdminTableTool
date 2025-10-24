# src/core/file_exporter.py

import os
from datetime import datetime
import pandas as pd

# PDF ile ilgili tüm importları buraya taşıyoruz
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors

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
        print(f"Kayıt yolu oluşturulurken hata: {e}")
        return None # Hata durumunda None döndür

def task_run_excel(kayit_yolu, df_to_save):
    """(Worker Görevi) ARKA PLANDA çalışacak Excel kaydetme işi."""
    print(f"Çalışan iş parçacığı: Excel kaydetme başlatıldı -> {kayit_yolu}")
    df_to_save.to_excel(kayit_yolu, index=False)
    print("Çalışan iş parçacığı: Excel kaydetme bitti.")
    return kayit_yolu

def task_run_pdf(kayit_yolu, df_to_save):
    """(Worker Görevi) ARKA PLANDA çalışacak PDF kaydetme işi."""
    print(f"Çalışan iş parçacığı: PDF kaydetme başlatıldı -> {kayit_yolu}")

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
    print("Çalışan iş parçacığı: PDF kaydetme bitti.")
    return kayit_yolu