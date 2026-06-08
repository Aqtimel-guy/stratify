import duckdb

# =========================================================================
# DATABASE CONNECTION & INITIALIZATION
# =========================================================================
# Establishing a persistent connection to the structural data catalog file
con = duckdb.connect('C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb')  

# Installing and loading networking extensions for decoupled asset tracking
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# =========================================================================
# DATABASE SEQUENCES INITIALIZATION
# =========================================================================
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_transaction_id START 1;")
con.execute("CREATE SEQUENCE IF NOT EXISTS portfolio_history_seq START 1;")
con.execute("CREATE SEQUENCE IF NOT EXISTS portfolio_strategy_seq START 1;")
con.execute("CREATE SEQUENCE IF NOT EXISTS multi_strategy_seq START 1;")

# =========================================================================
# RELATIONAL SCHEMA CREATION (ORDERED BY STRUCTURAL DEPENDENCIES)
# =========================================================================

## Table 0 - Test Table
con.execute("""
    -- description: A test table to verify the connection and setup
    CREATE TABLE IF NOT EXISTS test_table (
        col1 INTEGER,
        col2 VARCHAR,
        PRIMARY KEY (col1)
    );
""")


## Table 1 - Assets
con.execute("""
    -- description: A table of all tradeable assets in Stratify 
    -- should be in DUCKDB, SUPABASE and as a parquet file in GCS for global access
    CREATE TABLE IF NOT EXISTS assets (
        asset_id INTEGER PRIMARY KEY,
        ticker VARCHAR,
        sector VARCHAR,
        industry VARCHAR,
        name VARCHAR,
        is_etf BOOLEAN
    );
""")

## Table 2 - Prices
con.execute("""
    -- description: Historical price data of the assets
    -- should be in DUCKDB and as a parquet file in GCS
    CREATE TABLE IF NOT EXISTS prices (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        adj_close DOUBLE,
        volume BIGINT,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 3 - Fundamentals
con.execute("""
    -- description: Fundamental metrics of the assets
    -- should be in DUCKDB and as a parquet file in GCS
    CREATE TABLE IF NOT EXISTS fundamentals (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        pe_ratio DOUBLE,
        market_cap DOUBLE,
        revenue DOUBLE,
        eps DOUBLE,
        shares_outstanding DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 4 - Features
con.execute("""
    -- description: Calculated features for assets, used for analysis
    -- should be in DUCKDB and as a parquet file in GCS
    CREATE TABLE IF NOT EXISTS features (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        volatility DOUBLE,
        momentum_relative_sp_1y DOUBLE,
        avg_volume DOUBLE,
        volume_spike DOUBLE,
        rsi_14 DOUBLE,
        atr_14 DOUBLE,
        dist_sma50 DOUBLE,
        dist_sma200 DOUBLE,
        beta_90d DOUBLE,
        sharpe_ratio_90d DOUBLE,
        max_drawdown_90d DOUBLE,
        revenue_growth_yoy DOUBLE,
        eps_growth_yoy DOUBLE,
        return_1d DOUBLE,
        return_7d DOUBLE,
        return_1m DOUBLE,
        return_3m DOUBLE,
        return_6m DOUBLE,
        return_1y DOUBLE,
        return_3y DOUBLE,
        return_max DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 5 - Users
con.execute("""
    -- description: Registered users of the platform
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        email VARCHAR UNIQUE,
        first_name VARCHAR,
        middle_name VARCHAR,
        last_name VARCHAR,
        date_of_birth DATE,
        password_hash VARCHAR
    );
""")

## Table 6 - Portfolios
con.execute("""
    -- description: Investment portfolios, users can create several
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS portfolios (
        portfolio_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        portfolio_name VARCHAR,
        created_at TIMESTAMP,
        starting_at TIMESTAMP,
        preferred_currency VARCHAR,
        available_cash DOUBLE,
        portfolio_value DOUBLE,
        current_sim_date TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
""")

## Table 7 - Assets Transactions
con.execute("""
    -- description: Asset transactional history logs mapping executions
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS assets_transactions (
        transaction_id INTEGER PRIMARY KEY DEFAULT nextval('seq_transaction_id'),
        portfolio_id INTEGER,
        asset_id INTEGER,
        timestamp TIMESTAMP,
        quantity DOUBLE,
        price_per_share DOUBLE,
        total_value DOUBLE,
        side VARCHAR,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 8 - Portfolio Performance
con.execute("""
    -- description: Tracks portfolio value over time
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS portfolio_performance (
        portfolio_id INTEGER,
        timestamp TIMESTAMP,
        value DOUBLE,
        initial_investment DOUBLE,
        PRIMARY KEY (portfolio_id, timestamp),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
    );
""")

## Table 9 - Cash Transactions
con.execute("""
    -- description: Records all cash deposits and withdrawals for portfolios
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS cash_transactions (
        transaction_id INTEGER PRIMARY KEY,
        portfolio_id INTEGER,
        timestamp TIMESTAMP,
        amount DOUBLE,
        transaction_type VARCHAR,
        reference VARCHAR,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
    );
""")

## Table 10 - Holdings
con.execute("""
    -- description: Current holdings (positions) of each portfolio
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS holdings (
        portfolio_id INTEGER,
        asset_id INTEGER,
        quantity DOUBLE,
        PRIMARY KEY (portfolio_id, asset_id),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 11 - Dividends
con.execute("""
    -- description: Recorded matrix tracking dividend distribution history
    -- should be in DUCKDB and as a parquet file in GCS
    CREATE TABLE IF NOT EXISTS dividends (
        asset_id INTEGER,
        timestamp DATE,
        dividend_amount DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 12 - Portfolio History Snapshots
con.execute("""
    -- description: Periodic system telemetry logging active portfolio asset values
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS portfolio_history (
        history_id INTEGER PRIMARY KEY DEFAULT nextval('portfolio_history_seq'),
        portfolio_id INTEGER,
        timestamp TIMESTAMP,
        portfolio_value DOUBLE,
        available_cash DOUBLE,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
    );
""")

## Table 13 - Grouped Factors Raw
con.execute("""
    -- description: Non-normalized quantitative strategy factor storage relation
    -- should be in DUCKDB only
    CREATE TABLE IF NOT EXISTS asset_factors_raw_v1 (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        momentum_factor_raw DOUBLE,
        value_factor_raw DOUBLE,
        quality_factor_raw DOUBLE,
        growth_factor_raw DOUBLE,
        defensive_factor_raw DOUBLE,
        size_factor_raw DOUBLE,
        liquidity_factor_raw DOUBLE,
        diversification_factor_raw DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 14 - Grouped Factors Percentile
con.execute("""
    -- description: Strategy factors normalized utilizing percentile-based boundaries
    -- should be in DUCKDB only
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_percentile (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        momentum_factor_sector DOUBLE,
        momentum_factor_market DOUBLE,
        value_factor_sector DOUBLE,
        value_factor_market DOUBLE,
        quality_factor_sector DOUBLE,
        quality_factor_market DOUBLE,
        growth_factor_sector DOUBLE,
        growth_factor_market DOUBLE,
        defensive_factor_sector DOUBLE,
        defensive_factor_market DOUBLE,
        size_factor_sector DOUBLE,
        size_factor_market DOUBLE,
        liquidity_factor_sector DOUBLE,
        liquidity_factor_market DOUBLE,
        diversification_factor_sector DOUBLE,
        diversification_factor_market DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 15 - Grouped Factors Z-Score
con.execute("""
    -- description: Strategy factors normalized utilizing cross-sectional Z-scores
    -- should be in DUCKDB only
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_zscore (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        momentum_factor_sector DOUBLE,
        momentum_factor_market DOUBLE,
        value_factor_sector DOUBLE,
        value_factor_market DOUBLE,
        quality_factor_sector DOUBLE,
        quality_factor_market DOUBLE,
        growth_factor_sector DOUBLE,
        growth_factor_market DOUBLE,
        defensive_factor_sector DOUBLE,
        defensive_factor_market DOUBLE,
        size_factor_sector DOUBLE,
        size_factor_market DOUBLE,
        liquidity_factor_sector DOUBLE,
        liquidity_factor_market DOUBLE,
        diversification_factor_sector DOUBLE,
        diversification_factor_market DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 16 - Grouped Factors Final Grade
con.execute("""
    -- description: Consolidated application-facing normalized factor metrics (Score 1-100)
    -- should be in DUCKDB and as a parquet file in GCS
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_final (
        asset_id INTEGER,
        timestamp TIMESTAMP,
        momentum_factor_sector DOUBLE,
        momentum_factor_market DOUBLE,
        value_factor_sector DOUBLE,
        value_factor_market DOUBLE,
        quality_factor_sector DOUBLE,
        quality_factor_market DOUBLE,
        growth_factor_sector DOUBLE,
        growth_factor_market DOUBLE,
        defensive_factor_sector DOUBLE,
        defensive_factor_market DOUBLE,
        size_factor_sector DOUBLE,
        size_factor_market DOUBLE,
        liquidity_factor_sector DOUBLE,
        liquidity_factor_market DOUBLE,
        diversification_factor_sector DOUBLE,
        diversification_factor_market DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    );
""")

## Table 17 - User Preferences Strategy
con.execute("""
    -- description: Custom quantitative strategy criteria formulated by users
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS user_preferences_strategy (
        portfolio_strategy_id INTEGER PRIMARY KEY DEFAULT nextval('portfolio_strategy_seq'),
        strategy_name VARCHAR(255),
        user_id INTEGER,
        portfolio_id INTEGER,
        timestamp TIMESTAMP,
        momentum_preference DOUBLE DEFAULT 50,
        value_preference DOUBLE DEFAULT 50,
        quality_preference DOUBLE DEFAULT 50,
        growth_preference DOUBLE DEFAULT 50,
        defensive_preference DOUBLE DEFAULT 50,
        size_preference DOUBLE DEFAULT 50,
        liquidity_preference DOUBLE DEFAULT 50,
        diversification_preference DOUBLE DEFAULT 50,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
    );
""")

## Table 18 - Multi-Strategy Allocation
con.execute("""
    -- description: Interface tracking strategic allocation split layers across vectors
    -- should be in DUCKDB and SUPABASE
    CREATE TABLE IF NOT EXISTS multi_strategy (
        multi_strategy_id INTEGER PRIMARY KEY DEFAULT nextval('multi_strategy_seq'),
        user_id INTEGER,
        portfolio_id INTEGER,
        strategy_1_id INTEGER DEFAULT NULL,
        strategy_1_pct DOUBLE DEFAULT 0,
        strategy_2_id INTEGER DEFAULT NULL,
        strategy_2_pct DOUBLE DEFAULT 0,
        strategy_3_id INTEGER DEFAULT NULL,
        strategy_3_pct DOUBLE DEFAULT 0,
        strategy_4_id INTEGER DEFAULT NULL,
        strategy_4_pct DOUBLE DEFAULT 0,
        monthly_deposit INTEGER DEFAULT 0 ,
        initial_investment INTEGER DEFAULT 0,
        buy_fee DOUBLE DEFAULT 0,
        sell_fee DOUBLE DEFAULT 0,
        deposit_fee DOUBLE DEFAULT 0,
        withdrawal_fee DOUBLE DEFAULT 0,
        preferred_sectors VARCHAR DEFAULT NULL,
        excluded_sectors VARCHAR DEFAULT NULL,
        diversification INTEGER DEFAULT 1,
        
        foreign KEY (user_id) REFERENCES users(user_id),
        foreign KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        
    );
""")

# =========================================================================
# DATA ADMINISTRATIVE MAINTENANCE PIPELINES
# =========================================================================

def db_reset():
    """
    Safely executes database sweeping routines across transaction tables.
    Adheres strictly to referential integrity constraints to protect relational structure.
    """
    # 1. Purge dependencies, snapshot tracking data rows, and position ledgers
    con.execute("DELETE FROM holdings;")
    con.execute("DELETE FROM assets_transactions;")
    con.execute("DELETE FROM cash_transactions;")
    con.execute("DELETE FROM portfolio_history;")
    con.execute("DELETE FROM portfolio_performance;")
    con.execute("DELETE FROM user_preferences_strategy;")
    con.execute("DELETE FROM multi_strategy;")

    # 2. Safely unload child entities depending directly on user vectors
    con.execute("DELETE FROM portfolios;")

    # 3. Finalize routine by clearing top-level entity vectors
    con.execute("DELETE FROM users;")
    
    print("Cleanup successful! All user-related execution contexts wiped cleanly.")

# Closing core link thread handles properly
con.close()

