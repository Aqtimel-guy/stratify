import streamlit as st
import pandas as pd
import datetime as dt

from Code.functions.portfolio_managment import *
from Code.functions.db_manager import *
from Code.functions.trading_logic import *
from Code.functions.users_managment import *
from Code.functions.UI_components import *








DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'

con = duckdb.connect(DB_PATH)
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")


portfolio_id = con.execute("SELECT portfolio_id FROM portfolios ORDER BY portfolio_id ASC")

test = con.execute(""" select *
                   from 
                   portfolios j 
                   join 
                   user_preferences_strategy s 
                   on
                   j.portfolio_id = s.portfolio_id
                   where j.portfolio_id = ?", [portfolio_id]).df()
""")
print(test)
#get_strategy_matched_assets(
 #   con=con,  
  #  portfolio_id=portfolio_id,
   # sim_date= "2026-05-05" , 
    #num_assets=5
#)

