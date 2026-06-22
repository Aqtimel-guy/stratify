import streamlit as st
import pandas as pd

from cloud_connections.supabase_connection import test_supabase_connection
from cloud_connections.gcs_connection import test_gcs_connection


st.set_page_config(
    page_title="Stratify Cloud Test",
    layout="wide"
)

st.title("Stratify Cloud Connection Test")

st.markdown("""
This temporary app tests cloud connections only.

It does not connect to the local DuckDB database.
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


st.divider()

st.subheader("2. Google Cloud Storage public read")

gcs_ok, gcs_message, gcs_files = test_gcs_connection()

if gcs_ok:
    st.success(gcs_message)
    st.write("Files found:", len(gcs_files))
    st.write(gcs_files)
else:
    st.error(gcs_message)