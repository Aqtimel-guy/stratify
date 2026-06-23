import streamlit as st
import requests


def get_public_gcs_base_url() -> str:
    # Return the public base URL for the configured GCS bucket
    bucket_name = st.secrets["GCS_BUCKET_NAME"]
    return f"https://storage.googleapis.com/{bucket_name}"


def test_public_gcs_file_exists(file_path: str) -> tuple[bool, str]:
    # Test whether a public file exists in the GCS bucket
    base_url = get_public_gcs_base_url()
    url = f"{base_url}/{file_path.lstrip('/')}"

    try:
        response = requests.head(url, timeout=10)

        if response.status_code == 200:
            return True, f"Public GCS file is reachable: {file_path}"

        if response.status_code == 404:
            return False, f"File not found in public GCS: {file_path}"

        if response.status_code == 403:
            return False, (
                f"File exists or bucket exists, but public access is denied: {file_path}"
            )

        return False, (
            f"Unexpected response from GCS. "
            f"Status code: {response.status_code}"
        )

    except Exception as e:
        return False, f"Public GCS test failed: {e}"


def test_gcs_connection() -> tuple[bool, str, list[str]]:
    # Test public GCS access using a known file path
    test_file_path = "connection_test.txt"

    ok, message = test_public_gcs_file_exists(test_file_path)

    return ok, message, [test_file_path] if ok else []