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
    """Open a new Postgres connection using environment variables."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "offboarding"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )

    # Register required extensions for vector search and UUIDs
    register_uuid(conn_or_curs=conn)
    register_vector(conn)

    return conn