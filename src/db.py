"""
Postgres/pgvector connection helper.

Supports two modes:
1. Streamlit deployment: reads connection params from st.secrets
2. Local development: reads from .env via os.environ
"""
import os
import psycopg2
from psycopg2.extras import register_uuid
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def _get_config(key: str, default: str = "") -> str:
    """Read a config value from Streamlit secrets if available, else os.environ."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


def get_connection():
    """Open a new Postgres connection with pgvector + UUID support registered."""
    conn = psycopg2.connect(
        host=_get_config("PG_HOST", "localhost"),
        port=_get_config("PG_PORT", "5432"),
        dbname=_get_config("PG_DB", "offboarding"),
        user=_get_config("PG_USER", "postgres"),
        password=_get_config("PG_PASSWORD", ""),
    )
    register_uuid(conn_or_curs=conn)
    register_vector(conn)
    return conn