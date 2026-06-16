import duckdb
import pandas as pd
from .portfolio_managment import calculate_fifo_avg_price


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