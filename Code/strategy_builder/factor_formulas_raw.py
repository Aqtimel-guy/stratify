import duckdb
import logging
import pandas as pd
import numpy as np
from functools import reduce
import sys

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'




## seems ok
def momentum_factor_raw_calculator(con  ,asset_id , w1=0.3 , w2=0.3 , w3=0.2 , w4=0.1 , w5=0.1):
    """
    gets an asset_id and potential weights. than calculate the momentum score for each day we have in the DB
    Wi refers to the weights
    returns a DF with (asset_id , timestamp , momentum_factor_raw)

    """
    logger = logging.getLogger(__name__)
   
   # making sure the weights make sense
    weights_sum = sum([w1, w2, w3, w4, w5])
    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights should sum to 1. Current sum: {weights_sum}")
        return None
    
    # fetching data
    df = con.execute("""
                     
                SELECT 
                asset_id , timestamp, return_3m , return_6m , return_1y , momentum_relative_sp_1y , dist_sma50 , dist_sma200
                FROM
                features
                WHERE
                asset_id = ?
                ORDER BY
                timestamp asc
                
                """ , [asset_id]).df()
    if df.empty:
        return None
    
    df['momentum_factor_raw'] = (
            w1 * df['return_1y'] +
            w2 * df['momentum_relative_sp_1y'] +
            w3 * df['return_6m'] +
            w4 * df['dist_sma200'] +
            w5 * df['return_3m']
        )
    df['momentum_factor_raw'] = df['momentum_factor_raw'].round(3)
    
    return df[['asset_id', 'timestamp', 'momentum_factor_raw']]

## seems ok
def value_factor_raw_calculator(con , asset_id, w1=0.6, w2=0.3, w3=0.1):
    """

    Key properties:
    - True point-in-time alignment (AS-OF JOIN logic)
    - Lagged fundamentals (avoid lookahead bias)
    - TTM dividends
    - Stable numeric handling
    - Cross-sectional ready output (no leakage assumptions)
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    # -----------------------------
    # 1. Validate weights
    # -----------------------------
    if abs(w1 + w2 + w3 - 1.0) > 1e-6:
        logger.error("Weights must sum to 1.0")
        return None

    # -----------------------------
    # 2. Fetch aligned data (AS-OF SAFE)
    # -----------------------------
    query = """
        SELECT 
            p.asset_id,
            p.timestamp,
            p.adj_close,

            -- latest known fundamentals BEFORE or AT price time (no leakage)
            (
                SELECT f.eps
                FROM fundamentals f
                WHERE f.asset_id = p.asset_id
                  AND f.timestamp <= p.timestamp
                ORDER BY f.timestamp DESC
                LIMIT 1
            ) AS eps,

            (
                SELECT f.revenue
                FROM fundamentals f
                WHERE f.asset_id = p.asset_id
                  AND f.timestamp <= p.timestamp
                ORDER BY f.timestamp DESC
                LIMIT 1
            ) AS revenue,

            (
                SELECT f.shares_outstanding
                FROM fundamentals f
                WHERE f.asset_id = p.asset_id
                  AND f.timestamp <= p.timestamp
                ORDER BY f.timestamp DESC
                LIMIT 1
            ) AS shares_outstanding,

            (
                SELECT d.dividend_amount
                FROM dividends d
                WHERE d.asset_id = p.asset_id
                  AND d.timestamp <= p.timestamp
                ORDER BY d.timestamp DESC
                LIMIT 1
            ) AS dividend_amount

        FROM prices p
        WHERE p.asset_id = ?
        ORDER BY p.timestamp
    """

    df = con.execute(query, [asset_id]).df()

    if df.empty:
        return pd.DataFrame(columns=["asset_id", "timestamp", "value_factor_raw"])

    df["asset_id"] = asset_id

    # -----------------------------
    # 3. Lag adjustment (IMPORTANT)
    # -----------------------------
    # Simulate reporting delay (avoid lookahead bias)
    df[["eps", "revenue", "shares_outstanding"]] = df[
        ["eps", "revenue", "shares_outstanding"]
    ].shift(1).ffill()

    # -----------------------------
    # 4. TTM dividends
    # -----------------------------
    df["dividend_amount"] = df["dividend_amount"].fillna(0)

    df["div_ttm"] = (
        df["dividend_amount"]
        .rolling(window=252, min_periods=1)
        .sum()
    )

    # -----------------------------
    # 5. Stable price base
    # -----------------------------
    price = df["adj_close"].clip(lower=EPSILON)

    shares = df["shares_outstanding"].clip(lower=EPSILON)

    mcap = (shares * price).clip(lower=EPSILON)

    # -----------------------------
    # 6. Value components
    # -----------------------------
    df["earnings_yield"] = df["eps"] / price
    df["sales_yield"] = df["revenue"] / mcap
    df["div_yield"] = df["div_ttm"] / price

    # -----------------------------
    # 7. Clean numerical issues
    # -----------------------------
    for col in ["earnings_yield", "sales_yield", "div_yield"]:
        df.loc[~np.isfinite(df[col]), col] = np.nan

        # Winsorization (robust quant practice)
        if df[col].notna().any():
            lower = df[col].quantile(0.01)
            upper = df[col].quantile(0.99)
            df[col] = df[col].clip(lower, upper)

    # -----------------------------
    # 8. Final factor
    # -----------------------------
    df["value_factor_raw"] = (
        w1 * df["earnings_yield"] +
        w2 * df["sales_yield"] +
        w3 * df["div_yield"]
    )

    # -----------------------------
    # 9. Output
    # -----------------------------
    return df[["asset_id", "timestamp", "value_factor_raw"]]


## seems ok
def quality_factor_raw_calculator(con, asset_id, w1=0.4, w2=0.4, w3=0.2):
    """
    Output:
     asset_id, timestamp, quality_factor_raw
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    # -------------------------
    # 1. Validate weights
    # -------------------------
    if abs(w1 + w2 + w3 - 1.0) > 1e-6:
        logger.error("Weights must sum to 1.0")
        return None

    # -------------------------
    # 2. Point-in-time data (AS-OF JOIN)
    # -------------------------
    query = """
        SELECT 
            p.asset_id,
            p.timestamp,
            p.adj_close,

            (SELECT f.eps
             FROM fundamentals f
             WHERE f.asset_id = p.asset_id
               AND f.timestamp <= p.timestamp
             ORDER BY f.timestamp DESC
             LIMIT 1) AS eps,

            (SELECT f.revenue
             FROM fundamentals f
             WHERE f.asset_id = p.asset_id
               AND f.timestamp <= p.timestamp
             ORDER BY f.timestamp DESC
             LIMIT 1) AS revenue,

            (SELECT f.shares_outstanding
             FROM fundamentals f
             WHERE f.asset_id = p.asset_id
               AND f.timestamp <= p.timestamp
             ORDER BY f.timestamp DESC
             LIMIT 1) AS shares_outstanding

        FROM prices p
        WHERE p.asset_id = ?
        ORDER BY p.timestamp
    """

    df = con.execute(query, [asset_id]).df()

    if df.empty:
        return pd.DataFrame(columns=["asset_id", "timestamp", "quality_factor_raw"])

    df["asset_id"] = asset_id

    # -------------------------
    # 3. Clean fundamentals (NO time-series fill here)
    # -------------------------
    df["revenue"] = df["revenue"].clip(lower=EPSILON)
    df["shares_outstanding"] = df["shares_outstanding"].clip(lower=EPSILON)

    # EPS can be negative → keep sign
    # (important for quality differentiation)
    eps = df["eps"]

    # -------------------------
    # 4. Core financial constructions
    # -------------------------
    price = df["adj_close"].clip(lower=EPSILON)

    revenue_per_share = df["revenue"] / df["shares_outstanding"]

    # Profitability (efficiency proxy)
    df["profitability"] = eps / revenue_per_share.replace(0, np.nan)

    # Revenue scale efficiency
    df["revenue_scale"] = revenue_per_share

    # -------------------------
    # 5. Earnings stability (IMPORTANT FIX)
    # -------------------------
    # EPS is quarterly → avoid over-smoothing
    df["eps_stability"] = 1 / (
        eps.rolling(window=252, min_periods=63).std().clip(lower=EPSILON)
    )

    # -------------------------
    # 6. Clean numerical issues
    # -------------------------
    components = ["profitability", "eps_stability", "revenue_scale"]

    for col in components:
        df.loc[~np.isfinite(df[col]), col] = np.nan

        if df[col].notna().any():
            lower = df[col].quantile(0.01)
            upper = df[col].quantile(0.99)
            df[col] = df[col].clip(lower, upper)

    # -------------------------
    # 7. FINAL IMPORTANT DESIGN DECISION
    # -------------------------
    # NO normalization here (critical fix)
    # Cross-sectional normalization happens later at portfolio level

    df["quality_factor_raw"] = (
        w1 * df["profitability"] +
        w2 * df["eps_stability"] +
        w3 * df["revenue_scale"]
    )

    # -------------------------
    # 8. Output
    # -------------------------
    return df[["asset_id", "timestamp", "quality_factor_raw"]]

## seems ok
def growth_factor_raw_calculator(con , asset_id, w_eps=0.5, w_revenue=0.5):
    """
    if the asset is an ETF we will return an empty DF since growth is not relevant for ETFs
    
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6
    REPORT_LAG = pd.Timedelta(days=1)

    # -----------------------
    # 1. Validate weights
    # -----------------------
    if abs((w_eps + w_revenue) - 1.0) > 1e-6:
        logger.error("Weights must sum to 1.0")
        return None

    # -----------------------
    # 2. Load fundamentals (event data)
    # -----------------------
    f_query = """
        SELECT asset_id, timestamp, eps, revenue
        FROM fundamentals
        WHERE asset_id = ?
        ORDER BY timestamp ASC
    """
    f_df = con.execute(f_query, [asset_id]).df()

    if f_df.empty:
        return pd.DataFrame(columns=[
            "asset_id", "timestamp",
            "growth_factor_raw",
            "eps_growth_yoy",
            "revenue_growth_yoy"
        ])

    # -----------------------
    # 3. Apply reporting lag (critical for realism)
    # -----------------------
    f_df["available_timestamp"] = f_df["timestamp"] + REPORT_LAG

    # -----------------------
    # 4. Event-based YoY (NO shift assumption)
    # -----------------------
    # We compare each report to the closest report ~1 year earlier
    def compute_yoy(df, col):
        results = []

        for i, row in df.iterrows():
            target_time = row["timestamp"] - pd.Timedelta(days=365)

            past = df[
                (df["timestamp"] >= target_time - pd.Timedelta(days=60)) &
                (df["timestamp"] <= target_time + pd.Timedelta(days=60))
            ]

            if past.empty:
                results.append(np.nan)
                continue

            prev_val = past.iloc[-1][col]
            curr_val = row[col]

            if prev_val is None or abs(prev_val) < EPSILON:
                results.append(np.nan)
                continue

            growth = (curr_val - prev_val) / abs(prev_val)
            results.append(growth)

        return np.array(results)

    f_df["eps_growth_yoy"] = compute_yoy(f_df, "eps")
    f_df["revenue_growth_yoy"] = compute_yoy(f_df, "revenue")

    # -----------------------
    # 5. Winsorization (only valid values)
    # -----------------------
    for col in ["eps_growth_yoy", "revenue_growth_yoy"]:
        valid = f_df[col].replace([np.inf, -np.inf], np.nan).dropna()

        if len(valid) > 10:
            lower = valid.quantile(0.01)
            upper = valid.quantile(0.99)
            f_df[col] = f_df[col].clip(lower, upper)

    # -----------------------
    # 6. Align to trading days (NO lookahead)
    # -----------------------
    p_query = """
        SELECT asset_id, timestamp
        FROM prices
        WHERE asset_id = ?
        ORDER BY timestamp ASC
    """
    p_df = con.execute(p_query, [asset_id]).df()

    df = pd.merge_asof(
        p_df,
        f_df[["available_timestamp", "eps_growth_yoy", "revenue_growth_yoy"]],
        left_on="timestamp",
        right_on="available_timestamp",
        direction="backward"
    )

    # -----------------------
    # 7. Final factor 
    # -----------------------
    df["growth_factor_raw"] = (
        w_eps * df["eps_growth_yoy"] +
        w_revenue * df["revenue_growth_yoy"]
    )

    # keep NaN if no information exists
    missing_mask = (
        df["eps_growth_yoy"].isna() &
        df["revenue_growth_yoy"].isna()
    )

    df.loc[missing_mask, "growth_factor_raw"] = np.nan

    df["asset_id"] = asset_id

    # -----------------------
    # 8. Output
    # -----------------------
    return df[
        [
            "asset_id",
            "timestamp",
            "growth_factor_raw"
        ]
    ]
    
    
## seems to ok
def defensive_factor_raw_calculator(
    con,
    asset_id ,
    benchmark_id=504, # 504 is SPY
    w_vol=0.4,
    w_beta=0.4,
    w_dd=0.2
):
    """
    Defensive Factor (Production-Ready Version)

    OUTPUT:
            "asset_id",
            "timestamp",
            "defensive_factor_raw",
            "volatility",
            "beta_90d",
            "sharpe_90d",
            "max_drawdown_90d"
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    # -----------------------
    # 1. Validate weights
    # -----------------------
    if abs((w_vol + w_beta + w_dd) - 1.0) > 1e-6:
        logger.error("Weights must sum to 1.0")
        return None

    # -----------------------
    # 2. Load asset prices
    # -----------------------
    q_asset = """
        SELECT asset_id, timestamp, adj_close
        FROM prices
        WHERE asset_id = ?
        ORDER BY timestamp
    """
    df_asset = con.execute(q_asset, [asset_id]).df()

    # -----------------------
    # 3. Load benchmark prices
    # -----------------------
    q_bench = """
        SELECT timestamp, adj_close AS bench_price
        FROM prices
        WHERE asset_id = ?
        ORDER BY timestamp
    """
    df_bench = con.execute(q_bench, [benchmark_id]).df()

    if df_asset.empty or df_bench.empty or len(df_asset) < 100:
        return pd.DataFrame()

    # -----------------------
    # 4. Proper time alignment
    # -----------------------
    df_asset = df_asset.sort_values("timestamp")
    df_bench = df_bench.sort_values("timestamp")

    df = pd.merge_asof(
        df_asset,
        df_bench,
        on="timestamp",
        direction="backward"
    )

    # -----------------------
    # 5. Returns
    # -----------------------
    df["returns"] = df["adj_close"].pct_change()
    df["bench_returns"] = df["bench_price"].pct_change()

    # -----------------------
    # 6. Volatility (90D annualized)
    # -----------------------
    df["volatility"] = (
        df["returns"]
        .rolling(90, min_periods=20)
        .std() * np.sqrt(252)
    )

    # -----------------------
    # 7. Beta (robust)
    # -----------------------
    cov = df["returns"].rolling(90, min_periods=20).cov(df["bench_returns"])
    var = df["bench_returns"].rolling(90, min_periods=20).var()

    df["beta_90d"] = cov / var.replace(0, np.nan)

    # -----------------------
    # 8. Sharpe (risk-free = 0 assumption for ranking)
    # -----------------------
    mean_ret = df["returns"].rolling(90, min_periods=20).mean() * 252
    df["sharpe_90d"] = mean_ret / df["volatility"].replace(0, np.nan)

    # -----------------------
    # 9. Max Drawdown (vectorized, stable)
    # -----------------------
    roll_max = df["adj_close"].rolling(90, min_periods=20).max()
    drawdown = df["adj_close"] / roll_max - 1

    df["max_drawdown_90d"] = drawdown.rolling(90, min_periods=20).min()

    # -----------------------
    # 10. Convert to defensive signals
    # -----------------------
    inv_vol = 1 / df["volatility"].clip(lower=EPSILON)
    inv_beta = 1 / df["beta_90d"].abs().clip(lower=EPSILON)
    inv_dd = 1 / df["max_drawdown_90d"].abs().clip(lower=EPSILON)

    # remove invalid values only (no artificial bias)
    inv_vol = inv_vol.replace([np.inf, -np.inf], np.nan)
    inv_beta = inv_beta.replace([np.inf, -np.inf], np.nan)
    inv_dd = inv_dd.replace([np.inf, -np.inf], np.nan)

    # -----------------------
    # 11. Final factor 
    # -----------------------
    df["defensive_factor_raw"] = (
        w_vol * inv_vol +
        w_beta * inv_beta +
        w_dd * inv_dd
    )

    df["asset_id"] = asset_id

    # -----------------------
    # 12. Output
    # -----------------------
    return df[
        [
            "asset_id",
            "timestamp",
            "defensive_factor_raw"
        ]
    ]
    
## seems ok
def size_factor_raw_calculator(con, asset_id, w_mcap=0.7, w_liquidity=0.3):
    """
    Size Factor (Research / Production Grade)

    Core Idea:
    - Size = Negative log(Market Cap)  → smaller companies = higher score
    - Liquidity = log(Dollar Volume)   → avoids illiquid micro-cap traps

    IMPORTANT:
    - NO time-series normalization here
    - Cross-sectional normalization happens later at portfolio level
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    # -----------------------
    # 1. Data Fetch (Point-in-Time Market Cap)
    # -----------------------
    query = """
        SELECT 
            p.asset_id,
            p.timestamp,
            p.adj_close,
            p.volume,
            (
                SELECT f.market_cap
                FROM fundamentals f
                WHERE f.asset_id = p.asset_id
                  AND f.timestamp <= p.timestamp
                ORDER BY f.timestamp DESC
                LIMIT 1
            ) as market_cap
        FROM prices p
        WHERE p.asset_id = ?
        ORDER BY p.timestamp ASC
    """

    df = con.execute(query, [asset_id]).df()

    if df.empty:
        return pd.DataFrame(columns=["asset_id", "timestamp", "size_factor_raw"])

    df = df.sort_values("timestamp")

    # -----------------------
    # 2. Liquidity (Smoothed Dollar Volume)
    # -----------------------
    df["dollar_volume"] = df["adj_close"] * df["volume"]
    df["dollar_volume"] = df["dollar_volume"].rolling(
        window=20, min_periods=5
    ).mean()

    # -----------------------
    # 3. Safety Cleaning
    # -----------------------
    df["market_cap"] = df["market_cap"].clip(lower=EPSILON)
    df["dollar_volume"] = df["dollar_volume"].clip(lower=EPSILON)

    # -----------------------
    # 4. Feature Construction (Log Space)
    # -----------------------
    log_mcap = np.log(df["market_cap"])
    log_dollar_vol = np.log(df["dollar_volume"])

    # Size intuition:
    # smaller market cap → higher score
    size_score = -log_mcap

    # Liquidity bonus:
    liquidity_score = log_dollar_vol

    # -----------------------
    # 5. Raw Factor (NO normalization here!)
    # -----------------------
    df["size_factor_raw"] = (
        w_mcap * size_score +
        w_liquidity * liquidity_score
    )

    # -----------------------
    # 6. Output
    # -----------------------
    df["asset_id"] = asset_id

    return df[[
        "asset_id",
        "timestamp",
        "size_factor_raw"
    ]]

## seems ok
def liquidity_factor_raw_calculator(con, asset_id, window=20):
    """
    Liquidity Factor (Amihud Illiquidity Ratio)

    Core idea:
    - Measures price impact per unit of traded volume
    - Lower illiquidity = higher liquidity score

    Fixes applied:
    - Stable log returns instead of pct_change
    - Robust handling of low-volume spikes
    - Controlled smoothing
    - No log-explosion instability
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-10

    # -----------------------
    # 1. Fetch data
    # -----------------------
    query = """
        SELECT timestamp, adj_close, volume
        FROM prices
        WHERE asset_id = ?
        ORDER BY timestamp ASC
    """

    df = con.execute(query, [asset_id]).df()

    if df.empty or len(df) < window:
        return pd.DataFrame(columns=[
            "asset_id", "timestamp",
            "liquidity_factor_raw",
            "avg_volume", "dollar_volume"
        ])

    df = df.sort_values("timestamp")

    # -----------------------
    # 2. Clean inputs
    # -----------------------
    df["price"] = df["adj_close"].clip(lower=EPSILON)
    df["volume"] = df["volume"]

    # Dollar volume
    df["dollar_volume"] = (df["price"] * df["volume"]).clip(lower=EPSILON)

    # -----------------------
    # 3. Stable return calculation
    # -----------------------
    # log returns are more stable than pct_change
    df["log_return"] = np.log(df["price"]).diff().abs()

    # -----------------------
    # 4. Amihud illiquidity
    # -----------------------
    df["amihud"] = df["log_return"] / df["dollar_volume"]

    # Remove invalid values
    df.loc[~np.isfinite(df["amihud"]), "amihud"] = np.nan

    # -----------------------
    # 5. Smoothing
    # -----------------------
    df["illiquidity"] = df["amihud"].rolling(
        window=window,
        min_periods=max(5, window // 3)
    ).mean()

    # -----------------------
    # 6. Convert to liquidity factor
    # -----------------------
    # safer than log: avoids explosion for tiny values
    df["liquidity_factor_raw"] = -np.log(df["illiquidity"].clip(lower=1e-20))
    # Optional: winsorization to remove extreme spikes
    if df["liquidity_factor_raw"].notna().any():
        lower = df["liquidity_factor_raw"].quantile(0.01)
        upper = df["liquidity_factor_raw"].quantile(0.99)
        df["liquidity_factor_raw"] = df["liquidity_factor_raw"].clip(lower, upper)

    # -----------------------
    # 7. Auxiliary features
    # -----------------------
    df["avg_volume"] = df["volume"].rolling(window, min_periods=5).mean()

    df["asset_id"] = asset_id

    return df[
        [
            "asset_id",
            "timestamp",
            "liquidity_factor_raw"
        ]
    ]
    
## seems ok
def diversification_factor_raw_calculator(con, asset_id, benchmark_id=504, window=90):
    """
    Diversification Factor (Robust Correlation Model)

    Core idea:
    - Measures rolling correlation vs benchmark
    - Lower correlation = higher diversification score

    Fixes applied:
    - Proper time alignment (no silent join bias)
    - Log returns for stability
    - NaN-safe rolling correlation
    - Clean inversion logic (-corr)
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-10

    # -----------------------
    # 1. Fetch aligned data
    # -----------------------
    query = """
        SELECT 
            p.timestamp,
            p.adj_close AS asset_price,
            b.adj_close AS bench_price
        FROM prices p
        LEFT JOIN prices b
            ON p.timestamp = b.timestamp
           AND b.asset_id = ?
        WHERE p.asset_id = ?
        ORDER BY p.timestamp ASC
    """

    df = con.execute(query, [benchmark_id, asset_id]).df()

    if df.empty or len(df) < window:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "diversification_factor_raw"
        ])

    df = df.sort_values("timestamp")

    # -----------------------
    # 2. Clean prices
    # -----------------------
    df["asset_price"] = df["asset_price"].clip(lower=EPSILON)
    df["bench_price"] = df["bench_price"].clip(lower=EPSILON)

    # -----------------------
    # 3. Stable returns (log returns)
    # -----------------------
    df["asset_ret"] = np.log(df["asset_price"]).diff()
    df["bench_ret"] = np.log(df["bench_price"]).diff()

    # Clean invalid returns
    df.loc[~np.isfinite(df["asset_ret"]), "asset_ret"] = np.nan
    df.loc[~np.isfinite(df["bench_ret"]), "bench_ret"] = np.nan

    # -----------------------
    # 4. Rolling correlation (robust)
    # -----------------------
    df["correlation"] = (
        df["asset_ret"]
        .rolling(window=window, min_periods=max(20, window // 2))
        .corr(df["bench_ret"])
    )

    # -----------------------
    # 5. Convert to diversification score
    # -----------------------
    # Invert correlation (simple, stable, interpretable)
    df["diversification_factor_raw"] = -df["correlation"]

    # -----------------------
    # 6. Optional stabilization (important for portfolio stability)
    # -----------------------
    if df["diversification_factor_raw"].notna().any():
        lower = df["diversification_factor_raw"].quantile(0.01)
        upper = df["diversification_factor_raw"].quantile(0.99)
        df["diversification_factor_raw"] = df["diversification_factor_raw"].clip(lower, upper)

    # -----------------------
    # 7. Output
    # -----------------------
    df["asset_id"] = asset_id

    return df[
        [
            "asset_id",
            "timestamp",
            "diversification_factor_raw"
        ]
    ] 



def update_asset_factors_raw_v1():
    """
    Update all raw factor values for all assets in the database.
    This is a heavy operation and should be run periodically (once a week).
    The function merges individual factor dataframes on [asset_id, timestamp].
    """
    logger = logging.getLogger(__name__)

    LOOKBACK_BUFFER_DAYS = 300

    target_cols = [
        'asset_id', 'timestamp',
        'momentum_factor_raw',
        'value_factor_raw',
        'quality_factor_raw',
        'growth_factor_raw',
        'defensive_factor_raw',
        'size_factor_raw',
        'liquidity_factor_raw',
        'diversification_factor_raw'
    ]

    calculators = {
        'momentum_factor_raw': momentum_factor_raw_calculator,
        'value_factor_raw': value_factor_raw_calculator,
        'quality_factor_raw': quality_factor_raw_calculator,
        'growth_factor_raw': growth_factor_raw_calculator,  # allowed to be NaN
        'defensive_factor_raw': defensive_factor_raw_calculator,
        'size_factor_raw': size_factor_raw_calculator,
        'liquidity_factor_raw': liquidity_factor_raw_calculator,
        'diversification_factor_raw': diversification_factor_raw_calculator
    }
    
    logger.info("Starting asset_factors_raw_v1 update process")

    # -------------------------
    # OPEN CONNECTION (SAFE)
    # -------------------------
    con = duckdb.connect(DB_PATH)

    try:
        asset_ids = [
            row[0] for row in con.execute(
                "SELECT DISTINCT asset_id FROM assets"
            ).fetchall()
        ]

        total_assets = len(asset_ids)
        logger.info(f"Starting factor update for {total_assets} assets")

        all_results = []

        for i, asset_id in enumerate(asset_ids, start=1):

            # -------------------------
            # Progress indicator
            # -------------------------
            progress = (i / total_assets) * 100
            sys.stdout.write(f"\rRaw Factors Calculation: Processing assets: {i}/{total_assets} ({progress:.1f}%)")
            sys.stdout.flush()

            try:
                # -------------------------
                # 1. Get last timestamp
                # -------------------------
                last_ts_row = con.execute("""
                    SELECT MAX(timestamp)
                    FROM asset_factors_raw_v1
                    WHERE asset_id = ?
                """, [asset_id]).fetchone()

                last_ts = last_ts_row[0] if last_ts_row and last_ts_row[0] else None

                # -------------------------
                # 2. Define start date with buffer
                # -------------------------
                if last_ts:
                    start_date = pd.to_datetime(last_ts) - pd.Timedelta(days=LOOKBACK_BUFFER_DAYS)
                else:
                    start_date = None

                # -------------------------
                # 3. Fetch price timeline
                # -------------------------
                if start_date:
                    prices_df = con.execute("""
                        SELECT asset_id, timestamp
                        FROM prices
                        WHERE asset_id = ? AND timestamp >= ?
                        ORDER BY timestamp
                    """, [asset_id, start_date]).df()
                else:
                    prices_df = con.execute("""
                        SELECT asset_id, timestamp
                        FROM prices
                        WHERE asset_id = ?
                        ORDER BY timestamp
                    """, [asset_id]).df()

                if prices_df.empty:
                    continue

                prices_df = prices_df.sort_values("timestamp")
                final_df = prices_df.copy()

                # -------------------------
                # 4. Merge factors
                # -------------------------
                for col_name, calc_func in calculators.items():
                    try:
                        f_df = calc_func(con ,asset_id)

                        if f_df is None or f_df.empty:
                            continue

                        if col_name not in f_df.columns:
                            continue

                        f_df = f_df[['timestamp', col_name]].copy()
                        f_df = f_df.drop_duplicates(subset=["timestamp"])
                        f_df = f_df.sort_values("timestamp")

                        # ensure sorted before merge_asof (safety)
                        final_df = final_df.sort_values("timestamp")

                        final_df = pd.merge_asof(
                            final_df,
                            f_df,
                            on="timestamp",
                            direction="backward"
                        )

                    except Exception as e:
                        logger.warning(f"{col_name} failed for asset {asset_id}: {e}")
                        continue

                # -------------------------
                # 5. Clean
                # -------------------------
                final_df.replace([np.inf, -np.inf], np.nan, inplace=True)

                # IMPORTANT:
                # Growth is allowed to be NaN → exclude it from drop condition
                factor_cols = [
                    c for c in target_cols
                    if c not in ['asset_id', 'timestamp', 'growth_factor_raw']
                ]

                final_df = final_df.dropna(subset=factor_cols, how='all')

                if final_df.empty:
                    continue

                # -------------------------
                # 6. Keep only NEW rows
                # -------------------------
                if last_ts:
                    final_df = final_df[final_df["timestamp"] > last_ts]

                if final_df.empty:
                    continue

                # -------------------------
                # 7. Ensure schema
                # -------------------------
                for col in target_cols:
                    if col not in final_df.columns:
                        final_df[col] = np.nan

                final_df = final_df[target_cols]

                all_results.append(final_df)

            except Exception as e:
                logger.error(f"Error processing asset {asset_id}: {e}")
                continue

        # New line after progress bar
        logger.info("\nFactor calculation completed for all assets. Starting database update...")

        # -------------------------
        # 8. Batch insert
        # -------------------------
        if not all_results:
            logger.warning("No new data to insert")
            
            return

        final_insert_df = pd.concat(all_results, ignore_index=True)

        con.register("temp_factors", final_insert_df)

        # -------------------------
        # TRANSACTION (SAFE INSERT)
        # -------------------------
        con.execute("BEGIN")

        con.execute("""
            INSERT OR REPLACE INTO asset_factors_raw_v1
            SELECT * FROM temp_factors
        """)

        con.execute("COMMIT")

        logger.info(f"Inserted/Updated {len(final_insert_df)} rows successfully")

    except Exception as e:
        logger.error(f"Critical pipeline failure: {e}")

        # -------------------------
        # SAFE ROLLBACK
        # -------------------------
        try:
            con.execute("ROLLBACK")
        except:
            pass

    finally:
        # -------------------------
        # ALWAYS CLOSE CONNECTION
        # -------------------------
        con.close()









update_asset_factors_raw_v1()



