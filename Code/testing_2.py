import duckdb

con = duckdb.connect(
    r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb",
    read_only=True
)

print(
    con.execute("""
        SELECT COUNT(*)
        FROM prices
    """).fetchone()[0]
)