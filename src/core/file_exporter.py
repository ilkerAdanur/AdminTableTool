def get_yeni_kayit_yolu(self, format):
    """
    Dinamik kayıt yolu ve 'TABLO(BAŞLANGIÇ-BİTİŞ)' formatında dosya adı oluşturan fonksiyon.
    Eğer dosya varsa 'TABLO(BAŞLANGIÇ-BİTİŞ) (1).xlsx' şeklinde devam eder.
    """
    try:
        # 1. Ana klasörler
        base_folder = r"C:\rapor" 
        format_folder = os.path.join(base_folder, format)
        
        # 2. Tarihleri al ve istediğin 'DD.MM.YYYY' formatına çevir
        start_date_obj = self.date_Baslangic.date().toPyDate()
        end_date_obj = self.date_Bitis.date().toPyDate()
        
        start_str = start_date_obj.strftime("%d.%m.%Y")
        end_str = end_date_obj.strftime("%d.%m.%Y")
        
        # 3. Klasör yolu için tarihleri al (YIL\GUN_AY)
        yil = start_date_obj.strftime("%Y")
        gun_ay = start_date_obj.strftime("%d_%m")
        
        # 4. Tablo adını al (Bağlantı yoksa 'Rapor' olarak varsay)
        table_name = self.target_table if self.target_table else "Rapor"
        
        # 5. İstenen formatta ana dosya adını oluştur
        # (Dosya adlarında / \ : * ? " < > | gibi karakterler olamaz, 
        #  ama bizim formatımız (DD.MM.YYYY) buna uygun.)
        base_filename = f"{table_name}({start_str}-{end_str})"
        
        # 6. Kayıt klasörünü oluştur
        tam_klasor_yolu = os.path.join(format_folder, yil, gun_ay)
        os.makedirs(tam_klasor_yolu, exist_ok=True)
        
        # 7. Dosya adı çakışmasını kontrol et
        uzanti = "xlsx" if format == "excel" else "pdf"
        dosya_adi = f"{base_filename}.{uzanti}" # Örn: "DEBILER(1.01.2024-4.01.2024).xlsx"
        tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
        
        sayac = 1
        # Döngü: Dosya zaten varsa, adını (1), (2) diye değiştir
        while os.path.exists(tam_dosya_yolu):
            dosya_adi = f"{base_filename} ({sayac}).{uzanti}" # Örn: "DEBILER(1.01.2024-4.01.2024) (1).xlsx"
            tam_dosya_yolu = os.path.join(tam_klasor_yolu, dosya_adi)
            sayac += 1
            
        return tam_dosya_yolu
        
    except Exception as e:
        QMessageBox.critical(self, "Hata", f"Kayıt yolu oluşturulamadı:\n{e}")
        return None
