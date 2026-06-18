import duckdb
import pandas as pd
from .portfolio_managment import calculate_fifo_avg_price
from . trading_logic import re_score_assets , get_closest_assets

def get_current_holdings_with_prices(con, portfolio_id, sim_date):
    """
    Loads current portfolio holdings with latest available prices and FIFO average buy price.

    Returns a DataFrame with:
    - asset_id
    - ticker
    - name
    - sector
    - industry
    - shares
    - avg_buy_price
    - current_price
    - market_value
    - pnl_pct
    - portfolio_weight
    """

    # ======================================================
    # LOAD TRANSACTIONS FOR FIFO AVG PRICE
    # ======================================================
    tx_query = """
        SELECT 
            asset_id,
            quantity,
            price_per_share,
            side,
            timestamp
        FROM assets_transactions
        WHERE portfolio_id = ?
          AND timestamp <= ?
        ORDER BY timestamp, transaction_id
    """

    all_tx = con.execute(tx_query, [portfolio_id, sim_date]).df()

    # ======================================================
    # LOAD CURRENT HOLDINGS WITH ASSET METADATA
    # ======================================================
    holdings_query = """
        SELECT 
            a.asset_id,
            a.ticker,
            a.name,
            a.sector,
            a.industry,
            h.quantity AS shares
        FROM holdings h
        JOIN assets a
            ON h.asset_id = a.asset_id
        WHERE h.portfolio_id = ?
          AND h.quantity > 0
    """

    holdings_df = con.execute(holdings_query, [portfolio_id]).df()

    if holdings_df.empty:
        return holdings_df

    rows = []

    for _, row in holdings_df.iterrows():
        asset_id = row["asset_id"]
        shares = int(row["shares"])

        # ======================================================
        # FIFO AVG BUY PRICE
        # ======================================================
        asset_tx = all_tx[all_tx["asset_id"] == asset_id]
        avg_buy_price = calculate_fifo_avg_price(asset_tx)

        # ======================================================
        # LATEST PRICE BEFORE SIM DATE
        # ======================================================
        price_row = con.execute("""
            SELECT close
            FROM prices
            WHERE asset_id = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, [asset_id, sim_date]).fetchone()

        if not price_row:
            current_price = None
            market_value = 0
            pnl_pct = 0
        else:
            current_price = float(price_row[0])
            market_value = shares * current_price
            pnl_pct = ((current_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0

        rows.append({
            "asset_id": int(asset_id),
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": row["sector"],
            "industry": row["industry"],
            "shares": shares,
            "avg_buy_price": float(avg_buy_price),
            "current_price": current_price,
            "market_value": float(market_value),
            "pnl_pct": float(pnl_pct)
        })

    result_df = pd.DataFrame(rows)

    total_market_value = result_df["market_value"].sum()

    if total_market_value > 0:
        result_df["portfolio_weight"] = result_df["market_value"] / total_market_value
    else:
        result_df["portfolio_weight"] = 0.0

    result_df = result_df.sort_values(
        "market_value",
        ascending=False
    ).reset_index(drop=True)

    return result_df



def evaluate_current_holdings(con, context, strategy_id, holdings_df, sim_date):
    """
    Evaluates how relevant current portfolio holdings are for a specific strategy.

    Relevance is based on:
    - distance from the strategy vector
    - score = 1 / (distance + 1)
    - preferred sector bonus from context

    This function does not decide whether to sell.
    It only measures current strategic relevance.
    """

    if holdings_df is None or holdings_df.empty:
        return pd.DataFrame()

    if strategy_id not in context["strategies"]:
        raise ValueError(f"Strategy {strategy_id} not found in context")

    ranked_assets = get_closest_assets(con, strategy_id, sim_date)

    if ranked_assets.empty:
        return pd.DataFrame()

    # ======================================================
    # CALCULATE SCORE FROM DISTANCE
    # ======================================================
    ranked_assets["base_score"] = 1 / (ranked_assets["distance"] + 1)
    ranked_assets["relevance_score"] = ranked_assets["base_score"]

    # ======================================================
    # APPLY PREFERRED SECTOR BONUS
    # ======================================================
    preferred_sectors = context["meta"].get("preferred_sectors", [])

    if preferred_sectors:
        preferred_mask = ranked_assets["sector"].isin(preferred_sectors)
        ranked_assets.loc[preferred_mask, "relevance_score"] *= 1.05

    # ======================================================
    # RANK BY SCORE, NOT DISTANCE
    # ======================================================
    ranked_assets = ranked_assets.sort_values(
        "relevance_score",
        ascending=False
    ).reset_index(drop=True)

    ranked_assets["strategy_rank"] = ranked_assets.index + 1

    score_cols = [
        "asset_id",
        "strategy_rank",
        "distance",
        "base_score",
        "relevance_score"
    ]

    relevance_df = holdings_df.merge(
        ranked_assets[score_cols],
        on="asset_id",
        how="left"
    )


    # ======================================================
    # CLASSIFY BY STRATEGY RANK POSITION, NOT RAW SCORE
    # ======================================================
    total_ranked_assets = len(ranked_assets)

    def classify_rank(rank):
        if pd.isna(rank):
            return "not_evaluable"

        rank_pct = rank / total_ranked_assets

        if rank_pct <= 0.10:
            return "strong_hold"

        if rank_pct <= 0.25:
            return "hold"

        if rank_pct <= 0.40:
            return "watch"

        if rank_pct <= 0.60:
            return "consider_out"

        return "weak_hold"

    relevance_df["rank_percentile"] = relevance_df["strategy_rank"].apply(
        lambda rank: rank / total_ranked_assets if not pd.isna(rank) else None
    )

    relevance_df["relevance_status"] = relevance_df["strategy_rank"].apply(classify_rank)


    relevance_df = relevance_df.sort_values(
        by=["relevance_score", "market_value"],
        ascending=[False, False],
        na_position="last"
    ).reset_index(drop=True)

    return relevance_df



# def find_portfolio_sell_candidates(strategy_evaluations):
#     """
#     Finds holdings that are weak across all active strategies.

#     Args:
#         strategy_evaluations (dict):
#             Dictionary in the format:
#             {
#                 strategy_id: relevance_df
#             }

#             Each relevance_df is the output of evaluate_current_holdings()
#             and must include:
#             - asset_id
#             - ticker
#             - relevance_status
#             - strategy_rank
#             - market_value

#     Returns:
#         pd.DataFrame:
#             Assets that are consider_out or weak_hold in every strategy
#             where they were evaluated.
#     """

#     weak_statuses = {"consider_out", "weak_hold"}

#     rows = []

#     for strategy_id, eval_df in strategy_evaluations.items():

#         if eval_df is None or eval_df.empty:
#             continue

#         required_cols = {"asset_id", "relevance_status"}

#         if not required_cols.issubset(eval_df.columns):
#             raise ValueError(
#                 f"Missing required columns in evaluation df for strategy {strategy_id}"
#             )

#         temp = eval_df.copy()
#         temp["strategy_id"] = strategy_id

#         rows.append(temp)

#     if not rows:
#         return pd.DataFrame()

#     all_eval_df = pd.concat(rows, ignore_index=True)

#     result_rows = []

#     for asset_id, asset_group in all_eval_df.groupby("asset_id"):

#         statuses = set(asset_group["relevance_status"].dropna())

#         # If at least one strategy thinks the asset is better than weak/consider_out,
#         # we keep it.
#         has_good_strategy = any(
#             status not in weak_statuses
#             for status in statuses
#         )

#         if has_good_strategy:
#             continue

#         # If all strategies classify it as consider_out / weak_hold,
#         # it becomes a portfolio-level sell candidate.
#         if statuses and statuses.issubset(weak_statuses):

#             base_row = asset_group.iloc[0].copy()

#             base_row["evaluated_strategies"] = list(asset_group["strategy_id"])
#             base_row["strategy_statuses"] = dict(
#                 zip(
#                     asset_group["strategy_id"],
#                     asset_group["relevance_status"]
#                 )
#             )

#             if "strategy_rank" in asset_group.columns:
#                 base_row["best_strategy_rank"] = asset_group["strategy_rank"].min()

#             if "rank_percentile" in asset_group.columns:
#                 base_row["best_rank_percentile"] = asset_group["rank_percentile"].min()

#             result_rows.append(base_row)

#     if not result_rows:
#         return pd.DataFrame()

#     result_df = pd.DataFrame(result_rows)

#     sort_cols = []

#     if "market_value" in result_df.columns:
#         sort_cols.append("market_value")

#     if "best_rank_percentile" in result_df.columns:
#         sort_cols.append("best_rank_percentile")

#     if sort_cols:
#         result_df = result_df.sort_values(
#             by=sort_cols,
#             ascending=[False if col == "market_value" else True for col in sort_cols]
#         ).reset_index(drop=True)

#     return result_df

############## TODO: check later thos AI written functions

def get_max_assets_from_diversification(diversification):
    """
    Converts diversification level into target max asset count.
    """

    mapping = {
        1: 10,
        2: 25,
        3: 40
    }

    return mapping.get(int(diversification), 25)


def classify_relevance_by_rank(strategy_rank, max_assets):
    """
    Classifies asset relevance based on rank relative to strategy size.
    """

    if pd.isna(strategy_rank):
        return "not_evaluable"

    rank = int(strategy_rank)

    if rank <= max_assets:
        return "strong_hold"

    if rank <= max_assets * 2:
        return "hold"

    if rank <= max_assets * 4:
        return "watch"

    if rank <= max_assets * 8:
        return "consider_out"

    return "weak_hold"


def get_min_trade_value_from_context(context):
    """
    Calculates a minimal trade value to avoid unnecessary churn.
    """

    if context is None:
        return 0

    meta = context.get("meta", {})

    buy_fee = meta.get("buy_fee", 0) or 0
    sell_fee = meta.get("sell_fee", 0) or 0

    return 50 * max(buy_fee, sell_fee)


def get_max_position_weight_from_context(context):
    """
    Calculates an approximate max allowed portfolio weight per asset.
    """

    if context is None:
        return None

    meta = context.get("meta", {})
    diversification = meta.get("diversification", 2)

    max_assets = get_max_assets_from_diversification(diversification)

    multiplier_by_diversification = {
        1: 2.0,
        2: 2.5,
        3: 3.0
    }

    multiplier = multiplier_by_diversification.get(int(diversification), 2.5)

    return (1 / max_assets) * multiplier


def classify_portfolio_sell_decision(
    support_count,
    exit_count,
    unknown_count,
    is_overweight,
    passes_min_trade_filter
):
    """
    Converts strategy-level relevance into a portfolio-level decision.
    """

    if support_count > 0:
        if is_overweight and passes_min_trade_filter:
            return "reduce_candidate"

        return "keep"

    if exit_count > 0 and unknown_count == 0:
        if passes_min_trade_filter:
            return "sell_candidate"

        return "skip_small_trade"

    if exit_count > 0 and unknown_count > 0:
        if passes_min_trade_filter:
            return "sell_candidate_low_confidence"

        return "review_only"

    if unknown_count > 0:
        return "review_only"

    return "keep"


def find_portfolio_sell_candidates(
    strategy_evaluations,
    context=None,
    include_review=False,
    include_reduce_candidates=True
):
    """
    Finds portfolio-level sell or reduce candidates based on all active strategies.

    This function does not execute trades.
    It only creates a decision layer above strategy-level relevance.
    """

    support_statuses = {"strong_hold", "hold", "watch"}
    exit_statuses = {"consider_out", "weak_hold"}
    unknown_statuses = {"not_evaluable"}

    rows = []

    for strategy_id, eval_df in strategy_evaluations.items():

        if eval_df is None or eval_df.empty:
            continue

        required_cols = {"asset_id", "relevance_status"}

        if not required_cols.issubset(eval_df.columns):
            raise ValueError(
                f"Missing required columns in evaluation df for strategy {strategy_id}"
            )

        temp = eval_df.copy()
        temp["strategy_id"] = strategy_id

        rows.append(temp)

    if not rows:
        return pd.DataFrame()

    all_eval_df = pd.concat(rows, ignore_index=True)

    min_trade_value = get_min_trade_value_from_context(context)
    max_position_weight = get_max_position_weight_from_context(context)

    result_rows = []

    for asset_id, asset_group in all_eval_df.groupby("asset_id"):

        statuses = asset_group["relevance_status"].dropna().tolist()

        support_count = sum(status in support_statuses for status in statuses)
        exit_count = sum(status in exit_statuses for status in statuses)
        unknown_count = sum(status in unknown_statuses for status in statuses)

        evaluated_strategy_count = len(asset_group)

        base_row = asset_group.iloc[0].copy()

        market_value = base_row.get("market_value", 0) or 0
        portfolio_weight = base_row.get("portfolio_weight", 0) or 0

        passes_min_trade_filter = market_value >= min_trade_value

        if max_position_weight is not None:
            is_overweight = portfolio_weight > max_position_weight
        else:
            is_overweight = False

        decision = classify_portfolio_sell_decision(
            support_count=support_count,
            exit_count=exit_count,
            unknown_count=unknown_count,
            is_overweight=is_overweight,
            passes_min_trade_filter=passes_min_trade_filter
        )

        if decision == "keep":
            continue

        if decision == "review_only" and not include_review:
            continue

        if decision == "reduce_candidate" and not include_reduce_candidates:
            continue

        if decision == "skip_small_trade" and not include_review:
            continue

        base_row["portfolio_decision"] = decision

        base_row["support_count"] = support_count
        base_row["exit_count"] = exit_count
        base_row["unknown_count"] = unknown_count
        base_row["evaluated_strategy_count"] = evaluated_strategy_count

        base_row["strategy_statuses"] = dict(
            zip(
                asset_group["strategy_id"],
                asset_group["relevance_status"]
            )
        )

        base_row["evaluated_strategies"] = list(asset_group["strategy_id"])

        if "strategy_rank" in asset_group.columns:
            ranks = pd.to_numeric(asset_group["strategy_rank"], errors="coerce").dropna()
            base_row["best_strategy_rank"] = ranks.min() if not ranks.empty else None
            base_row["worst_strategy_rank"] = ranks.max() if not ranks.empty else None

        if "rank_percentile" in asset_group.columns:
            percentiles = pd.to_numeric(asset_group["rank_percentile"], errors="coerce").dropna()
            base_row["best_rank_percentile"] = percentiles.min() if not percentiles.empty else None
            base_row["worst_rank_percentile"] = percentiles.max() if not percentiles.empty else None

        if "rank_vs_target" in asset_group.columns:
            rank_vs_target = pd.to_numeric(asset_group["rank_vs_target"], errors="coerce").dropna()
            base_row["best_rank_vs_target"] = rank_vs_target.min() if not rank_vs_target.empty else None
            base_row["worst_rank_vs_target"] = rank_vs_target.max() if not rank_vs_target.empty else None

        base_row["min_trade_value"] = min_trade_value
        base_row["passes_min_trade_filter"] = passes_min_trade_filter
        base_row["max_position_weight"] = max_position_weight
        base_row["is_overweight"] = is_overweight

        result_rows.append(base_row)

    if not result_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(result_rows)

    decision_priority = {
        "sell_candidate": 1,
        "sell_candidate_low_confidence": 2,
        "reduce_candidate": 3,
        "review_only": 4,
        "skip_small_trade": 5
    }

    result_df["decision_priority"] = result_df["portfolio_decision"].map(
        decision_priority
    ).fillna(99)

    sort_cols = ["decision_priority"]

    if "market_value" in result_df.columns:
        sort_cols.append("market_value")

    result_df = result_df.sort_values(
        by=sort_cols,
        ascending=[True] + [False for _ in sort_cols[1:]]
    ).reset_index(drop=True)

    return result_df


