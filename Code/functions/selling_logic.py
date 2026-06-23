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



def evaluate_current_holdings(con, context, strategy_id, holdings_df, sim_date, debug=False):
    """
    Evaluates how relevant current portfolio holdings are for a specific strategy.

    This function always returns one row per current holding when holdings exist.
    If an asset cannot be evaluated, it receives relevance_status = not_evaluable.
    """

    if holdings_df is None or holdings_df.empty:
        if debug:
            print("EVALUATE DEBUG | holdings_df is empty")
        return pd.DataFrame()

    if strategy_id not in context["strategies"]:
        raise ValueError(f"Strategy {strategy_id} not found in context")

    holdings_df = holdings_df.copy()

    if "asset_id" not in holdings_df.columns:
        raise ValueError("holdings_df must include asset_id")

    holdings_df["asset_id"] = holdings_df["asset_id"].astype(int)

    ranked_assets = get_closest_assets(con, strategy_id, sim_date)

    if debug:
        print("=" * 80)
        print("EVALUATE CURRENT HOLDINGS DEBUG")
        print("strategy_id:", strategy_id)
        print("sim_date:", sim_date)
        print("holdings rows:", len(holdings_df))
        print("ranked_assets is None:", ranked_assets is None)
        print("ranked_assets rows:", 0 if ranked_assets is None else len(ranked_assets))
        print("holdings columns:", holdings_df.columns.tolist())
        if ranked_assets is not None:
            print("ranked columns:", ranked_assets.columns.tolist())

    if ranked_assets is None or ranked_assets.empty:
        relevance_df = holdings_df.copy()

        relevance_df["strategy_rank"] = None
        relevance_df["distance"] = None
        relevance_df["base_score"] = None
        relevance_df["relevance_score"] = None
        relevance_df["rank_percentile"] = None
        relevance_df["relevance_status"] = "not_evaluable"

        return relevance_df

    ranked_assets = ranked_assets.copy()

    if "asset_id" not in ranked_assets.columns:
        raise ValueError("ranked_assets from get_closest_assets must include asset_id")

    if "distance" not in ranked_assets.columns:
        raise ValueError("ranked_assets from get_closest_assets must include distance")

    ranked_assets["asset_id"] = ranked_assets["asset_id"].astype(int)
    ranked_assets["distance"] = pd.to_numeric(
        ranked_assets["distance"],
        errors="coerce"
    )

    # ======================================================
    # CALCULATE SCORE FROM DISTANCE
    # ======================================================
    ranked_assets["base_score"] = 1 / (ranked_assets["distance"] + 1)
    ranked_assets["relevance_score"] = ranked_assets["base_score"]

    # ======================================================
    # APPLY PREFERRED SECTOR BONUS
    # ======================================================
    preferred_sectors = context.get("meta", {}).get("preferred_sectors", [])

    if preferred_sectors and "sector" in ranked_assets.columns:
        preferred_mask = ranked_assets["sector"].isin(preferred_sectors)
        ranked_assets.loc[preferred_mask, "relevance_score"] *= 1.05

    # ======================================================
    # DETERMINISTIC RANKING
    # ======================================================
    ranked_assets = ranked_assets.sort_values(
        by=["relevance_score", "distance", "asset_id"],
        ascending=[False, True, True],
        na_position="last",
        kind="mergesort"
    ).reset_index(drop=True)

    ranked_assets["strategy_rank"] = ranked_assets.index + 1

    total_ranked_assets = len(ranked_assets)

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

    if debug:
        print("after merge rows:", len(relevance_df))
        print("matched rows:", relevance_df["strategy_rank"].notna().sum())
        print("not matched rows:", relevance_df["strategy_rank"].isna().sum())

    # ======================================================
    # CLASSIFY BY STRATEGY RANK POSITION
    # ======================================================
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
        by=["relevance_score", "market_value", "asset_id"],
        ascending=[False, False, True],
        na_position="last",
        kind="mergesort"
    ).reset_index(drop=True)

    return relevance_df



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
    That way in worse-case it requaires 4% increase to earn money
    """

    if context is None:
        return 0

    meta = context.get("meta", {})

    buy_fee = meta.get("buy_fee", 0) 
    sell_fee = meta.get("sell_fee", 0) 

    return 50 * max(buy_fee, sell_fee)


def get_max_position_weight_from_context(context):
    """
    Calculates an approximate max allowed portfolio weight per asset.

    """

    if context is None:
        return None

    meta = context.get("meta", {})
    cash = meta.get("cash", meta.get("total_cash", 0))
    if not cash:
        cash = meta["cash"]

        
    diversification = meta.get("diversification", 2)

    max_assets = get_max_assets_from_diversification(diversification)

    multiplier_by_diversification = {
        1: 4.0,
        2: 5,
        3: 4
    }

    multiplier = multiplier_by_diversification.get(int(diversification), 2.5)
    if cash < 1000:
        return 1

    return (1 / max_assets) * multiplier


def classify_portfolio_sell_decision(
    support_count,
    watch_count,
    exit_count,
    unknown_count,
    is_overweight,
    passes_min_trade_filter
):
    """
    Converts strategy-level relevance into a portfolio-level decision.

    Logic:
    - strong_hold / hold = real support
    - watch = neutral
    - consider_out / weak_hold = exit signal
    """

    if support_count > 0:
        if is_overweight and passes_min_trade_filter:
            return "reduce_candidate"

        return "keep"

    if exit_count > 0:
        if passes_min_trade_filter:
            if unknown_count > 0:
                return "sell_candidate_low_confidence"

            if watch_count > 0:
                return "sell_candidate_low_confidence"

            return "sell_candidate"

        return "skip_small_trade"

    if watch_count > 0:
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

    support_statuses = {"strong_hold", "hold"}
    watch_statuses = {"watch"}
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

    for asset_id, asset_group in all_eval_df.groupby("asset_id", sort=True):

        statuses = asset_group["relevance_status"].dropna().tolist()

        support_count = sum(status in support_statuses for status in statuses)
        watch_count = sum(status in watch_statuses for status in statuses)
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
            watch_count=watch_count,
            exit_count=exit_count,
            unknown_count=unknown_count,
            is_overweight=is_overweight,
            passes_min_trade_filter=passes_min_trade_filter
        )

        if decision == "keep":
            print(
    "SELL DEBUG |",
    "asset_id:", asset_id,
    "statuses:", statuses,
    "support:", support_count,
    "watch:", watch_count,
    "exit:", exit_count,
    "unknown:", unknown_count,
    "market_value:", market_value,
    "passes_min_trade:", passes_min_trade_filter,
    "is_overweight:", is_overweight,
    "decision:", decision
)
            continue

        if decision == "review_only" and not include_review:
            continue

        if decision == "reduce_candidate" and not include_reduce_candidates:
            continue

        if decision == "skip_small_trade" and not include_review:
            continue

        base_row["portfolio_decision"] = decision

        base_row["support_count"] = support_count
        base_row["watch_count"] = watch_count
        base_row["exit_count"] = exit_count
        base_row["unknown_count"] = unknown_count

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

    if "asset_id" in result_df.columns:
        sort_cols.append("asset_id")

    ascending_order = []

    for col in sort_cols:
        if col == "decision_priority":
            ascending_order.append(True)
        elif col == "asset_id":
            ascending_order.append(True)
        else:
            ascending_order.append(False)

    result_df = result_df.sort_values(
        by=sort_cols,
        ascending=ascending_order,
        kind="mergesort"
    ).reset_index(drop=True)

    return result_df


def build_recommended_sell_execution_df(sell_candidates_df, sell_fee=0):
    """
    Converts portfolio-level sell candidates into executable sell orders.

    Output columns match execute_portfolio_sell_orders:
    - asset_id
    - ticker
    - price
    - shares
    """

    if sell_candidates_df is None or sell_candidates_df.empty:
        return pd.DataFrame()

    df = sell_candidates_df.copy()

    if "current_price" in df.columns:
        price_col = "current_price"
    elif "price" in df.columns:
        price_col = "price"
    else:
        raise ValueError("sell_candidates_df must include current_price or price.")

    required_cols = ["asset_id", "ticker", "shares", price_col, "portfolio_decision"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        raise ValueError(f"Missing required columns for sell execution: {missing_cols}")

    execution_rows = []

    for _, row in df.iterrows():
        asset_id = int(row["asset_id"])
        ticker = row["ticker"]
        owned_shares = int(row["shares"])
        price = float(row[price_col])
        decision = row["portfolio_decision"]

        if owned_shares <= 0 or price <= 0:
            continue

        sell_shares = 0

        if decision in {"sell_candidate", "sell_candidate_low_confidence"}:
            sell_shares = owned_shares

        elif decision == "reduce_candidate":
            portfolio_weight = row.get("portfolio_weight", None)
            max_position_weight = row.get("max_position_weight", None)
            market_value = row.get("market_value", owned_shares * price)

            if (
                portfolio_weight is None or
                max_position_weight is None or
                portfolio_weight <= 0 or
                max_position_weight <= 0
            ):
                continue

            total_portfolio_value = market_value / portfolio_weight
            target_value = total_portfolio_value * max_position_weight
            excess_value = market_value - target_value

            if excess_value <= 0:
                continue

            sell_shares = int(excess_value // price)

            if sell_shares >= owned_shares:
                sell_shares = owned_shares - 1

        if sell_shares <= 0:
            continue

        estimated_value = sell_shares * price

        if estimated_value <= sell_fee:
            continue

        execution_rows.append({
            "asset_id": asset_id,
            "ticker": ticker,
            "price": price,
            "shares": sell_shares,
            "current_holding_shares": owned_shares,
            "portfolio_decision": decision,
            "estimated_value": estimated_value,
            "estimated_fee": float(sell_fee),
            "estimated_cash_added": float(estimated_value - sell_fee)
        })

    if not execution_rows:
        return pd.DataFrame()

    execution_df = pd.DataFrame(execution_rows)

    execution_df = execution_df.sort_values(
        "estimated_value",
        ascending=False
    ).reset_index(drop=True)

    return execution_df