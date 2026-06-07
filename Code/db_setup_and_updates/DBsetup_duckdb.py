import duckdb


# creating / opening connection
con = duckdb.connect('C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb')  

# creating tables if not exist

## Table 0 -test table
con.execute("""
            -- description: A test table to verify the connection and setup
            CREATE TABLE IF NOT EXISTS 
            test_table (
                col1 INTEGER,
                col2 VARCHAR,
                PRIMARY KEY (col1)
            )""")

## Table 1 - Assets
con.execute("""
            -- description: A table of all tradeable assets in Stratify
            
            CREATE TABLE IF NOT EXISTS 
            assets (
                asset_id INTEGER PRIMARY KEY,
                ticker VARCHAR,
                name VARCHAR,
                sector VARCHAR,
                industry VARCHAR,
                is_etf BOOLEAN
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
            
            CREATE TABLE IF NOT EXISTS 
            fundamentals (
                asset_id INTEGER,
                timestamp TIMESTAMP,
                pe_ratio double,
                market_cap double,
                revenue double,
                eps double,
                shares_outstanding double,
                PRIMARY KEY (asset_id, timestamp),
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            )""")

## Table 4 - Features
con.execute("""
            -- description: Calculated features for assets, used for analysis
            
            CREATE TABLE IF NOT EXISTS features (
                asset_id INTEGER,
                timestamp TIMESTAMP,
                -- Technicals
                volatility DOUBLE,
                momentum_relative_sp_1y DOUBLE,
                avg_volume DOUBLE,
                volume_spike DOUBLE,
                rsi_14 DOUBLE,
                atr_14 DOUBLE,
                dist_sma50 DOUBLE,
                dist_sma200 DOUBLE,
                -- Risk
                beta_90d DOUBLE,
                sharpe_ratio_90d DOUBLE,
                max_drawdown_90d DOUBLE,
                -- Fundamental Derived (Calculated from fundamentals table)
                revenue_growth_yoy DOUBLE,
                eps_growth_yoy DOUBLE,
                -- Returns
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
            )""")



## Table 5 - Users
con.execute("""
            -- description: Registered users of the platform
            
            CREATE TABLE IF NOT EXISTS 
            users (
                user_id INTEGER PRIMARY KEY,
                email VARCHAR UNIQUE,
                first_name VARCHAR,
                middle_name VARCHAR,
                last_name VARCHAR,
                date_of_birth DATE,
                password_hash VARCHAR
            )""")


## Table 6 - Portfolios
con.execute("""
            -- description: Investment portfolios, users can create several
            
            CREATE TABLE IF NOT EXISTS 
            portfolios (
                portfolio_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                portfolio_name VARCHAR,
                created_at TIMESTAMP, -- when the user opened the portfolio
                starting_at TIMESTAMP, -- historical start date for simulation
                preferred_currency VARCHAR,
                available_cash DOUBLE,
                portfolio_value DOUBLE, -- not used, unable to deleate, all are empty
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

## Table 8 - Portfolio Performance
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
con.execute("""
            -- description: Records all cash deposits and withdrawals for portfolios
            
            CREATE TABLE IF NOT EXISTS 
            cash_transactions (
                transaction_id INTEGER PRIMARY KEY,
                portfolio_id INTEGER,
                timestamp TIMESTAMP,
                amount DOUBLE,
                transaction_type VARCHAR, -- deposit/withdraw
                reference VARCHAR,
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

# Table 14 - Grouped factors normelized by percentile (for strategy)
con.execute("""
            -- normelized factors. both by sector and market
            -- the information will be derived from asset_factors_raw_v1
            -- higher = better , ranking will be between 0-100
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_percentile (
        
        asset_id INTEGER,
        timestamp TIMESTAMP,
        
        momentum_factor_sector DOUBLE,      -- short&long - term price behavior
        momentum_factor_market DOUBLE,      -- short&long - term price behavior
        value_factor_sector DOUBLE,         -- valuation
        value_factor_market DOUBLE,         -- valuation
        quality_factor_sector DOUBLE,       -- profitability & leverage
        quality_factor_market DOUBLE,       -- profitability & leverage
        growth_factor_sector DOUBLE,        -- fundamental growth
        growth_factor_market DOUBLE,        -- fundamental growth
        defensive_factor_sector DOUBLE,     -- downside protection (vol + drawdown)
        defensive_factor_market DOUBLE,     -- downside protection (vol + drawdown)
        size_factor_sector DOUBLE,          -- optional but useful (smaller = better )
        size_factor_market DOUBLE,          -- optional but useful (smaller = better )
        liquidity_factor_sector DOUBLE,     -- execution quality
        liquidity_factor_market DOUBLE,     -- execution quality
        diversification_factor_sector DOUBLE, -- oposing correlation level
        diversification_factor_market DOUBLE,   -- oposing correlation level

        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
            """)

# Table 15 - Grouped factors normelized by Z-score (for strategy)
con.execute("""
            -- normelized factors. both by sector and market
            -- the information will be derived from asset_factors_raw_v1
            -- higher = better , ranking will be between -3 to 3
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_zscore (
        
        asset_id INTEGER,
        timestamp TIMESTAMP,
        
        momentum_factor_sector DOUBLE,      -- short&long - term price behavior
        momentum_factor_market DOUBLE,      -- short&long - term price behavior
        value_factor_sector DOUBLE,         -- valuation
        value_factor_market DOUBLE,         -- valuation
        quality_factor_sector DOUBLE,       -- profitability & leverage
        quality_factor_market DOUBLE,       -- profitability & leverage
        growth_factor_sector DOUBLE,        -- fundamental growth
        growth_factor_market DOUBLE,        -- fundamental growth
        defensive_factor_sector DOUBLE,     -- downside protection (vol + drawdown)
        defensive_factor_market DOUBLE,     -- downside protection (vol + drawdown)
        size_factor_sector DOUBLE,          -- optional but useful (smaller = better )
        size_factor_market DOUBLE,          -- optional but useful (smaller = better )
        liquidity_factor_sector DOUBLE,     -- execution quality
        liquidity_factor_market DOUBLE,     -- execution quality
        diversification_factor_sector DOUBLE, -- oposing correlation level
        diversification_factor_market DOUBLE,   -- oposing correlation level

        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
            """)





# Table 16 - Grouped factors normelized to a final grade (UI LEVEL)(for strategy)
con.execute("""
            -- normelized factors. both by sector and market
            -- the information will be derived from asset_factors_normalized_zscore and asset_factors_normalized_percentile
            -- higher = better , ranking will be between 1 - 100
    CREATE TABLE IF NOT EXISTS asset_factors_normalized_final (
        
        asset_id INTEGER,
        timestamp TIMESTAMP,
        
        momentum_factor_sector DOUBLE,      -- short&long - term price behavior
        momentum_factor_market DOUBLE,      -- short&long - term price behavior
        value_factor_sector DOUBLE,         -- valuation
        value_factor_market DOUBLE,         -- valuation
        quality_factor_sector DOUBLE,       -- profitability & leverage
        quality_factor_market DOUBLE,       -- profitability & leverage
        growth_factor_sector DOUBLE,        -- fundamental growth
        growth_factor_market DOUBLE,        -- fundamental growth
        defensive_factor_sector DOUBLE,     -- downside protection (vol + drawdown)
        defensive_factor_market DOUBLE,     -- downside protection (vol + drawdown)
        size_factor_sector DOUBLE,          -- optional but useful (smaller = better )
        size_factor_market DOUBLE,          -- optional but useful (smaller = better )
        liquidity_factor_sector DOUBLE,     -- execution quality
        liquidity_factor_market DOUBLE,     -- execution quality
        diversification_factor_sector DOUBLE, -- oposing correlation level
        diversification_factor_market DOUBLE,   -- oposing correlation level

        PRIMARY KEY (asset_id, timestamp),
        FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
            """)

# Table 17 - user preferences (for strategy)
con.execute("CREATE SEQUENCE IF NOT EXISTS portfolio_strategy_seq;")

con.execute("""
            -- user preferences for the strategy builder. this will be used to create the strategy and give feedback to the user
            -- all values will be between 0-100, higher means the user prefer this factor more

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
        size_preference DOUBLE DEFAULT 50, -- bigger = prefer smaller companies
        liquidity_preference DOUBLE DEFAULT 50,
        diversification_preference DOUBLE DEFAULT 50,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
);
            """)



# Table 18 - Multi-strategy
con.execute("CREATE SEQUENCE IF NOT EXISTS multi_strategy_seq;")
con.execute("""
    CREATE TABLE IF NOT EXISTS multi_strategy (
        multi_strategy_id INTEGER PRIMARY KEY DEFAULT nextval('multi_strategy_seq'),
        user_id INTEGER,
        portfolio_id INTEGER,
        
        -- Strategy 1 Allocation
        strategy_1_id INTEGER DEFAULT NULL,
        strategy_1_pct DOUBLE DEFAULT 0,
        
        -- Strategy 2 Allocation
        strategy_2_id INTEGER DEFAULT NULL,
        strategy_2_pct DOUBLE DEFAULT 0,
        
        -- Strategy 3 Allocation
        strategy_3_id INTEGER DEFAULT NULL,
        strategy_3_pct DOUBLE DEFAULT 0,
        
        -- Strategy 4 Allocation
        strategy_4_id INTEGER DEFAULT NULL,
        strategy_4_pct DOUBLE DEFAULT 0,
        
        -- Overall monthly investment amount for this multi-strategy mix
        monthly_deposit INTEGER DEFAULT 0
        
        -- Sectors to Focus
        focus_sectors VARCHAR DEFAULT NULL
        
        -- Sectors to AVOID
        avoid_sectors VARCHAR DEFAULT NULL
        
        -- Deposits habbits
        monthly_deposit INTEGER DEFAULT 0
        initial_investment INTEGER DEFAULT 0
        
        -- Execution Settings
        transaction_fee_per_trade_buy DOUBLE DEFAULT 0,
        transaction_fee_per_trade_sell DOUBLE DEFAULT 0,
        transaction_fee_deposit DOUBLE DEFAULT 0,
        transaction_fee_withdraw DOUBLE DEFAULT 0,
        
        -- Diversification Level
        diversification_level INTEGER DEFAULT 1 -- 1 low, 2 medium, 3 high


    );
""")


#df_test = con.execute("SELECT * FROM user_preferences_strategy").df()
#print(df_test)
## for clearing all users and their history


def db_reset():
    # 1. Delete transaction and history data (The most specific data)
    con.execute("DELETE FROM holdings")
    con.execute("DELETE FROM assets_transactions")
    con.execute("DELETE FROM cash_transactions")
    con.execute("DELETE FROM portfolio_history")
    con.execute("DELETE FROM portfolio_performance")
    con.execute("DELETE FROM user_preferences_strategy")

    # 2. Delete the portfolios (Which depend on users)
    con.execute("DELETE FROM portfolios")

    # 3. Now you can safely delete the users
    con.execute("DELETE FROM users")

    print("Cleanup successful! All user-related data has been wiped.")



print(
    con.execute("""
            SELECT sector , COUNT(*) as num_assets
            FROM assets
            """).df()
      )


con.close()

