# Place this inside your main function to see what's actually there
import streamlit as st

st.write("Current Session State Keys:")
st.write(list(st.session_state.keys()))