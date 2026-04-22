import duckdb


### currently not implmented yet.


# creating / opening connection
con = duckdb.connect('C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb')  

# creating tables if not exist

## Table 1 - Assets
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_asset_id START 1;")

con.execute("""
            -- description: A table of all tradeable assets in Stratify
            
            CREATE TABLE IF NOT EXISTS 
            assets (
                asset_id INTEGER PRIMARY KEY DEFAULT nextval('seq_asset_id'),
                ticker VARCHAR,
                name VARCHAR,
                sector VARCHAR,
                industry VARCHAR,
                type VARCHAR , -- stock, etf, crypto, etc.
                currency VARCHAR , 
                is_active BOOLEAN
                
            )""")
    
## Table 2 - Prices
con.execute("""
            -- description: Historical price data of the assets
            
            CREATE TABLE IF NOT EXISTS 
            prices (
                asset_id INTEGER,
                timestamp TIMESTAMP,
                open double,
                high double,
                low double,
                close double,
                adj_close double,
                volume bigint,
                PRIMARY KEY (asset_id, timestamp),
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            )""")
    

## Table 3 - Fundamentals
con.execute("""
            -- description: Fundamental metrics of the assets
            
            CREATE TABLE IF NOT EXISTS fundamentals (
                asset_id INTEGER,
                report_date DATE,      
                -- Core
                revenue DOUBLE,
                net_income DOUBLE,
                eps DOUBLE,
                -- Balance Sheet Highlights
                total_assets DOUBLE,
                total_liabilities DOUBLE,
                total_equity DOUBLE,
                cash_and_equiv DOUBLE,
                -- Cash Flow
                free_cash_flow DOUBLE,
                operating_cash_flow DOUBLE,
                -- Capital Structure
                shares_outstanding DOUBLE,
                
                PRIMARY KEY (asset_id, timestamp),
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            
                
            )""")

## Table 4 - Features
con.execute("""
            -- description: Calculated features for assets, used for analysis
            
            CREATE TABLE IF NOT EXISTS features (
                asset_id INTEGER,
                timestamp TIMESTAMP,
                
                -- Valuation (Point-in-Time)
                pe_ratio DOUBLE,
                ps_ratio DOUBLE,
                pb_ratio DOUBLE,
                market_cap DOUBLE,
                enterprise_value DOUBLE,
                
                -- Technicals & Liquidity
                volatility_20d DOUBLE,
                rsi_14 DOUBLE,
                atr_14 DOUBLE,
                dist_sma50 DOUBLE,
                dist_sma200 DOUBLE,
                avg_volume_20d DOUBLE,
                volume_spike DOUBLE,
                
                -- Momentum (Relative & Absolute)
                momentum_1m DOUBLE,
                momentum_3m DOUBLE,
                momentum_1y DOUBLE,
                momentum_relative_sp_1y DOUBLE,
                
                -- Quality & Fundamental Derived
                revenue_growth_yoy DOUBLE,
                eps_growth_yoy DOUBLE,
                roe DOUBLE,
                net_margin DOUBLE,
                debt_to_equity DOUBLE,
                free_cash_flow_yield DOUBLE, -- FCF / Market Cap
                
                -- Risk Metrics
                beta_90d DOUBLE,
                sharpe_ratio_90d DOUBLE,
                max_drawdown_90d DOUBLE,
                
                -- Returns
                return_1d DOUBLE,
                return_1m DOUBLE,
                return_3m DOUBLE,
                return_6m DOUBLE,
                return_1y DOUBLE,
                
                PRIMARY KEY (asset_id, timestamp),
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)

            )""")



## Table 5 - Users
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_user_id START 1;")

con.execute("""
            -- description: Registered users of the platform
            
            CREATE TABLE IF NOT EXISTS 
            users (
                user_id INTEGER PRIMARY KEY DEFAULT nextval('seq_user_id'),
                email VARCHAR UNIQUE,
                first_name VARCHAR,
                middle_name VARCHAR,
                last_name VARCHAR,
                date_of_birth DATE,
                password_hash VARCHAR,
                created_at TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN,
                portfolio_count INTEGER DEFAULT 0 ,
            )""")


## Table 6 - Portfolios
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_portfolio_id START 1;")


con.execute("""
            -- description: Investment portfolios, users can create several
            
            CREATE TABLE IF NOT EXISTS 
            portfolios (
                portfolio_id INTEGER PRIMARY KEY DEFAULT nextval('seq_portfolio_id'),
                user_id INTEGER,
                portfolio_name VARCHAR,
                created_at TIMESTAMP, -- when the user opened the portfolio
                starting_at TIMESTAMP, -- historical start date for simulation
                preferred_currency VARCHAR,
                available_cash DOUBLE,
                current_sim_date TIMESTAMP ,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                
            )""")


## Table 7 - Assets Transactions
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_transaction_id START 1;")

con.execute("""
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
            )
        """)

## Table 8 - Portfolio Performance  (not sure if needed yet)
con.execute("""
            -- description: Tracks portfolio value over time
            
            CREATE TABLE IF NOT EXISTS 
            portfolio_performance (
                portfolio_id INTEGER,
                timestamp TIMESTAMP,
                value DOUBLE,
                initial_investment DOUBLE,
                PRIMARY KEY (portfolio_id, timestamp),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
            )""")

## Table 9 - Cash Transactions
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cash_transaction_id START 1;")


con.execute("""
            -- description: Records all cash deposits and withdrawals for portfolios
            
            CREATE TABLE IF NOT EXISTS 
            cash_transactions (
                cash_transaction_id INTEGER PRIMARY KEY DEFAULT nextval('seq_cash_transaction_id'),
                portfolio_id INTEGER,
                timestamp TIMESTAMP,
                amount DOUBLE,
                transaction_type VARCHAR, -- deposit/withdraw
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
            )""")

## Table 10 - Holdings
con.execute("""
            -- description: Current holdings (positions) of each portfolio
            
            CREATE TABLE IF NOT EXISTS 
            holdings (
                portfolio_id INTEGER,
                asset_id INTEGER,
                quantity DOUBLE,
                average_cost DOUBLE ,
                PRIMARY KEY (portfolio_id, asset_id),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            )""")

## Table 11 - dividends

con.execute("""
        -- every divident sharing that is recorded (very raw)
    CREATE TABLE IF NOT EXISTS dividends (
        asset_id INTEGER,
        timestamp DATE,
        dividend_amount DOUBLE,
        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    )
""")

## Table 12 - portfolio history snapshots
con.execute("CREATE SEQUENCE IF NOT EXISTS portfolio_history_seq;")

con.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_history (
        history_id INTEGER PRIMARY KEY DEFAULT nextval('portfolio_history_seq'),
        portfolio_id INTEGER,
        timestamp TIMESTAMP,
        portfolio_value DOUBLE,
        available_cash DOUBLE,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
    );
""")

# Table 13 - Grouped factors (for strategy)
con.execute("""
            -- not normelized factors. need to normelize by sectors 
            -- the information will be derived from data up to the timestamp
            -- higher = better
    CREATE TABLE IF NOT EXISTS asset_factors_raw_v1 (
        
        asset_id INTEGER,
        timestamp TIMESTAMP,
        
        momentum_factor_raw DOUBLE,      -- short&long - term price behavior
        value_factor_raw DOUBLE,         -- valuation
        quality_factor_raw DOUBLE,       -- profitability & leverage
        growth_factor_raw DOUBLE,        -- fundamental growth
        defensive_factor_raw DOUBLE,     -- downside protection (vol + drawdown)
        size_factor_raw DOUBLE,          -- optional but useful (smaller = better )
        liquidity_factor_raw DOUBLE,     -- execution quality
        diversification_factor_raw DOUBLE, -- oposing correlation level
        

    PRIMARY KEY (asset_id, timestamp),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
            """)


## Table 14 - Corporate Actions
con.execute("CREATE SEQUENCE IF NOT EXISTS seq_action_id START 1;")

con.execute("""
    -- description: Tracks stock splits and other corporate events that affect price/quantity
    CREATE TABLE IF NOT EXISTS corporate_actions (
        action_id INTEGER PRIMARY KEY DEFAULT nextval('seq_action_id'),
        asset_id INTEGER,
        timestamp TIMESTAMP,
        action_type VARCHAR, -- 'SPLIT' or 'SPINOFF' (Dividends are in Table 11)
        action_value DOUBLE,  -- for split: the factor (e.g., 10.0 for 10-for-1 split)
        description VARCHAR,
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
    )
""")



## for clearing all users and their history
def db_reset():
    # 1. Delete transaction and history data (The most specific data)
    con.execute("DELETE FROM holdings")
    con.execute("DELETE FROM assets_transactions")
    con.execute("DELETE FROM cash_transactions")
    con.execute("DELETE FROM portfolio_history")
    con.execute("DELETE FROM portfolio_performance")

    # 2. Delete the portfolios (Which depend on users)
    con.execute("DELETE FROM portfolios")

    # 3. Now you can safely delete the users
    con.execute("DELETE FROM users")

    print("Cleanup successful! All user-related data has been wiped.")


con.close()
  