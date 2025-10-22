def run_database_query(db_path, target_table, baslangic_tarihi, bitis_tarihi):
    """2. Adım: (Worker) Artık parametre olarak gelen db_path ve target_table'ı kullanıyor."""
    
    print(f"Çalışan iş parçacığı: Sorgulama başlatıldı. Tablo: {target_table}, Tarih: {baslangic_tarihi} - {bitis_tarihi}")
    
    # --- SABİT YOL KALDIRILDI ---
    # db_path = r"C:\Users\User\..." (KALDIRILDI)
    connection_string = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"Dbq={db_path};"
    )
    quoted_connection_string = urllib.parse.quote_plus(connection_string)
    engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
    
    # --- SABİT TABLO ADI KALDIRILDI ---
    # sql_query = "SELECT * FROM [DEBILER] ..." (KALDIRILDI)
    # Sütun adının [TARIH] olduğunu varsaymaya devam ediyoruz.
    # Bu da ilerde dinamik hale getirilebilir.
    sql_query = f"SELECT * FROM [{target_table}] WHERE [TARIH] BETWEEN ? AND ? ORDER BY [TARIH]"
    df = pd.read_sql(sql_query, engine, params=(baslangic_tarihi, bitis_tarihi))
    return df

def get_database_tables(db_path):
    """(Worker) Veritabanına bağlanır ve tablo isimlerinin listesini döndürür."""
    print(f"Tablo listesi çekiliyor -> {db_path}")
    connection_string = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"Dbq={db_path};"
    )
    quoted_connection_string = urllib.parse.quote_plus(connection_string)
    engine = create_engine(f"access+pyodbc:///?odbc_connect={quoted_connection_string}")
    
    # SQLAlchemy'nin 'inspect' özelliğini kullanarak tablo listesini al
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    user_tables = [name for name in table_names if not name.startswith("MSys")]
    return user_tables
