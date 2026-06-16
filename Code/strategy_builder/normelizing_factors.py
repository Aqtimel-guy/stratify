import duckdb
import pandas as pd
import numpy as np
import logging
import sys
from scipy.stats import norm


DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'  


## need to fix con scope



def update_factors_zscore(window=252):
    
    """
    Rolling Z-Score normalization (NO LOOKAHEAD BIAS).

    - Market Z-score: rolling across all assets
    - Sector Z-score: rolling within sector (via cached mapping)
    - Fully time-series consistent (true rolling window)
    - Incremental update only
    - Optimized: no repeated JOINs, no per-factor merges
    """

    logger = logging.getLogger(__name__)
    
    # Using 'with' statement ensures the connection is closed automatically
    with duckdb.connect(DB_PATH) as con:
        factors = [
            "momentum_factor",
            "value_factor",
            "quality_factor",
            "growth_factor",
            "defensive_factor",
            "size_factor",
            "liquidity_factor",
            "diversification_factor"
        ]

        try:
            # -------------------------------------------------
            # 1. Incremental update
            # -------------------------------------------------
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_zscore
            """).fetchone()[0]

            if last_ts:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    WHERE timestamp > ?
                    ORDER BY timestamp
                """, [last_ts]).df()["timestamp"].tolist()
            else:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    ORDER BY timestamp
                """).df()["timestamp"].tolist()

            if not dates:
                logger.info("Z-score already up to date.")
                return # Connection closes automatically via context manager

            # -------------------------------------------------
            # 2. Sector mapping (cached ONCE)
            # -------------------------------------------------
            sector_map_df = con.execute("""
                SELECT asset_id, sector
                FROM assets
            """).df()

            sector_map = dict(zip(sector_map_df.asset_id, sector_map_df.sector))

            # -------------------------------------------------
            # 3. Rolling loop
            # -------------------------------------------------
            for i, ts in enumerate(dates, 1):

                sys.stdout.write(f"\rRolling Z-Score: {i}/{len(dates)}")
                sys.stdout.flush()

                # 3.1 Rolling window (no leakage)
                start_ts = pd.to_datetime(ts) - pd.Timedelta(days=window)
                window_df = con.execute("""
                    SELECT *
                    FROM asset_factors_raw_v1
                    WHERE timestamp <= ?
                    AND timestamp > ?
                """, [ts, start_ts]).df()

                if window_df.empty:
                    logger.warning(f"No data in rolling window for timestamp {ts}. Skipping.")
                    continue

                # attach sector without JOIN
                window_df["sector"] = window_df["asset_id"].map(sector_map)

                # isolate "today"
                today_mask = window_df["timestamp"] == ts
                result_today = window_df[today_mask].copy()

                if result_today.empty:
                    logger.warning(f"No data for current timestamp {ts}. Skipping.")
                    continue

                # clean once
                window_df.replace([np.inf, -np.inf], np.nan, inplace=True)

                # 3.2 Vectorized rolling stats
                for f in factors:
                    raw = f"{f}_raw"
                    m_col = f"{f}_market"
                    s_col = f"{f}_sector"

                    if raw not in window_df.columns:
                        logger.warning(f"Missing raw column {raw} for timestamp {ts}. Skipping factor.")
                        continue

                    # MARKET Z-SCORE
                    mu = window_df[raw].mean()
                    sigma = window_df[raw].std()

                    if sigma > 1e-9:
                        result_today[m_col] = (result_today[raw] - mu) / sigma
                    else:
                        result_today[m_col] = 0.0

                    # SECTOR Z-SCORE
                    sector_stats = window_df.groupby("sector")[raw].agg(["mean", "std"])
                    result_today = result_today.merge(sector_stats, on="sector", how="left")

                    valid = result_today["std"] > 1e-9
                    result_today.loc[valid, s_col] = (
                        (result_today.loc[valid, raw] - result_today.loc[valid, "mean"])
                        / result_today.loc[valid, "std"]
                    )
                    result_today.loc[~valid, s_col] = 0.0
                    result_today.drop(columns=["mean", "std"], inplace=True)

                    # CLIPPING
                    result_today[m_col] = result_today[m_col].clip(-3, 3)
                    result_today[s_col] = result_today[s_col].clip(-3, 3)

                # 3.3 Final cleanup
                score_cols = [c for c in result_today.columns if c.endswith("_market") or c.endswith("_sector")]
                result_today[score_cols] = result_today[score_cols].fillna(0.0)
                final_df = result_today[["asset_id", "timestamp"] + score_cols]

                # 3.4 DB write
                con.register("temp_z", final_df)
                con.execute("""
                    INSERT OR REPLACE INTO asset_factors_normalized_zscore
                    SELECT * FROM temp_z
                """)

            logger.info("\nRolling Z-score update complete.")

        except Exception as e:
            logger.error(f"Rolling Z-score pipeline failed: {e}")
            # No need for manual close/rollback here as 'with' handles cleanup
            raise


def update_factors_percentile():
    """
    Cross-sectional percentile normalization for raw factors.
    """
    logger = logging.getLogger(__name__)

    factors = [
        'momentum_factor',
        'value_factor',
        'quality_factor',
        'growth_factor',
        'defensive_factor',
        'size_factor',
        'liquidity_factor',
        'diversification_factor'
    ]

    # Using 'with' ensures the connection is opened and closed correctly
    with duckdb.connect(DB_PATH) as con:
        try:
            # ----------------------------
            # 1. Incremental timestamps
            # ----------------------------
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_percentile
            """).fetchone()[0]

            if last_ts:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    WHERE timestamp > ?
                    ORDER BY timestamp
                """, [last_ts]).df()["timestamp"].tolist()
            else:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    ORDER BY timestamp
                """).df()["timestamp"].tolist()

            if not dates:
                logger.info("Percentile table already up to date.")
                return

            # ----------------------------
            # 2. Sector mapping (cached)
            # ----------------------------
            sector_map_df = con.execute("""
                SELECT asset_id, sector 
                FROM assets
            """).df()

            sector_map = dict(zip(sector_map_df.asset_id, sector_map_df.sector))

            # ----------------------------
            # 3. Main loop
            # ----------------------------
            all_results = []

            for i, ts in enumerate(dates, 1):
                sys.stdout.write(f"\rPercentile Progress: {i}/{len(dates)}")
                sys.stdout.flush()

                today_df = con.execute("""
                    SELECT *
                    FROM asset_factors_raw_v1
                    WHERE timestamp = ?
                """, [ts]).df()

                if today_df.empty:
                    continue

                # Attach sector (safe fallback)
                today_df["sector"] = (
                    today_df["asset_id"]
                    .map(sector_map)
                    .fillna("UNKNOWN")
                )

                # Clean infinities globally once
                today_df.replace([np.inf, -np.inf], np.nan, inplace=True)

                result_today = today_df.copy()

                # ----------------------------
                # 4. Compute percentiles
                # ----------------------------
                for f in factors:
                    raw_col = f"{f}_raw"
                    m_col = f"{f}_market"
                    s_col = f"{f}_sector"

                    if raw_col not in today_df.columns:
                        continue

                    values = today_df[raw_col]

                    # --- Market Percentile ---
                    result_today[m_col] = (
                        values.rank(pct=True, method="average") * 100
                    )

                    # --- Sector Percentile ---
                    result_today[s_col] = (
                        today_df.groupby("sector")[raw_col]
                        .transform(
                            lambda x: x.rank(pct=True, method="average") * 100
                            if x.notna().sum() > 1 else 50.0
                        )
                    )

                # ----------------------------
                # 5. Cleanup
                # ----------------------------
                score_cols = [
                    c for c in result_today.columns
                    if c.endswith("_market") or c.endswith("_sector")
                ]

                result_today[score_cols] = result_today[score_cols].fillna(50.0)

                final_df = result_today[["asset_id", "timestamp"] + score_cols]

                all_results.append(final_df)

            # ----------------------------
            # 6. Batch insert (FAST)
            # ----------------------------
            if not all_results:
                logger.info("No new percentile data to insert.")
                return

            final_insert_df = pd.concat(all_results, ignore_index=True)

            # Safety clip
            score_cols = [
                c for c in final_insert_df.columns
                if c.endswith("_market") or c.endswith("_sector")
            ]
            final_insert_df[score_cols] = final_insert_df[score_cols].clip(0, 100)

            con.register("temp_percentile", final_insert_df)

            con.execute("""
                INSERT OR REPLACE INTO asset_factors_normalized_percentile
                SELECT * FROM temp_percentile
            """)

            logger.log(f"\nCross-sectional percentile update complete. Rows: {len(final_insert_df)}")

        except Exception as e:
            logger.error(f"Percentile pipeline failed: {e}")
            raise
        
        
def update_asset_factors_normelized_final(w1=0.7, w2=0.3):
    """
    Combines Z-score and Percentile into final UI score (0-100).

    Logic:
    - Z-score → converted via Normal CDF → [0,100]
    - Percentile → already [0,100]
    - Final = weighted average (w1 for Z, w2 for P)
    """

    logger = logging.getLogger(__name__)

    # factors
    factors = [
        'momentum_factor_sector','momentum_factor_market',
        'value_factor_sector','value_factor_market', 
        'quality_factor_sector','quality_factor_market',
        'growth_factor_sector','growth_factor_market',
        'defensive_factor_sector','defensive_factor_market',
        'size_factor_sector','size_factor_market', 
        'liquidity_factor_sector','liquidity_factor_market',
        'diversification_factor_sector','diversification_factor_market'
    ]

    # ----------------------------
    # 0. Validate weights
    # ----------------------------
    if not np.isclose(w1 + w2, 1.0):
        raise ValueError("Weights must sum to 1")

    # ----------------------------
    # OPEN CONNECTION (SAFE)
    # ----------------------------
    with duckdb.connect(DB_PATH) as con:
        try:
            # ---------------------------------------
            # 1. Incremental timestamps
            # ---------------------------------------
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_final
            """).fetchone()[0]

            if last_ts:
                z_df = con.execute("""
                    SELECT *
                    FROM asset_factors_normalized_zscore
                    WHERE timestamp > ?
                """, [last_ts]).df()

                p_df = con.execute("""
                    SELECT *
                    FROM asset_factors_normalized_percentile
                    WHERE timestamp > ?
                """, [last_ts]).df()
            else:
                z_df = con.execute("""
                    SELECT *
                    FROM asset_factors_normalized_zscore
                """).df()

                p_df = con.execute("""
                    SELECT *
                    FROM asset_factors_normalized_percentile
                """).df()

            if z_df.empty or p_df.empty:
                logger.info("No new data to process.")
                return

            # ---------------------------------------
            # 2. Merge (IMPORTANT: OUTER)
            # ---------------------------------------
            merged = pd.merge(
                z_df,
                p_df,
                on=['asset_id', 'timestamp'],
                suffixes=('_z', '_p'),
                how="outer"
            )

            if merged.empty:
                logger.info("Merged dataframe is empty.")
                return

            # ---------------------------------------
            # 3. Prepare result
            # ---------------------------------------
            result = merged[['asset_id', 'timestamp']].copy()

            # ---------------------------------------
            # 4. Compute final score
            # ---------------------------------------
            for col in factors:

                z_col = f"{col}_z"
                p_col = f"{col}_p"

                if z_col not in merged.columns or p_col not in merged.columns:
                    continue  # skip silently (cleaner logs)

                # Safe fills
                z = merged[z_col].fillna(0.0).clip(-5, 5)
                p = merged[p_col].fillna(50.0)

                # Z-score → percentile via Normal CDF
                z_cdf = norm.cdf(z) * 100

                # Final weighted score
                result[col] = (w1 * z_cdf) + (w2 * p)

            # ---------------------------------------
            # 5. Cleanup
            # ---------------------------------------
            score_cols = [
                c for c in result.columns
                if c not in ['asset_id', 'timestamp']
            ]

            result[score_cols] = result[score_cols].clip(0, 100).round(2)

            # ---------------------------------------
            # 6. Batch insert (UPSERT)
            # ---------------------------------------
            con.register("temp_final", result)

            con.execute("""
                INSERT OR REPLACE INTO asset_factors_normalized_final
                SELECT * FROM temp_final
            """)

            logger.info(f"Final scores updated: {len(result)} rows")

        except Exception as e:
            logger.error(f"UI Score calculation failed: {e}")
            raise
        
        
        

        

