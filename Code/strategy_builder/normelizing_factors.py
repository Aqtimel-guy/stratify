import duckdb
import pandas as pd
import numpy as np
import logging
import sys
from scipy.stats import norm


DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'  


## need to fix con scope



def update_factors_zscore(window=252, recalc_buffer_days=300):
    """
    Updates rolling Z-score normalized factors.

    Active factors:
    - momentum_factor
    - value_factor
    - quality_factor
    - growth_factor
    - defensive_factor
    - size_factor

    Normalization logic:
    - Market Z-score: rolling window across all assets
    - Sector Z-score: rolling window within sector
    - No lookahead bias: each timestamp uses only raw rows up to that timestamp
    - Recalculates a recent buffer window to stay consistent with raw factor updates
    """

    logger = logging.getLogger(__name__)

    active_factors = [
        "momentum_factor",
        "value_factor",
        "quality_factor",
        "growth_factor",
        "defensive_factor",
        "size_factor",
    ]

    output_cols = ["asset_id", "timestamp"]

    for factor in active_factors:
        output_cols.append(f"{factor}_market")
        output_cols.append(f"{factor}_sector")

    logger.info("Starting rolling Z-score update process")

    with duckdb.connect(DB_PATH) as con:
        try:
            # ======================================================
            # 1. DETERMINE DATES TO RECALCULATE
            # ======================================================
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_zscore
            """).fetchone()[0]

            if last_ts is not None:
                start_recalc_ts = pd.to_datetime(last_ts) - pd.Timedelta(days=recalc_buffer_days)

                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, [start_recalc_ts]).df()["timestamp"].tolist()
            else:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    ORDER BY timestamp ASC
                """).df()["timestamp"].tolist()

            if not dates:
                logger.info("Z-score table is already up to date.")
                return

            logger.info(f"Preparing Z-score recalculation for {len(dates)} timestamps")

            # ======================================================
            # 2. LOAD SECTOR MAP ONCE
            # ======================================================
            sector_map_df = con.execute("""
                SELECT
                    asset_id,
                    sector
                FROM assets
            """).df()

            sector_map = dict(
                zip(sector_map_df["asset_id"], sector_map_df["sector"])
            )

            all_results = []

            # ======================================================
            # 3. PROCESS EACH TIMESTAMP
            # ======================================================
            for i, ts in enumerate(dates, start=1):
                sys.stdout.write(
                    f"\rRolling Z-Score: {i}/{len(dates)}"
                )
                sys.stdout.flush()

                ts = pd.to_datetime(ts)
                start_window_ts = ts - pd.Timedelta(days=window)

                # ======================================================
                # 3.1 LOAD ROLLING WINDOW RAW FACTORS
                # ======================================================
                window_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_raw,
                        value_factor_raw,
                        quality_factor_raw,
                        growth_factor_raw,
                        defensive_factor_raw,
                        size_factor_raw
                    FROM asset_factors_raw_v1
                    WHERE timestamp <= ?
                      AND timestamp > ?
                    ORDER BY timestamp ASC, asset_id ASC
                """, [ts, start_window_ts]).df()

                if window_df.empty:
                    logger.warning(f"No raw factor data in rolling window for {ts}. Skipping.")
                    continue

                window_df["timestamp"] = pd.to_datetime(window_df["timestamp"])
                window_df.replace([np.inf, -np.inf], np.nan, inplace=True)
                window_df["sector"] = window_df["asset_id"].map(sector_map)

                # ======================================================
                # 3.2 ISOLATE CURRENT TIMESTAMP
                # ======================================================
                result_today = window_df[window_df["timestamp"] == ts].copy()

                if result_today.empty:
                    logger.warning(f"No raw factor rows for current timestamp {ts}. Skipping.")
                    continue

                # ======================================================
                # 3.3 CALCULATE MARKET AND SECTOR Z-SCORES
                # ======================================================
                for factor in active_factors:
                    raw_col = f"{factor}_raw"
                    market_col = f"{factor}_market"
                    sector_col = f"{factor}_sector"

                    if raw_col not in window_df.columns:
                        logger.warning(f"Missing raw column {raw_col}. Skipping.")
                        continue

                    # ------------------------------
                    # Market Z-score
                    # ------------------------------
                    market_mean = window_df[raw_col].mean(skipna=True)
                    market_std = window_df[raw_col].std(skipna=True)

                    raw_today = result_today[raw_col]

                    if pd.notna(market_std) and market_std > 1e-9:
                        result_today[market_col] = (raw_today - market_mean) / market_std
                    else:
                        result_today[market_col] = np.nan

                    # Keep missing raw values as missing.
                    result_today.loc[raw_today.isna(), market_col] = np.nan

                    # ------------------------------
                    # Sector Z-score
                    # ------------------------------
                    sector_stats = (
                        window_df
                        .groupby("sector", dropna=False)[raw_col]
                        .agg(["mean", "std"])
                        .reset_index()
                        .rename(columns={
                            "mean": f"{factor}_sector_mean",
                            "std": f"{factor}_sector_std",
                        })
                    )

                    result_today = result_today.merge(
                        sector_stats,
                        on="sector",
                        how="left"
                    )

                    sector_mean_col = f"{factor}_sector_mean"
                    sector_std_col = f"{factor}_sector_std"

                    valid_sector_std = (
                        result_today[sector_std_col].notna() &
                        (result_today[sector_std_col] > 1e-9)
                    )

                    result_today[sector_col] = np.nan

                    result_today.loc[valid_sector_std, sector_col] = (
                        (
                            result_today.loc[valid_sector_std, raw_col] -
                            result_today.loc[valid_sector_std, sector_mean_col]
                        )
                        / result_today.loc[valid_sector_std, sector_std_col]
                    )

                    result_today.loc[result_today[raw_col].isna(), sector_col] = np.nan

                    result_today.drop(
                        columns=[sector_mean_col, sector_std_col],
                        inplace=True
                    )

                    # ------------------------------
                    # Clipping
                    # ------------------------------
                    result_today[market_col] = result_today[market_col].clip(-3, 3)
                    result_today[sector_col] = result_today[sector_col].clip(-3, 3)

                # ======================================================
                # 3.4 FINALIZE CURRENT TIMESTAMP OUTPUT
                # ======================================================
                for col in output_cols:
                    if col not in result_today.columns:
                        result_today[col] = np.nan

                final_today = result_today[output_cols].copy()

                # Keep rows that have at least one normalized value.
                score_cols = [col for col in output_cols if col not in ["asset_id", "timestamp"]]

                final_today = final_today.dropna(
                    subset=score_cols,
                    how="all"
                )

                if final_today.empty:
                    continue

                all_results.append(final_today)

            sys.stdout.write("\n")
            sys.stdout.flush()

            # ======================================================
            # 4. INSERT / REPLACE RESULTS
            # ======================================================
            if not all_results:
                logger.warning("No Z-score rows to insert/update.")
                return

            final_insert_df = pd.concat(all_results, ignore_index=True)

            final_insert_df = final_insert_df.drop_duplicates(
                subset=["asset_id", "timestamp"],
                keep="last"
            )

            final_insert_df["timestamp"] = pd.to_datetime(final_insert_df["timestamp"])

            logger.info(f"Prepared {len(final_insert_df)} Z-score rows for insert/replace")

            con.register("temp_zscore_factors", final_insert_df)

            transaction_started = False

            try:
                con.execute("BEGIN")
                transaction_started = True

                con.execute("""
                    INSERT OR REPLACE INTO asset_factors_normalized_zscore (
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    )
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM temp_zscore_factors
                """)

                con.execute("COMMIT")
                transaction_started = False

                logger.info(
                    f"Inserted/Replaced {len(final_insert_df)} rows into asset_factors_normalized_zscore"
                )

            except Exception as e:
                if transaction_started:
                    try:
                        con.execute("ROLLBACK")
                    except Exception as rollback_error:
                        logger.warning(f"Rollback failed: {rollback_error}")

                logger.error(f"Z-score insert/replace failed: {e}")
                raise

        except Exception as e:
            logger.error(f"Rolling Z-score pipeline failed: {e}")
            raise
        
        
def update_factors_percentile(recalc_buffer_days=300):
    """
    Updates cross-sectional percentile normalization for active raw factors.

    Active factors:
    - momentum_factor
    - value_factor
    - quality_factor
    - growth_factor
    - defensive_factor
    - size_factor

    Logic:
    - Market percentile compares assets against all assets on the same timestamp.
    - Sector percentile compares assets against assets in the same sector on the same timestamp.
    - Missing raw values remain missing.
    - If a sector has only one valid value for a factor, that valid value receives 50.
    - Recent buffer is recalculated to stay consistent with raw factor replacements.
    """

    logger = logging.getLogger(__name__)

    active_factors = [
        "momentum_factor",
        "value_factor",
        "quality_factor",
        "growth_factor",
        "defensive_factor",
        "size_factor",
    ]

    output_cols = ["asset_id", "timestamp"]

    for factor in active_factors:
        output_cols.append(f"{factor}_market")
        output_cols.append(f"{factor}_sector")

    logger.info("Starting percentile normalization update process")

    with duckdb.connect(DB_PATH) as con:
        try:
            # ======================================================
            # 1. DETERMINE DATES TO RECALCULATE
            # ======================================================
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_percentile
            """).fetchone()[0]

            if last_ts is not None:
                start_recalc_ts = pd.to_datetime(last_ts) - pd.Timedelta(days=recalc_buffer_days)

                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, [start_recalc_ts]).df()["timestamp"].tolist()
            else:
                dates = con.execute("""
                    SELECT DISTINCT timestamp
                    FROM asset_factors_raw_v1
                    ORDER BY timestamp ASC
                """).df()["timestamp"].tolist()

            if not dates:
                logger.info("Percentile table is already up to date.")
                return

            logger.info(f"Preparing percentile recalculation for {len(dates)} timestamps")

            # ======================================================
            # 2. LOAD SECTOR MAP ONCE
            # ======================================================
            sector_map_df = con.execute("""
                SELECT
                    asset_id,
                    sector
                FROM assets
            """).df()

            sector_map = dict(
                zip(sector_map_df["asset_id"], sector_map_df["sector"])
            )

            all_results = []

            # ======================================================
            # 3. PROCESS EACH TIMESTAMP
            # ======================================================
            for i, ts in enumerate(dates, start=1):
                sys.stdout.write(
                    f"\rPercentile Progress: {i}/{len(dates)}"
                )
                sys.stdout.flush()

                today_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_raw,
                        value_factor_raw,
                        quality_factor_raw,
                        growth_factor_raw,
                        defensive_factor_raw,
                        size_factor_raw
                    FROM asset_factors_raw_v1
                    WHERE timestamp = ?
                    ORDER BY asset_id ASC
                """, [ts]).df()

                if today_df.empty:
                    continue

                today_df["timestamp"] = pd.to_datetime(today_df["timestamp"])

                today_df["sector"] = (
                    today_df["asset_id"]
                    .map(sector_map)
                    .fillna("UNKNOWN")
                )

                today_df.replace([np.inf, -np.inf], np.nan, inplace=True)

                result_today = today_df[["asset_id", "timestamp", "sector"]].copy()

                # ======================================================
                # 4. COMPUTE MARKET AND SECTOR PERCENTILES
                # ======================================================
                for factor in active_factors:
                    raw_col = f"{factor}_raw"
                    market_col = f"{factor}_market"
                    sector_col = f"{factor}_sector"

                    if raw_col not in today_df.columns:
                        logger.warning(f"Missing raw column {raw_col}. Skipping.")
                        continue

                    # ------------------------------
                    # Market percentile
                    # ------------------------------
                    result_today[market_col] = (
                        today_df[raw_col]
                        .rank(pct=True, method="average") * 100
                    )

                    # Missing raw values must remain missing.
                    result_today.loc[today_df[raw_col].isna(), market_col] = np.nan

                    # ------------------------------
                    # Sector percentile
                    # ------------------------------
                    sector_percentile = (
                        today_df
                        .groupby("sector", dropna=False)[raw_col]
                        .transform(lambda x: x.rank(pct=True, method="average") * 100)
                    )

                    valid_count_by_sector = (
                        today_df
                        .groupby("sector", dropna=False)[raw_col]
                        .transform(lambda x: x.notna().sum())
                    )

                    # If there is only one valid value in the sector, give that valid value neutral 50.
                    sector_percentile = sector_percentile.where(
                        valid_count_by_sector > 1,
                        50.0
                    )

                    # But missing raw values still remain missing.
                    sector_percentile = sector_percentile.where(
                        today_df[raw_col].notna(),
                        np.nan
                    )

                    result_today[sector_col] = sector_percentile

                # ======================================================
                # 5. FINALIZE CURRENT TIMESTAMP
                # ======================================================
                for col in output_cols:
                    if col not in result_today.columns:
                        result_today[col] = np.nan

                final_today = result_today[output_cols].copy()

                score_cols = [
                    col for col in output_cols
                    if col not in ["asset_id", "timestamp"]
                ]

                final_today[score_cols] = final_today[score_cols].clip(0, 100)

                final_today = final_today.dropna(
                    subset=score_cols,
                    how="all"
                )

                if final_today.empty:
                    continue

                all_results.append(final_today)

            sys.stdout.write("\n")
            sys.stdout.flush()

            # ======================================================
            # 6. BATCH INSERT
            # ======================================================
            if not all_results:
                logger.info("No percentile rows to insert/update.")
                return

            final_insert_df = pd.concat(all_results, ignore_index=True)

            if final_insert_df.empty:
                logger.info("Final percentile insert dataframe is empty.")
                return

            final_insert_df = final_insert_df.drop_duplicates(
                subset=["asset_id", "timestamp"],
                keep="last"
            )

            final_insert_df["timestamp"] = pd.to_datetime(final_insert_df["timestamp"])

            logger.info(
                f"Prepared {len(final_insert_df)} percentile rows for insert/replace"
            )

            con.register("temp_percentile_factors", final_insert_df)

            # ======================================================
            # 7. SAFE INSERT / REPLACE
            # ======================================================
            transaction_started = False

            try:
                con.execute("BEGIN")
                transaction_started = True

                con.execute("""
                    INSERT OR REPLACE INTO asset_factors_normalized_percentile (
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    )
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM temp_percentile_factors
                """)

                con.execute("COMMIT")
                transaction_started = False

                logger.info(
                    f"Inserted/Replaced {len(final_insert_df)} rows into asset_factors_normalized_percentile"
                )

            except Exception as e:
                if transaction_started:
                    try:
                        con.execute("ROLLBACK")
                    except Exception as rollback_error:
                        logger.warning(f"Rollback failed: {rollback_error}")

                logger.error(f"Percentile insert/replace failed: {e}")
                raise

        except Exception as e:
            logger.error(f"Percentile pipeline failed: {e}")
            raise
     
     
        
def update_asset_factors_normalized_final(
    w_zscore=0.70,
    w_percentile=0.30,
    recalc_buffer_days=300
):
    """
    Combines Z-score and Percentile normalized factors into final scores.

    Final score logic:
    - Z-score is converted to 0-100 using Normal CDF.
    - Percentile is already 0-100.
    - If both sources exist: weighted average.
    - If only one source exists: use the available source.
    - If both are missing: keep NaN.

    Active factors:
    - momentum
    - value
    - quality
    - growth
    - defensive
    - size
    """

    logger = logging.getLogger(__name__)

    if not np.isclose(w_zscore + w_percentile, 1.0):
        raise ValueError("Weights must sum to 1")

    factor_cols = [
        "momentum_factor_sector",
        "momentum_factor_market",
        "value_factor_sector",
        "value_factor_market",
        "quality_factor_sector",
        "quality_factor_market",
        "growth_factor_sector",
        "growth_factor_market",
        "defensive_factor_sector",
        "defensive_factor_market",
        "size_factor_sector",
        "size_factor_market",
    ]

    output_cols = [
        "asset_id",
        "timestamp",
        *factor_cols,
    ]

    logger.info("Starting final normalized factor update process")

    with duckdb.connect(DB_PATH) as con:
        try:
            # ======================================================
            # 1. DETERMINE RECALCULATION RANGE
            # ======================================================
            last_ts = con.execute("""
                SELECT MAX(timestamp)
                FROM asset_factors_normalized_final
            """).fetchone()[0]

            if last_ts is not None:
                start_recalc_ts = pd.to_datetime(last_ts) - pd.Timedelta(days=recalc_buffer_days)

                z_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM asset_factors_normalized_zscore
                    WHERE timestamp >= ?
                """, [start_recalc_ts]).df()

                p_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM asset_factors_normalized_percentile
                    WHERE timestamp >= ?
                """, [start_recalc_ts]).df()

            else:
                z_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM asset_factors_normalized_zscore
                """).df()

                p_df = con.execute("""
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_market,
                        momentum_factor_sector,
                        value_factor_market,
                        value_factor_sector,
                        quality_factor_market,
                        quality_factor_sector,
                        growth_factor_market,
                        growth_factor_sector,
                        defensive_factor_market,
                        defensive_factor_sector,
                        size_factor_market,
                        size_factor_sector
                    FROM asset_factors_normalized_percentile
                """).df()

            if z_df.empty and p_df.empty:
                logger.info("No normalized data to process.")
                return

            # ======================================================
            # 2. PREPARE INPUTS
            # ======================================================
            if not z_df.empty:
                z_df["timestamp"] = pd.to_datetime(z_df["timestamp"])
                z_df.replace([np.inf, -np.inf], np.nan, inplace=True)

            if not p_df.empty:
                p_df["timestamp"] = pd.to_datetime(p_df["timestamp"])
                p_df.replace([np.inf, -np.inf], np.nan, inplace=True)

            # ======================================================
            # 3. MERGE Z-SCORE AND PERCENTILE
            # ======================================================
            merged = pd.merge(
                z_df,
                p_df,
                on=["asset_id", "timestamp"],
                suffixes=("_z", "_p"),
                how="outer"
            )

            if merged.empty:
                logger.info("Merged dataframe is empty.")
                return

            result = merged[["asset_id", "timestamp"]].copy()

            # ======================================================
            # 4. COMPUTE FINAL SCORES
            # ======================================================
            for col in factor_cols:
                z_col = f"{col}_z"
                p_col = f"{col}_p"

                z_available = z_col in merged.columns
                p_available = p_col in merged.columns

                if not z_available and not p_available:
                    result[col] = np.nan
                    continue

                z_score_0_100 = None
                percentile_score = None

                if z_available:
                    z_raw = merged[z_col].copy()
                    z_raw = z_raw.clip(-5, 5)
                    z_score_0_100 = pd.Series(
                        norm.cdf(z_raw) * 100,
                        index=merged.index
                    )
                    z_score_0_100.loc[z_raw.isna()] = np.nan

                if p_available:
                    percentile_score = merged[p_col].copy()
                    percentile_score = percentile_score.clip(0, 100)
                    percentile_score.loc[percentile_score.isna()] = np.nan

                # --------------------------------------------------
                # Combine sources without inventing missing data.
                # --------------------------------------------------
                if z_score_0_100 is not None and percentile_score is not None:
                    weighted_sum = (
                        z_score_0_100.fillna(0) * w_zscore +
                        percentile_score.fillna(0) * w_percentile
                    )

                    available_weight = (
                        z_score_0_100.notna().astype(float) * w_zscore +
                        percentile_score.notna().astype(float) * w_percentile
                    )

                    result[col] = weighted_sum / available_weight
                    result.loc[available_weight == 0, col] = np.nan

                elif z_score_0_100 is not None:
                    result[col] = z_score_0_100

                elif percentile_score is not None:
                    result[col] = percentile_score

            # ======================================================
            # 5. CLEAN FINAL OUTPUT
            # ======================================================
            score_cols = [
                c for c in result.columns
                if c not in ["asset_id", "timestamp"]
            ]

            result[score_cols] = result[score_cols].clip(0, 100).round(2)

            result = result.dropna(
                subset=score_cols,
                how="all"
            )

            if result.empty:
                logger.info("No final normalized rows to insert/update.")
                return

            result = result.drop_duplicates(
                subset=["asset_id", "timestamp"],
                keep="last"
            )

            result["timestamp"] = pd.to_datetime(result["timestamp"])

            for col in output_cols:
                if col not in result.columns:
                    result[col] = np.nan

            result = result[output_cols]

            logger.info(f"Prepared {len(result)} final normalized rows for insert/replace")

            # ======================================================
            # 6. INSERT / REPLACE
            # ======================================================
            con.register("temp_final_factors", result)

            transaction_started = False

            try:
                con.execute("BEGIN")
                transaction_started = True

                con.execute("""
                    INSERT OR REPLACE INTO asset_factors_normalized_final (
                        asset_id,
                        timestamp,
                        momentum_factor_sector,
                        momentum_factor_market,
                        value_factor_sector,
                        value_factor_market,
                        quality_factor_sector,
                        quality_factor_market,
                        growth_factor_sector,
                        growth_factor_market,
                        defensive_factor_sector,
                        defensive_factor_market,
                        size_factor_sector,
                        size_factor_market
                    )
                    SELECT
                        asset_id,
                        timestamp,
                        momentum_factor_sector,
                        momentum_factor_market,
                        value_factor_sector,
                        value_factor_market,
                        quality_factor_sector,
                        quality_factor_market,
                        growth_factor_sector,
                        growth_factor_market,
                        defensive_factor_sector,
                        defensive_factor_market,
                        size_factor_sector,
                        size_factor_market
                    FROM temp_final_factors
                """)

                con.execute("COMMIT")
                transaction_started = False

                logger.info(
                    f"Final normalized scores inserted/replaced: {len(result)} rows"
                )

            except Exception as e:
                if transaction_started:
                    try:
                        con.execute("ROLLBACK")
                    except Exception as rollback_error:
                        logger.warning(f"Rollback failed: {rollback_error}")

                logger.error(f"Final normalized insert/replace failed: {e}")
                raise

        except Exception as e:
            logger.error(f"Final normalized score calculation failed: {e}")
            raise

