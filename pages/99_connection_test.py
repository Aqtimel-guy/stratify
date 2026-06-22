import streamlit as st
import pandas as pd

from cloud_connections.supabase_connection import test_supabase_connection


st.set_page_config(
    page_title="Connection Test",
    layout="wide"
)


st.title("Live Server Connection Test")

st.markdown("""
This page checks whether the deployed app can connect to Supabase.
""")


st.divider()


st.subheader("1. Supabase")

supabase_ok, supabase_message, supabase_data = test_supabase_connection()

if supabase_ok:
    st.success(supabase_message)

    if supabase_data:
        st.dataframe(pd.DataFrame(supabase_data), use_container_width=True)
    else:
        st.info("Supabase connected, but no rows were returned.")
else:
    st.error(supabase_message)