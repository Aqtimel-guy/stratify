
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


# df_report = get_null_analysis(con , 'asset_factors_raw_v1' , '2015-01-01')
# df_report2 = get_null_analysis(con, 'asset_factors_normalized_zscore', '2015-01-01')
# df_report3 = get_null_analysis(con, 'asset_factors_normalized_percentile', '2015-01-01')

# df_report3 = get_null_analysis(con, 'fundamentals', '2015-01-01')


# print(df_report)
# print(df_report2)
# print(df_report3)

query = """
SELECT
    a.ticker,
    COUNT(*) AS rows_count,
    MIN(f.timestamp) AS min_feature_date,
    MAX(f.timestamp) AS max_feature_date,

    ROUND(
        100.0 * SUM(CASE WHEN f.revenue_growth_yoy IS NULL THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS revenue_growth_null_pct,

    ROUND(
        100.0 * SUM(CASE WHEN f.eps_growth_yoy IS NULL THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS eps_growth_null_pct,

    SUM(CASE WHEN f.revenue_growth_yoy IS NOT NULL THEN 1 ELSE 0 END) AS revenue_growth_non_null,
    SUM(CASE WHEN f.eps_growth_yoy IS NOT NULL THEN 1 ELSE 0 END) AS eps_growth_non_null,

    MIN(CASE WHEN f.revenue_growth_yoy IS NOT NULL THEN f.timestamp END) AS first_revenue_growth_date,
    MIN(CASE WHEN f.eps_growth_yoy IS NOT NULL THEN f.timestamp END) AS first_eps_growth_date,

    MAX(CASE WHEN f.revenue_growth_yoy IS NOT NULL THEN f.timestamp END) AS last_revenue_growth_date,
    MAX(CASE WHEN f.eps_growth_yoy IS NOT NULL THEN f.timestamp END) AS last_eps_growth_date

FROM features f
JOIN assets a
    ON f.asset_id = a.asset_id

WHERE a.ticker IN ('PLTR', 'UBER')
  AND f.timestamp >= DATE '2020-01-01'

GROUP BY
    a.ticker

ORDER BY
    a.ticker;

"""


print(con.execute(query).df())