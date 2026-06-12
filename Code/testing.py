import duckdb
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'

def patch_size_factor_inversion_fixed():
    with duckdb.connect(DB_PATH) as con:
        # הפעולה מבוצעת רק פעם אחת לכל טבלה!
        
        # 1. Percentile
        con.execute("""
            UPDATE asset_factors_normalized_percentile 
            SET size_factor_market = 100 - size_factor_market,
                size_factor_sector = 100 - size_factor_sector
        """)
        
        # 2. Final
        con.execute("""
            UPDATE asset_factors_normalized_final 
            SET size_factor_market = 100 - size_factor_market,
                size_factor_sector = 100 - size_factor_sector
        """)
        
        print("Patch applied exactly once. Values should be corrected.")

# להריץ רק פעם אחת!
patch_size_factor_inversion_fixed()

# בדיקה מחדש
con = duckdb.connect(DB_PATH)
asset_id = con.execute("SELECT asset_id FROM assets WHERE ticker = 'AAPL'").fetchone()[0]
df = con.execute("SELECT size_factor_sector, size_factor_market FROM asset_factors_normalized_final WHERE asset_id = ?", [asset_id]).df()
print(df)
con.close()