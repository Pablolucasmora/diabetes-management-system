import psycopg
from psycopg.rows import dict_row

from DayBetes_food.config import DATABASE_URL


def get_connection():
    # DATABASE_URL ya se valida una sola vez, al arrancar, en config.py.
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

