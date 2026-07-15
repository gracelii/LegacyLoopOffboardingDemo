"""
Credentials helper for Google service account auth.

Supports two modes:
1. Streamlit deployment: reads the service account JSON from st.secrets
   (set GOOGLE_SERVICE_ACCOUNT_JSON in Streamlit Cloud secrets)
2. Local development: reads from the service_account.json file on disk
   (set GOOGLE_SERVICE_ACCOUNT_FILE in .env)

This means the service account key never needs to be committed to GitHub
or pasted anywhere publicly.
"""
import json
import os
from google.oauth2 import service_account


def get_credentials(scopes: list[str]) -> service_account.Credentials:
    """
    Return service account credentials for the given scopes.
    Tries Streamlit secrets first, falls back to local file.
    """
    # Try Streamlit secrets first (production/deployed mode)
    try:
        import streamlit as st
        if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
            service_account_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
            return service_account.Credentials.from_service_account_info(
                service_account_info, scopes=scopes
            )
    except Exception:
        pass  # Not running in Streamlit or secret not set -- fall through to file

    # Fall back to local file (development mode)
    service_account_file = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"
    )
    return service_account.Credentials.from_service_account_file(
        service_account_file, scopes=scopes
    )