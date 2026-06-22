
DB_PATH = r'C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb'
  
  
import duckdb
import pandas as pd
con = duckdb.connect(DB_PATH)
def get_null_analysis(con, table_name, start_date):
    """
    מחשב אחוזי NULL עבור כל עמודה בטבלה החל מתאריך מסוים.
    """
    # 1. קבלת שמות העמודות
    cols = get_columns(con, table_name)
    
    # 2. בניית ביטויים של COUNT(CASE WHEN col IS NULL THEN 1 END) לכל עמודה
    # זה יוצר עמודה אחת של אחוזים לכל עמודה בטבלה
    expression = ", ".join([
        f"(COUNT(CASE WHEN {col} IS NULL THEN 1 END) * 100.0 / COUNT(*)) AS {col}_null_pct" 
        for col in cols
    ])
    
    # 3. בניית השאילתה המלאה
    query = f"""
    SELECT {expression}
    FROM {table_name}
    WHERE timestamp >= '{start_date}'
    """
    
    # 4. הרצה והפיכה לפורמט נוח לקריאה (Long format)
    df = con.execute(query).df()
    
    # הפיכה מפורמט רחב (עמודות רבות) לפורמט ארוך (רשימה של עמודות ואחוזים)
    df_long = df.melt(var_name='column_name', value_name='null_percentage')
    df_long['column_name'] = df_long['column_name'].str.replace('_null_pct', '')
    
    return df_long


def get_columns(con, table_name):
    """פונקציית עזר להוצאת שמות העמודות מהטבלה"""
    res = con.execute(f"PRAGMA table_info('{table_name}')").df()
    return res['name'].tolist()

# df_report = get_null_analysis(con, 'asset_factors_normalized_final', '2015-01-01')
# df_report2 = get_null_analysis(con, 'features', '2015-01-01')
# df_report3 = get_null_analysis(con, 'fundamentals', '2015-01-01')


# print(df_report)
# print(df_report2)
# print(df_report3)


      
query = """

SELECT
    EXTRACT(YEAR FROM timestamp) AS year,
    COUNT(*) AS rows_count,

    ROUND(100.0 * SUM(CASE WHEN pe_ratio IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS pe_ratio_null_pct,
    ROUND(100.0 * SUM(CASE WHEN revenue_growth_yoy IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS revenue_growth_yoy_null_pct,
    ROUND(100.0 * SUM(CASE WHEN eps_growth_yoy IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS eps_growth_yoy_null_pct,

    ROUND(100.0 * SUM(CASE WHEN return_1y IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_1y_null_pct,
    ROUND(100.0 * SUM(CASE WHEN beta_90d IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS beta_90d_null_pct

FROM features
GROUP BY year
ORDER BY year DESC;
"""


print(
    con.execute(query).df()
)      


