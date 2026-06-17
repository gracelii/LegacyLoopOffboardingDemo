"""
Thin Postgres/pgvector connection helper.

Swap point: if you migrate to ChromaDB later, this module (plus db_writer.py)
is the only thing that needs replacing -- ingestion and embedding logic stay the same.
"""
import os
import psycopg2
from psycopg2.extras import register_uuid
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Open a new Postgres connection with pgvector + UUID support registered."""
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ.get("PG_DB", "offboarding"),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", ""),
    )
    register_uuid(conn_or_curs=conn)
    register_vector(conn)
    return conn
