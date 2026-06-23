import duckdb
import logging
import pandas as pd
import numpy as np
from functools import reduce
import sys
import streamlit as st

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'






def momentum_factor_raw_calculator(
    con,
    asset_id,
    w_return_1y=0.30,
    w_momentum_relative_sp_1y=0.30,
    w_return_6m=0.20,
    w_dist_sma200=0.10,
    w_return_3m=0.10,
    min_available_components=3,
    start_date=None
):
    """
    Calculates a raw composite momentum factor for a single asset.

    The function uses available raw features from the features table and computes
    a weighted momentum score per date.

    Missing values are not filled with zero.
    If some components are missing, the available weights are re-normalized.
    If fewer than min_available_components are available, the result is NULL.
    """

    logger = logging.getLogger(__name__)

    weights = {
        "return_1y": w_return_1y,
        "momentum_relative_sp_1y": w_momentum_relative_sp_1y,
        "return_6m": w_return_6m,
        "dist_sma200": w_dist_sma200,
        "return_3m": w_return_3m,
    }

    weights_sum = sum(weights.values())
    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights should sum to 1. Current sum: {weights_sum}")
        return None

    params = [asset_id]

    date_filter = ""
    if start_date is not None:
        date_filter = "AND timestamp >= ?"
        params.append(start_date)

    df = con.execute(f"""
        SELECT
            asset_id,
            timestamp,
            return_1y,
            momentum_relative_sp_1y,
            return_6m,
            dist_sma200,
            return_3m
        FROM features
        WHERE asset_id = ?
        {date_filter}
        ORDER BY timestamp ASC
    """, params).df()

    if df.empty:
        return None

    component_cols = list(weights.keys())

    weighted_sum = 0
    available_weight_sum = 0
    available_components = 0

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["momentum_factor_raw"] = weighted_sum / available_weight_sum

    df.loc[
        (available_weight_sum == 0) | (available_components < min_available_components),
        "momentum_factor_raw"
    ] = None

    return df[["asset_id", "timestamp", "momentum_factor_raw"]]


def value_factor_raw_calculator(
    con,
    asset_id,
    w_earnings_yield=0.60,
    w_sales_yield=0.30,
    w_dividend_yield=0.10,
    fundamental_lag_days=60,
    min_available_components=2,
    start_date=None,
    max_fundamental_age_days=550,
    earnings_yield_positive_cap=0.30,
    earnings_yield_negative_cap=0.50,
    sales_yield_cap=5.00,
    dividend_yield_cap=0.12
):
    """
    Calculates a robust raw composite value factor for a single asset.

    Formula is conceptually unchanged:
    - earnings yield
    - sales yield
    - dividend yield

    Source of truth:
    - features.pe_ratio for earnings yield
    - fundamentals for revenue / market cap / shares
    - prices only for close when needed
    - dividends table for dividend yield

    Missing values are not filled with fake values.
    Negative earnings yield is kept and treated as a penalty.
    Zero dividend yield is a valid value, not missing.
    Components are converted to comparable scores before weighting.
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    weights = {
        "earnings_score": w_earnings_yield,
        "sales_score": w_sales_yield,
        "dividend_score": w_dividend_yield,
    }

    weights_sum = sum(weights.values())
    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights must sum to 1. Current sum: {weights_sum}")
        return None

    # ======================================================
    # 1. LOAD DAILY TIMELINE FROM FEATURES
    # ======================================================
    params = [asset_id]

    date_filter = ""
    if start_date is not None:
        date_filter = "AND f.timestamp >= ?"
        params.append(start_date)

    df = con.execute(f"""
        SELECT
            f.asset_id,
            f.timestamp,
            f.pe_ratio,
            p.close
        FROM features f
        JOIN prices p
            ON f.asset_id = p.asset_id
           AND f.timestamp = p.timestamp
        WHERE f.asset_id = ?
          AND p.close IS NOT NULL
          AND p.close > 0
          {date_filter}
        ORDER BY f.timestamp ASC
    """, params).df()

    if df.empty:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "value_factor_raw"
        ])

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values("timestamp").drop_duplicates(
        subset=["asset_id", "timestamp"],
        keep="last"
    ).reset_index(drop=True)

    df["pe_ratio"] = pd.to_numeric(df["pe_ratio"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df.loc[~np.isfinite(df["pe_ratio"]), "pe_ratio"] = np.nan
    df.loc[~np.isfinite(df["close"]), "close"] = np.nan

    # ======================================================
    # 2. EARNINGS YIELD FROM FEATURES PE RATIO
    # ======================================================
    # If PE is positive, earnings yield is positive.
    # If PE is negative, earnings yield is negative.
    # If PE is missing or zero, earnings yield is missing.
    df["earnings_yield"] = np.where(
        df["pe_ratio"].notna() &
        (df["pe_ratio"].abs() > EPSILON),
        1.0 / df["pe_ratio"],
        np.nan
    )

    # ======================================================
    # 3. LOAD FUNDAMENTALS FOR SALES YIELD
    # ======================================================
    fundamentals_df = con.execute("""
        SELECT
            asset_id,
            timestamp,
            revenue,
            market_cap,
            shares_outstanding
        FROM fundamentals
        WHERE asset_id = ?
        ORDER BY timestamp ASC
    """, [asset_id]).df()

    if fundamentals_df.empty:
        df["revenue_ttm"] = np.nan
        df["market_cap_from_fundamentals"] = np.nan
        df["shares_outstanding"] = np.nan

    else:
        fundamentals_df["timestamp"] = pd.to_datetime(
            fundamentals_df["timestamp"]
        )

        for col in ["revenue", "market_cap", "shares_outstanding"]:
            fundamentals_df[col] = pd.to_numeric(
                fundamentals_df[col],
                errors="coerce"
            )

        fundamentals_df = fundamentals_df.sort_values("timestamp").drop_duplicates(
            subset=["asset_id", "timestamp"],
            keep="last"
        ).reset_index(drop=True)

        fundamentals_df["available_timestamp"] = (
            fundamentals_df["timestamp"] + pd.Timedelta(days=fundamental_lag_days)
        )

        fundamentals_df["revenue_ttm"] = (
            fundamentals_df["revenue"]
            .rolling(window=4, min_periods=4)
            .sum()
        )

        fundamentals_aligned = fundamentals_df[[
            "available_timestamp",
            "revenue_ttm",
            "market_cap",
            "shares_outstanding"
        ]].copy()

        df = pd.merge_asof(
            df.sort_values("timestamp"),
            fundamentals_aligned.sort_values("available_timestamp"),
            left_on="timestamp",
            right_on="available_timestamp",
            direction="backward"
        )

        df["fundamental_age_days"] = (
            df["timestamp"] - df["available_timestamp"]
        ).dt.days

        stale_fundamentals_mask = (
            df["available_timestamp"].isna() |
            (df["fundamental_age_days"] > max_fundamental_age_days)
        )

        df.loc[
            stale_fundamentals_mask,
            ["revenue_ttm", "market_cap", "shares_outstanding"]
        ] = np.nan

        df = df.rename(columns={
            "market_cap": "market_cap_from_fundamentals"
        })

        df = df.drop(
            columns=["available_timestamp", "fundamental_age_days"],
            errors="ignore"
        )

    # If market_cap is missing in fundamentals, estimate it from shares * close.
    df["market_cap_estimated"] = np.where(
        df["shares_outstanding"].notna() &
        (df["shares_outstanding"] > 0) &
        df["close"].notna() &
        (df["close"] > 0),
        df["shares_outstanding"] * df["close"],
        np.nan
    )

    df["market_cap_used"] = df["market_cap_from_fundamentals"].combine_first(
        df["market_cap_estimated"]
    )

    df["sales_yield"] = np.where(
        df["revenue_ttm"].notna() &
        (df["revenue_ttm"] > 0) &
        df["market_cap_used"].notna() &
        (df["market_cap_used"] > EPSILON),
        df["revenue_ttm"] / df["market_cap_used"],
        np.nan
    )

    # ======================================================
    # 4. LOAD DIVIDENDS AND CALCULATE TTM DIVIDENDS
    # ======================================================
    dividends_df = con.execute("""
        SELECT
            timestamp,
            dividend_amount
        FROM dividends
        WHERE asset_id = ?
          AND dividend_amount IS NOT NULL
          AND dividend_amount > 0
        ORDER BY timestamp ASC
    """, [asset_id]).df()

    if dividends_df.empty:
        df["dividend_ttm"] = 0.0
    else:
        dividends_df["timestamp"] = pd.to_datetime(dividends_df["timestamp"])

        dividends_daily = (
            dividends_df
            .groupby("timestamp", as_index=True)["dividend_amount"]
            .sum()
            .sort_index()
        )

        price_dates = pd.Index(df["timestamp"].sort_values().unique())
        combined_index = price_dates.union(dividends_daily.index).sort_values()

        dividend_series = (
            dividends_daily
            .reindex(combined_index)
            .fillna(0.0)
        )

        dividend_ttm_series = (
            dividend_series
            .rolling("365D")
            .sum()
        )

        df = df.sort_values("timestamp")
        df["dividend_ttm"] = df["timestamp"].map(
            dividend_ttm_series
        ).fillna(0.0)

    df["dividend_yield"] = np.where(
        df["dividend_ttm"].notna() &
        (df["dividend_ttm"] >= 0) &
        df["close"].notna() &
        (df["close"] > EPSILON),
        df["dividend_ttm"] / df["close"],
        np.nan
    )

    # ======================================================
    # 5. CLEAN RAW COMPONENTS
    # ======================================================
    for col in ["earnings_yield", "sales_yield", "dividend_yield"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[~np.isfinite(df[col]), col] = np.nan

    # ======================================================
    # 6. ROBUST COMPONENT SCORING
    # ======================================================

    earnings_yield_clipped = df["earnings_yield"].clip(
        lower=-earnings_yield_negative_cap,
        upper=earnings_yield_positive_cap
    )

    df["earnings_score"] = np.where(
        earnings_yield_clipped.notna() &
        (earnings_yield_clipped >= 0),
        earnings_yield_clipped / earnings_yield_positive_cap,
        np.where(
            earnings_yield_clipped.notna() &
            (earnings_yield_clipped < 0),
            earnings_yield_clipped / earnings_yield_negative_cap,
            np.nan
        )
    )

    sales_yield_clipped = df["sales_yield"].clip(
        lower=0,
        upper=sales_yield_cap
    )

    df["sales_score"] = np.where(
        sales_yield_clipped.notna(),
        np.log1p(sales_yield_clipped) / np.log1p(sales_yield_cap),
        np.nan
    )

    dividend_yield_clipped = df["dividend_yield"].clip(
        lower=0,
        upper=dividend_yield_cap
    )

    df["dividend_score"] = np.where(
        dividend_yield_clipped.notna(),
        dividend_yield_clipped / dividend_yield_cap,
        np.nan
    )

    for col in ["earnings_score", "sales_score", "dividend_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[~np.isfinite(df[col]), col] = np.nan

    # ======================================================
    # 7. WEIGHTED FACTOR WITH AVAILABLE COMPONENTS ONLY
    # ======================================================
    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight_sum = pd.Series(0.0, index=df.index)
    available_components = pd.Series(0, index=df.index)

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0.0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["value_factor_raw"] = np.divide(
        weighted_sum,
        available_weight_sum,
        out=np.full(len(df), np.nan),
        where=available_weight_sum > 0
    )

    df.loc[
        (available_weight_sum == 0) |
        (available_components < min_available_components),
        "value_factor_raw"
    ] = np.nan

    df = df.replace([np.inf, -np.inf], np.nan)

    return df[[
        "asset_id",
        "timestamp",
        "value_factor_raw"
    ]]


def quality_factor_raw_calculator(
    con,
    asset_id,
    w_profitability=0.70,
    w_earnings_stability=0.30,
    fundamental_lag_days=60,
    min_available_components=1,
    start_date=None
):
    """
    Calculates a raw composite quality factor for a single asset.

    Formula is unchanged.

    Components:
    - profitability_margin: EPS TTM divided by revenue per share TTM
    - earnings_stability: stability of EPS over recent fundamental observations

    Source of daily timeline:
    - features table

    Fundamentals are lagged by fundamental_lag_days to avoid lookahead bias.
    Missing values are not filled with zero.
    Available component weights are re-normalized per row.
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6

    weights = {
        "profitability_margin": w_profitability,
        "earnings_stability": w_earnings_stability,
    }

    weights_sum = sum(weights.values())

    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights must sum to 1. Current sum: {weights_sum}")
        return None

    # ======================================================
    # 1. LOAD DAILY TIMELINE FROM FEATURES
    # ======================================================
    params = [asset_id]

    date_filter = ""
    if start_date is not None:
        date_filter = "AND timestamp >= ?"
        params.append(start_date)

    timeline_df = con.execute(f"""
        SELECT
            asset_id,
            timestamp
        FROM features
        WHERE asset_id = ?
          {date_filter}
        ORDER BY timestamp ASC
    """, params).df()

    if timeline_df.empty:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "quality_factor_raw"
        ])

    timeline_df["timestamp"] = pd.to_datetime(timeline_df["timestamp"])

    timeline_df = timeline_df.sort_values("timestamp").drop_duplicates(
        subset=["asset_id", "timestamp"],
        keep="last"
    ).reset_index(drop=True)

    # ======================================================
    # 2. LOAD FUNDAMENTALS
    # ======================================================
    fundamentals_df = con.execute("""
        SELECT
            asset_id,
            timestamp,
            eps,
            revenue,
            shares_outstanding
        FROM fundamentals
        WHERE asset_id = ?
        ORDER BY timestamp ASC
    """, [asset_id]).df()

    if fundamentals_df.empty:
        return pd.DataFrame({
            "asset_id": timeline_df["asset_id"],
            "timestamp": timeline_df["timestamp"],
            "quality_factor_raw": np.nan
        })

    fundamentals_df["timestamp"] = pd.to_datetime(fundamentals_df["timestamp"])

    for col in ["eps", "revenue", "shares_outstanding"]:
        fundamentals_df[col] = pd.to_numeric(
            fundamentals_df[col],
            errors="coerce"
        )

    fundamentals_df = fundamentals_df.sort_values("timestamp").drop_duplicates(
        subset=["asset_id", "timestamp"],
        keep="last"
    ).reset_index(drop=True)

    fundamentals_df["available_timestamp"] = (
        fundamentals_df["timestamp"] + pd.Timedelta(days=fundamental_lag_days)
    )

    # ======================================================
    # 3. CALCULATE ORIGINAL QUALITY COMPONENTS
    # ======================================================

    # Explicit rolling counts make the calculation easier to debug.
    fundamentals_df["eps_count_4q"] = (
        fundamentals_df["eps"]
        .rolling(window=4, min_periods=1)
        .count()
    )

    fundamentals_df["revenue_count_4q"] = (
        fundamentals_df["revenue"]
        .rolling(window=4, min_periods=1)
        .count()
    )

    fundamentals_df["shares_count_4q"] = (
        fundamentals_df["shares_outstanding"]
        .rolling(window=4, min_periods=1)
        .count()
    )

    fundamentals_df["eps_ttm"] = (
        fundamentals_df["eps"]
        .rolling(window=4, min_periods=4)
        .sum()
    )

    fundamentals_df["revenue_ttm"] = (
        fundamentals_df["revenue"]
        .rolling(window=4, min_periods=4)
        .sum()
    )

    fundamentals_df["avg_shares_outstanding_4q"] = (
        fundamentals_df["shares_outstanding"]
        .rolling(window=4, min_periods=4)
        .mean()
    )

    fundamentals_df["revenue_per_share_ttm"] = np.divide(
        fundamentals_df["revenue_ttm"],
        fundamentals_df["avg_shares_outstanding_4q"],
        out=np.full(len(fundamentals_df), np.nan),
        where=(
            fundamentals_df["revenue_ttm"].notna()
            & fundamentals_df["avg_shares_outstanding_4q"].notna()
            & (fundamentals_df["avg_shares_outstanding_4q"] > EPSILON)
        )
    )

    fundamentals_df["profitability_margin"] = np.divide(
        fundamentals_df["eps_ttm"],
        fundamentals_df["revenue_per_share_ttm"],
        out=np.full(len(fundamentals_df), np.nan),
        where=(
            fundamentals_df["eps_ttm"].notna()
            & fundamentals_df["revenue_per_share_ttm"].notna()
            & (fundamentals_df["revenue_per_share_ttm"] > EPSILON)
            & (fundamentals_df["eps_count_4q"] >= 4)
            & (fundamentals_df["revenue_count_4q"] >= 4)
            & (fundamentals_df["shares_count_4q"] >= 4)
        )
    )

    # Earnings stability component.
    # std == 0 means perfectly stable EPS, not missing data.
    eps_std_8q = (
        fundamentals_df["eps"]
        .rolling(window=8, min_periods=4)
        .std()
    )

    eps_mean_abs_8q = (
        fundamentals_df["eps"]
        .rolling(window=8, min_periods=4)
        .mean()
        .abs()
    )

    eps_count_8q = (
        fundamentals_df["eps"]
        .rolling(window=8, min_periods=1)
        .count()
    )

    eps_relative_volatility = np.divide(
        eps_std_8q,
        eps_mean_abs_8q + EPSILON,
        out=np.full(len(fundamentals_df), np.nan),
        where=(
            eps_std_8q.notna()
            & eps_mean_abs_8q.notna()
            & (eps_count_8q >= 4)
        )
    )

    fundamentals_df["earnings_stability"] = np.divide(
        1.0,
        1.0 + eps_relative_volatility,
        out=np.full(len(fundamentals_df), np.nan),
        where=eps_relative_volatility.notna()
    )

    component_cols = [
        "profitability_margin",
        "earnings_stability",
    ]

    for col in component_cols:
        fundamentals_df[col] = pd.to_numeric(
            fundamentals_df[col],
            errors="coerce"
        )

        fundamentals_df.loc[
            ~np.isfinite(fundamentals_df[col]),
            col
        ] = np.nan

    fundamentals_df = fundamentals_df.sort_values("available_timestamp")

    # ======================================================
    # 4. ALIGN FUNDAMENTAL COMPONENTS TO DAILY FEATURE DATES
    # ======================================================
    aligned_components = fundamentals_df[[
        "available_timestamp",
        "profitability_margin",
        "earnings_stability"
    ]].copy()

    df = pd.merge_asof(
        timeline_df.sort_values("timestamp"),
        aligned_components.sort_values("available_timestamp"),
        left_on="timestamp",
        right_on="available_timestamp",
        direction="backward"
    )

    df = df.drop(columns=["available_timestamp"], errors="ignore")

    # ======================================================
    # 5. WEIGHTED FACTOR WITH AVAILABLE COMPONENTS ONLY
    # ======================================================
    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight_sum = pd.Series(0.0, index=df.index)
    available_components = pd.Series(0, index=df.index)

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0.0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["quality_factor_raw"] = np.divide(
        weighted_sum,
        available_weight_sum,
        out=np.full(len(df), np.nan),
        where=available_weight_sum > 0
    )

    df.loc[
        (available_weight_sum == 0) |
        (available_components < min_available_components),
        "quality_factor_raw"
    ] = np.nan

    df["asset_id"] = asset_id

    return df[[
        "asset_id",
        "timestamp",
        "quality_factor_raw"
    ]]


def growth_factor_raw_calculator(
    con,
    asset_id,
    w_eps=0.5,
    w_revenue=0.5,
    min_available_components=1,
    start_date=None
):
    """
    Calculates a raw composite growth factor for a single asset.

    Formula is unchanged:
    - EPS YoY growth
    - Revenue YoY growth

    Source of truth:
    - features.eps_growth_yoy
    - features.revenue_growth_yoy

    Missing values are not filled with zero.
    Available component weights are re-normalized per row.
    """

    logger = logging.getLogger(__name__)

    weights = {
        "eps_growth_yoy": w_eps,
        "revenue_growth_yoy": w_revenue,
    }

    weights_sum = sum(weights.values())
    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights must sum to 1. Current sum: {weights_sum}")
        return None

    params = [asset_id]

    date_filter = ""
    if start_date is not None:
        date_filter = "AND timestamp >= ?"
        params.append(start_date)

    df = con.execute(f"""
        SELECT
            asset_id,
            timestamp,
            eps_growth_yoy,
            revenue_growth_yoy
        FROM features
        WHERE asset_id = ?
          {date_filter}
        ORDER BY timestamp ASC
    """, params).df()

    if df.empty:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "growth_factor_raw"
        ])

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    for col in ["eps_growth_yoy", "revenue_growth_yoy"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[~np.isfinite(df[col]), col] = np.nan

    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight_sum = pd.Series(0.0, index=df.index)
    available_components = pd.Series(0, index=df.index)

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0.0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["growth_factor_raw"] = np.divide(
        weighted_sum,
        available_weight_sum,
        out=np.full(len(df), np.nan),
        where=available_weight_sum > 0
    )

    df.loc[
        (available_weight_sum == 0) |
        (available_components < min_available_components),
        "growth_factor_raw"
    ] = np.nan

    return df[[
        "asset_id",
        "timestamp",
        "growth_factor_raw"
    ]]


def defensive_factor_raw_calculator(
    con,
    asset_id,
    benchmark_id=504, # 504 is SPY
    w_vol=0.30,
    w_beta=0.25,
    w_dd=0.25,
    w_sharpe=0.20 , 
    start_date=None

):
    """
    Calculates a raw defensive factor for a single asset.

    Defensive logic:
    - Lower volatility is better
    - Lower absolute beta is better
    - Smaller max drawdown is better
    - Higher Sharpe ratio is better

    The function uses adjusted prices because this is a return/risk based factor.
    Missing values are not filled with zero.
    """

    logger = logging.getLogger(__name__)

    # ======================================================
    # 1. VALIDATE WEIGHTS
    # ======================================================
    weights_sum = w_vol + w_beta + w_dd + w_sharpe

    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights must sum to 1. Current sum: {weights_sum}")
        return None
    
    price_start_date = None

    if start_date is not None:
        price_start_date = pd.to_datetime(start_date) - pd.Timedelta(days=200)

    # ======================================================
    # 2. LOAD ASSET PRICES & BENCHMARK PRICES
    # ======================================================
   
    if price_start_date is not None:
        df_asset = con.execute("""
            SELECT
                asset_id,
                timestamp,
                adj_close
            FROM prices
            WHERE asset_id = ?
            AND adj_close IS NOT NULL
            AND adj_close > 0
            AND timestamp >= ?
            ORDER BY timestamp ASC
        """, [asset_id, price_start_date]).df()

        df_bench = con.execute("""
            SELECT
                timestamp,
                adj_close AS bench_price
            FROM prices
            WHERE asset_id = ?
            AND adj_close IS NOT NULL
            AND adj_close > 0
            AND timestamp >= ?
            ORDER BY timestamp ASC
        """, [benchmark_id, price_start_date]).df()
    
    
    else:
        df_asset = con.execute("""
            SELECT
                asset_id,
                timestamp,
                adj_close
            FROM prices
            WHERE asset_id = ?
            AND adj_close IS NOT NULL
            AND adj_close > 0
            ORDER BY timestamp ASC
        """, [asset_id]).df()

        df_bench = con.execute("""
            SELECT
                timestamp,
                adj_close AS bench_price
            FROM prices
            WHERE asset_id = ?
            AND adj_close IS NOT NULL
            AND adj_close > 0
            ORDER BY timestamp ASC
        """, [benchmark_id]).df()

    if df_asset.empty or df_bench.empty or len(df_asset) < 100:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "defensive_factor_raw"
        ])

    df_asset["timestamp"] = pd.to_datetime(df_asset["timestamp"])
    df_bench["timestamp"] = pd.to_datetime(df_bench["timestamp"])

    df_asset = df_asset.sort_values("timestamp")
    df_bench = df_bench.sort_values("timestamp")

    # ======================================================
    # 4. ALIGN ASSET AND BENCHMARK PRICES
    # ======================================================
    df = pd.merge_asof(
        df_asset,
        df_bench,
        on="timestamp",
        direction="backward"
    )

    # ======================================================
    # 5. CALCULATE RETURNS
    # ======================================================
    df["returns"] = df["adj_close"].pct_change()
    df["bench_returns"] = df["bench_price"].pct_change()

    # ======================================================
    # 6. RISK METRICS
    # ======================================================
    df["volatility"] = (
        df["returns"]
        .rolling(window=90, min_periods=20)
        .std() * np.sqrt(252)
    )

    cov = df["returns"].rolling(window=90, min_periods=20).cov(df["bench_returns"])
    var = df["bench_returns"].rolling(window=90, min_periods=20).var()

    df["beta_90d"] = cov / var.replace(0, np.nan)

    mean_ret_90d_annualized = (
        df["returns"]
        .rolling(window=90, min_periods=20)
        .mean() * 252
    )

    df["sharpe_90d"] = (
        mean_ret_90d_annualized /
        df["volatility"].replace(0, np.nan)
    )

    roll_max = df["adj_close"].rolling(window=90, min_periods=20).max()
    drawdown = df["adj_close"] / roll_max - 1

    df["max_drawdown_90d"] = (
        drawdown
        .rolling(window=90, min_periods=20)
        .min()
        .clip(upper=0)
    )

    # ======================================================
    # 7. CONVERT METRICS TO STABLE DEFENSIVE SCORES
    # ======================================================
    df["vol_score"] = np.where(
        (df["volatility"].notna()) & (df["volatility"] >= 0),
        1 / (1 + df["volatility"]),
        np.nan
    )

    df["beta_score"] = np.where(
        df["beta_90d"].notna(),
        1 / (1 + df["beta_90d"].abs()),
        np.nan
    )

    df["drawdown_score"] = np.where(
        df["max_drawdown_90d"].notna(),
        1 / (1 + df["max_drawdown_90d"].abs()),
        np.nan
    )

    # Sigmoid keeps Sharpe score in a stable 0-1 range.
    df["sharpe_score"] = np.where(
        df["sharpe_90d"].notna(),
        1 / (1 + np.exp(-df["sharpe_90d"].clip(-10, 10))),
        np.nan
    )

    for col in ["vol_score", "beta_score", "drawdown_score", "sharpe_score"]:
        df.loc[~np.isfinite(df[col]), col] = np.nan

    # ======================================================
    # 8. FINAL FACTOR WITH AVAILABLE COMPONENTS ONLY
    # ======================================================
    weights = {
        "vol_score": w_vol,
        "beta_score": w_beta,
        "drawdown_score": w_dd,
        "sharpe_score": w_sharpe,
    }

    weighted_sum = 0
    available_weight_sum = 0
    available_components = 0

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["defensive_factor_raw"] = weighted_sum / available_weight_sum

    df.loc[
        (available_weight_sum == 0) | (available_components == 0),
        "defensive_factor_raw"
    ] = None

    df["asset_id"] = asset_id

    if start_date is not None:
        df = df[df["timestamp"] >= pd.to_datetime(start_date)]

    return df[[
        "asset_id",
        "timestamp",
        "defensive_factor_raw"
    ]]




def size_factor_raw_calculator(
    con,
    asset_id,
    w_market_cap=0.70,
    w_liquidity=0.30,
    fundamental_lag_days=60 ,
    start_date=None

):
    """
    Calculates a raw size factor for a single asset.

    Interpretation:
    - Higher score means larger and more liquid.
    - Market cap is calculated point-in-time using lagged shares_outstanding and raw close.
    - Liquidity is calculated using smoothed dollar volume.

    Missing values are not filled with zero.
    Cross-sectional normalization happens later.
    """

    logger = logging.getLogger(__name__)
    EPSILON = 1e-6
    
    price_start_date = None

    if start_date is not None:
        price_start_date = pd.to_datetime(start_date) - pd.Timedelta(days=60)

    # ======================================================
    # 1. VALIDATE WEIGHTS
    # ======================================================
    weights_sum = w_market_cap + w_liquidity

    if abs(weights_sum - 1.0) > 1e-6:
        logger.error(f"Weights must sum to 1. Current sum: {weights_sum}")
        return None

    # ======================================================
    # 2. LOAD PRICES
    # ======================================================
    if price_start_date is not None:
        prices_df = con.execute("""
            SELECT
                asset_id,
                timestamp,
                close,
                COALESCE(adj_close, close) AS adjusted_price,
                volume
            FROM prices
            WHERE asset_id = ?
              AND close IS NOT NULL
              AND close > 0
              AND timestamp >= ?
            ORDER BY timestamp ASC
        """, [asset_id, price_start_date]).df()
    else:
        prices_df = con.execute("""
            SELECT
                asset_id,
                timestamp,
                close,
                COALESCE(adj_close, close) AS adjusted_price,
                volume
            FROM prices
            WHERE asset_id = ?
              AND close IS NOT NULL
              AND close > 0
            ORDER BY timestamp ASC
        """, [asset_id]).df()
    
    if prices_df.empty:
        return pd.DataFrame(columns=[
            "asset_id",
            "timestamp",
            "size_factor_raw"
        ])

    prices_df["timestamp"] = pd.to_datetime(prices_df["timestamp"])
    prices_df = prices_df.sort_values("timestamp")
    prices_df = prices_df.drop_duplicates(
        subset=["asset_id", "timestamp"],
        keep="last"
    )

    # ======================================================
    # 3. LOAD LAGGED SHARES OUTSTANDING
    # ======================================================
    fundamentals_df = con.execute("""
        SELECT
            asset_id,
            timestamp,
            shares_outstanding
        FROM fundamentals
        WHERE asset_id = ?
          AND shares_outstanding IS NOT NULL
          AND shares_outstanding > 0
        ORDER BY timestamp ASC
    """, [asset_id]).df()

    if fundamentals_df.empty:
        # No fundamentals means no market-cap component,
        # but liquidity can still be calculated from prices.
        df = prices_df.copy()
        df["shares_outstanding"] = np.nan

    else:
        fundamentals_df["timestamp"] = pd.to_datetime(fundamentals_df["timestamp"])

        fundamentals_df["available_timestamp"] = (
            fundamentals_df["timestamp"] + pd.Timedelta(days=fundamental_lag_days)
        )

        fundamentals_df = fundamentals_df.sort_values("available_timestamp")

        # ======================================================
        # 4. ALIGN SHARES OUTSTANDING TO PRICE DATES
        # ======================================================
        df = pd.merge_asof(
            prices_df.sort_values("timestamp"),
            fundamentals_df[[
                "available_timestamp",
                "shares_outstanding"
            ]].sort_values("available_timestamp"),
            left_on="timestamp",
            right_on="available_timestamp",
            direction="backward"
        )

        df = df.drop(columns=["available_timestamp"], errors="ignore")

    # ======================================================
    # 5. CALCULATE POINT-IN-TIME MARKET CAP AND LIQUIDITY
    # ======================================================
    df["market_cap"] = np.where(
        (df["shares_outstanding"].notna()) &
        (df["shares_outstanding"] > 0) &
        (df["close"] > 0),
        df["close"] * df["shares_outstanding"],
        np.nan
    )

    # For liquidity, adjusted close is acceptable because this is a traded-value proxy.
    df["dollar_volume"] = np.where(
        (df["adjusted_price"].notna()) &
        (df["adjusted_price"] > 0) &
        (df["volume"].notna()) &
        (df["volume"] > 0),
        df["adjusted_price"] * df["volume"],
        np.nan
    )

    df["avg_dollar_volume_20d"] = (
        df["dollar_volume"]
        .rolling(window=20, min_periods=5)
        .mean()
    )

    # ======================================================
    # 6. LOG TRANSFORMS
    # ======================================================
    df["market_cap_score_raw"] = np.where(
        (df["market_cap"].notna()) & (df["market_cap"] > EPSILON),
        np.log(df["market_cap"]),
        np.nan
    )

    df["liquidity_score_raw"] = np.where(
        (df["avg_dollar_volume_20d"].notna()) &
        (df["avg_dollar_volume_20d"] > EPSILON),
        np.log(df["avg_dollar_volume_20d"]),
        np.nan
    )

    for col in ["market_cap_score_raw", "liquidity_score_raw"]:
        df.loc[~np.isfinite(df[col]), col] = np.nan

    # ======================================================
    # 7. FINAL FACTOR WITH AVAILABLE COMPONENTS ONLY
    # ======================================================
    weights = {
        "market_cap_score_raw": w_market_cap,
        "liquidity_score_raw": w_liquidity,
    }

    weighted_sum = 0
    available_weight_sum = 0
    available_components = 0

    for col, weight in weights.items():
        is_available = df[col].notna()

        weighted_sum = weighted_sum + df[col].where(is_available, 0) * weight
        available_weight_sum = available_weight_sum + is_available.astype(float) * weight
        available_components = available_components + is_available.astype(int)

    df["size_factor_raw"] = weighted_sum / available_weight_sum

    df.loc[
        (available_weight_sum == 0) | (available_components == 0),
        "size_factor_raw"
    ] = None

    df["asset_id"] = asset_id

    if start_date is not None:
        df = df[df["timestamp"] >= pd.to_datetime(start_date)]

    return df[[
        "asset_id",
        "timestamp",
        "size_factor_raw"
    ]]
    
    

###################################


def update_asset_factors_raw_v1():
    """
    Updates raw factor values for all assets in the database.

    Active raw factors:
    - momentum_factor_raw
    - value_factor_raw
    - quality_factor_raw
    - growth_factor_raw
    - defensive_factor_raw
    - size_factor_raw

    Deprecated / currently unused factors are intentionally excluded:
    - liquidity_factor_raw
    - diversification_factor_raw

    This function recalculates a rolling buffer window and uses INSERT OR REPLACE
    so recent factor values can be corrected when rolling/as-of inputs change.
    """

    logger = logging.getLogger(__name__)

    LOOKBACK_BUFFER_DAYS = 300

    con = None

    active_factor_cols = [
        "momentum_factor_raw",
        "value_factor_raw",
        "quality_factor_raw",
        "growth_factor_raw",
        "defensive_factor_raw",
        "size_factor_raw",
    ]

    target_cols = [
        "asset_id",
        "timestamp",
        *active_factor_cols,
    ]

    calculators = {
        "momentum_factor_raw": momentum_factor_raw_calculator,
        "value_factor_raw": value_factor_raw_calculator,
        "quality_factor_raw": quality_factor_raw_calculator,
        "growth_factor_raw": growth_factor_raw_calculator,
        "defensive_factor_raw": defensive_factor_raw_calculator,
        "size_factor_raw": size_factor_raw_calculator,
    }

    try:
        # ======================================================
        # 0. OPEN CONNECTION
        # ======================================================
        con = duckdb.connect(DB_PATH)

        logger.info("Starting asset_factors_raw_v1 update process")

        asset_status_df = con.execute("""
            SELECT
                a.asset_id,
                MAX(f.timestamp) AS last_factor_timestamp
            FROM assets a
            LEFT JOIN asset_factors_raw_v1 f
                ON a.asset_id = f.asset_id
            GROUP BY a.asset_id
            ORDER BY a.asset_id
        """).df()

        total_assets = len(asset_status_df)

        if total_assets == 0:
            logger.warning("No assets found in assets table.")
            return

        logger.info(f"Starting raw factor update for {total_assets} assets")

        all_results = []
        processed_assets = 0
        skipped_assets = 0
        failed_assets = 0

        # ======================================================
        # 1. PROCESS ASSETS
        # ======================================================
        for i, row in asset_status_df.iterrows():
            asset_id = int(row["asset_id"])
            last_ts = row["last_factor_timestamp"]
            progress = ((i + 1) / total_assets) * 100

            sys.stdout.write(
                f"\rRaw Factors Calculation: {i}/{total_assets} ({progress:.1f}%)"
            )
            sys.stdout.flush()

            try:
                # ======================================================
                # 1.1 GET LAST STORED FACTOR TIMESTAMP
                # ======================================================


                if last_ts is not None:
                    start_date = pd.to_datetime(last_ts) - pd.Timedelta(days=LOOKBACK_BUFFER_DAYS)
                else:
                    start_date = None

                # ======================================================
                # 1.2 LOAD PRICE TIMELINE
                # ======================================================
                if start_date is not None:
                    prices_df = con.execute("""
                        SELECT
                            asset_id,
                            timestamp
                        FROM prices
                        WHERE asset_id = ?
                          AND timestamp >= ?
                        ORDER BY timestamp ASC
                    """, [asset_id, start_date]).df()
                else:
                    prices_df = con.execute("""
                        SELECT
                            asset_id,
                            timestamp
                        FROM prices
                        WHERE asset_id = ?
                        ORDER BY timestamp ASC
                    """, [asset_id]).df()

                if prices_df.empty:
                    skipped_assets += 1
                    continue

                prices_df["timestamp"] = pd.to_datetime(prices_df["timestamp"])

                prices_df = prices_df.drop_duplicates(
                    subset=["asset_id", "timestamp"]
                )

                prices_df = prices_df.sort_values("timestamp")

                final_df = prices_df.copy()

                # ======================================================
                # 1.3 CALCULATE AND MERGE ACTIVE FACTORS
                # ======================================================
                for col_name, calc_func in calculators.items():
                    try:
                        f_df = calc_func(
                                    con=con,
                                    asset_id=asset_id,
                                    start_date=start_date
                                )

                        if f_df is None or f_df.empty:
                            continue

                        if col_name not in f_df.columns:
                            logger.warning(
                                f"{col_name} missing from calculator output for asset {asset_id}"
                            )
                            continue

                        f_df = f_df[["timestamp", col_name]].copy()
                        f_df["timestamp"] = pd.to_datetime(f_df["timestamp"])

                        f_df = f_df.drop_duplicates(
                            subset=["timestamp"],
                            keep="last"
                        )

                        f_df = f_df.sort_values("timestamp")

                        if start_date is not None:
                            f_df = f_df[f_df["timestamp"] >= start_date]

                        if f_df.empty:
                            continue

                        before_cols = set(final_df.columns)

                        final_df = final_df.merge(
                            f_df,
                            on="timestamp",
                            how="left"
                        )

                        after_cols = set(final_df.columns)

                        if col_name not in final_df.columns:
                            logger.warning(
                                f"{col_name} was calculated for asset {asset_id} but did not appear after merge. "
                                f"New columns: {sorted(after_cols - before_cols)}"
                            )
                            continue

                        non_null_after_merge = final_df[col_name].notna().sum()

                        non_null_before_merge = f_df[col_name].notna().sum()
                        non_null_after_merge = final_df[col_name].notna().sum()

                        if non_null_before_merge == 0:
                            # Calculator returned rows, but the factor itself is fully missing.
                            # This is usually a data availability issue, not a merge/save issue.
                            if col_name in ["size_factor_raw"]:
                                logger.warning(
                                    f"{col_name} calculator returned only NULL values for asset {asset_id}. "
                                    f"f_df rows={len(f_df)}, "
                                    f"f_df min_ts={f_df['timestamp'].min()}, "
                                    f"f_df max_ts={f_df['timestamp'].max()}"
                                )

                        elif non_null_after_merge == 0:
                            # This is the real dangerous case:
                            # calculator had valid values, but merge lost them.
                            logger.warning(
                                f"{col_name} had valid values before merge but all values became NULL after merge. "
                                f"asset_id={asset_id}, "
                                f"f_df rows={len(f_df)}, "
                                f"f_df non_null={non_null_before_merge}, "
                                f"f_df min_ts={f_df['timestamp'].min()}, "
                                f"f_df max_ts={f_df['timestamp'].max()}, "
                                f"prices min_ts={final_df['timestamp'].min()}, "
                                f"prices max_ts={final_df['timestamp'].max()}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"{col_name} failed for asset {asset_id}: {e}"
                        )
                        continue

                # ======================================================
                # 1.4 ENSURE FINAL SCHEMA BEFORE CLEANING
                # ======================================================

                for col in target_cols:
                    if col not in final_df.columns:
                        final_df[col] = np.nan

                final_df.replace([np.inf, -np.inf], np.nan, inplace=True)

                # ======================================================
                # 1.5 CLEAN OUTPUT
                # ======================================================

                final_df = final_df.dropna(
                    subset=active_factor_cols,
                    how="all"
                )

                if final_df.empty:
                    skipped_assets += 1
                    continue

                # ======================================================
                # 1.6 KEEP BUFFER WINDOW FOR REPLACE
                # ======================================================

                if start_date is not None:
                    final_df = final_df[final_df["timestamp"] >= start_date]

                if final_df.empty:
                    skipped_assets += 1
                    continue

                # ======================================================
                # 1.7 KEEP ONLY TARGET COLUMNS
                # ======================================================

                final_df = final_df[target_cols]

                all_results.append(final_df)
                processed_assets += 1

            except Exception as e:
                failed_assets += 1
                logger.error(f"Error processing asset {asset_id}: {e}")
                continue

        sys.stdout.write("\n")
        sys.stdout.flush()

        logger.info("Factor calculation completed for all assets.")
        logger.info(
            f"Processed assets: {processed_assets}, "
            f"Skipped assets: {skipped_assets}, "
            f"Failed assets: {failed_assets}"
        )

        # ======================================================
        # 2. BATCH INSERT
        # ======================================================
        if not all_results:
            logger.warning("No factor rows to insert/update")
            return

        final_insert_df = pd.concat(all_results, ignore_index=True)

        if final_insert_df.empty:
            logger.warning("Final insert dataframe is empty")
            return

        final_insert_df = final_insert_df.drop_duplicates(
            subset=["asset_id", "timestamp"],
            keep="last"
        )

        final_insert_df["timestamp"] = pd.to_datetime(final_insert_df["timestamp"])

        logger.info(f"Prepared {len(final_insert_df)} rows for insert/replace")
        
        final_insert_df = final_insert_df.replace([np.inf, -np.inf], np.nan)
        final_insert_df = final_insert_df.where(pd.notna(final_insert_df), None)

        con.register("temp_factors_raw_v1", final_insert_df)

        # ======================================================
        # 3. SAFE INSERT / REPLACE
        # ======================================================
        transaction_started = False

        try:
            con.execute("BEGIN")
            transaction_started = True

            con.execute("""
                INSERT INTO asset_factors_raw_v1 (
                    asset_id,
                    timestamp,
                    momentum_factor_raw,
                    value_factor_raw,
                    quality_factor_raw,
                    growth_factor_raw,
                    defensive_factor_raw,
                    size_factor_raw
                )
                SELECT
                    asset_id,
                    timestamp,
                    momentum_factor_raw,
                    value_factor_raw,
                    quality_factor_raw,
                    growth_factor_raw,
                    defensive_factor_raw,
                    size_factor_raw
                FROM temp_factors_raw_v1
                ON CONFLICT (asset_id, timestamp) DO UPDATE SET
                    momentum_factor_raw = COALESCE(EXCLUDED.momentum_factor_raw, asset_factors_raw_v1.momentum_factor_raw),
                    value_factor_raw = COALESCE(EXCLUDED.value_factor_raw, asset_factors_raw_v1.value_factor_raw),
                    quality_factor_raw = COALESCE(EXCLUDED.quality_factor_raw, asset_factors_raw_v1.quality_factor_raw),
                    growth_factor_raw = COALESCE(EXCLUDED.growth_factor_raw, asset_factors_raw_v1.growth_factor_raw),
                    defensive_factor_raw = COALESCE(EXCLUDED.defensive_factor_raw, asset_factors_raw_v1.defensive_factor_raw),
                    size_factor_raw = COALESCE(EXCLUDED.size_factor_raw, asset_factors_raw_v1.size_factor_raw)
            """)

            con.execute("COMMIT")
            transaction_started = False

            logger.info(
                f"Inserted/Replaced {len(final_insert_df)} rows into asset_factors_raw_v1"
            )

        except Exception as e:
            if transaction_started:
                try:
                    con.execute("ROLLBACK")
                except Exception as rollback_error:
                    logger.warning(f"Rollback failed: {rollback_error}")

            logger.error(f"Insert/replace failed: {e}")
            raise

    except Exception as e:
        logger.error(f"Critical pipeline failure: {e}")
        raise

    finally:
        if con is not None:
            try:
                con.close()
                logger.info("DuckDB connection closed")
            except Exception as e:
                logger.warning(f"Failed to close DuckDB connection: {e}")



################################

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


# update_asset_factors_raw_v1()


# test_tickers = ["AAPL", "MSFT", "TSLA", "PLTR", "F", "UBER" , "META"]
# start_date = "2020-01-01"

# factor_calculators = {
#     "momentum_factor_raw": momentum_factor_raw_calculator,
#     "value_factor_raw": value_factor_raw_calculator,
#     "quality_factor_raw": quality_factor_raw_calculator,
#     "growth_factor_raw": growth_factor_raw_calculator,
#     "defensive_factor_raw": defensive_factor_raw_calculator,
#     "size_factor_raw": size_factor_raw_calculator,

# }

# results = []

# with duckdb.connect(DB_PATH) as con:
#     for ticker in test_tickers:
#         row = con.execute("""
#             SELECT asset_id
#             FROM assets
#             WHERE ticker = ?
#             LIMIT 1
#         """, [ticker]).fetchone()

#         if row is None:
#             print(ticker, "not found")
#             continue

#         asset_id = int(row[0])

#         print("=" * 100)
#         print(f"Testing ticker: {ticker} | asset_id: {asset_id}")
#         print("=" * 100)

#         for factor_col, calculator_func in factor_calculators.items():
#             try:
#                 df = calculator_func(
#                     con=con,
#                     asset_id=asset_id,
#                     start_date=start_date
#                 )

#                 if df is None or df.empty:
#                     result = {
#                         "ticker": ticker,
#                         "asset_id": asset_id,
#                         "factor": factor_col,
#                         "rows": 0,
#                         "null_pct": 100.0,
#                         "non_null": 0,
#                         "first_non_null_date": None,
#                         "last_non_null_date": None,
#                         "status": "EMPTY_DF"
#                     }

#                     results.append(result)

#                     print(
#                         f"{factor_col:<30} | "
#                         f"rows: {0:<6} | "
#                         f"null pct: {100.0:<6} | "
#                         f"non-null: {0:<6} | "
#                         f"status: EMPTY_DF"
#                     )

#                     continue

#                 if factor_col not in df.columns:
#                     result = {
#                         "ticker": ticker,
#                         "asset_id": asset_id,
#                         "factor": factor_col,
#                         "rows": len(df),
#                         "null_pct": None,
#                         "non_null": None,
#                         "first_non_null_date": None,
#                         "last_non_null_date": None,
#                         "status": "MISSING_FACTOR_COLUMN"
#                     }

#                     results.append(result)

#                     print(
#                         f"{factor_col:<30} | "
#                         f"rows: {len(df):<6} | "
#                         f"status: MISSING_FACTOR_COLUMN"
#                     )

#                     continue

#                 df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

#                 non_null_mask = df[factor_col].notna()
#                 rows_count = len(df)
#                 non_null_count = int(non_null_mask.sum())
#                 null_pct = round(df[factor_col].isna().mean() * 100, 2)

#                 if non_null_count > 0:
#                     first_non_null_date = df.loc[
#                         non_null_mask,
#                         "timestamp"
#                     ].min()

#                     last_non_null_date = df.loc[
#                         non_null_mask,
#                         "timestamp"
#                     ].max()
#                 else:
#                     first_non_null_date = None
#                     last_non_null_date = None

#                 result = {
#                     "ticker": ticker,
#                     "asset_id": asset_id,
#                     "factor": factor_col,
#                     "rows": rows_count,
#                     "null_pct": null_pct,
#                     "non_null": non_null_count,
#                     "first_non_null_date": first_non_null_date,
#                     "last_non_null_date": last_non_null_date,
#                     "status": "OK"
#                 }

#                 results.append(result)

#                 print(
#                     f"{factor_col:<30} | "
#                     f"rows: {rows_count:<6} | "
#                     f"null pct: {null_pct:<6} | "
#                     f"non-null: {non_null_count:<6} | "
#                     f"first: {first_non_null_date} | "
#                     f"last: {last_non_null_date}"
#                 )

#             except Exception as e:
#                 result = {
#                     "ticker": ticker,
#                     "asset_id": asset_id,
#                     "factor": factor_col,
#                     "rows": None,
#                     "null_pct": None,
#                     "non_null": None,
#                     "first_non_null_date": None,
#                     "last_non_null_date": None,
#                     "status": f"ERROR: {str(e)}"
#                 }

#                 results.append(result)

#                 print(
#                     f"{factor_col:<30} | "
#                     f"status: ERROR | {str(e)}"
#                 )

# results_df = pd.DataFrame(results)
# problematic_df = results_df[
#     (results_df["status"] != "OK") |
#     (results_df["null_pct"].fillna(100) > 50)
# ].copy()

# print("\n")
# print("=" * 100)
# print("PROBLEMS TABLE")
# print("=" * 100)

# print(problematic_df)

# print("\n")
# print("=" * 100)
# print("SUMMARY TABLE")
# print("=" * 100)

# print(results_df)