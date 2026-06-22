import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase_client() -> Client:
    # Create and cache a Supabase client
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]

    return create_client(url, key)


def test_supabase_connection() -> tuple[bool, str, list[dict]]:
    # Test Supabase connection using a lightweight query
    try:
        supabase = get_supabase_client()

        response = (
            supabase
            .table("assets")
            .select("*")
            .limit(5)
            .execute()
        )

        return True, "Supabase connection works.", response.data or []

    except Exception as e:
        return False, f"Supabase connection failed: {e}", []