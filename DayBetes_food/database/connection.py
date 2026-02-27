import os
import psycopg
from psycopg.rows import dict_row


def get_connection():
    # 1. Retrieve the connection URL that Docker injected
    db_url = os.getenv("DATABASE_URL")
    
    # 2. Security measure in case Docker fails to pass the variable
    if not db_url:
        raise ValueError("Critical error: DATABASE_URL not found in the environment.")
    
    # 3. Psycopg connects using full URL
    return psycopg.connect(db_url, row_factory=dict_row)

