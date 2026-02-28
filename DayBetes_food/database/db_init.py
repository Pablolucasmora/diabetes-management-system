import os
from DayBetes_food.database.schema import DBSchema
from DayBetes_food.database.connection import get_connection

DEFAULT_USER_NAME = os.getenv("DEFAULT_USER_NAME", "Default User")
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "default@daybetes.local")
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "change-me")


def _ensure_email_column(cursor):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'mail';
        """
    )
    has_mail = cursor.fetchone() is not None
    if has_mail:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'email';
            """
        )
        has_email = cursor.fetchone() is not None
        if not has_email:
            cursor.execute("ALTER TABLE users RENAME COLUMN mail TO email;")


def _ensure_default_user(cursor):
    cursor.execute("SELECT id FROM users WHERE email = %(email)s;", {"email": DEFAULT_USER_EMAIL})
    row = cursor.fetchone()
    if row:
        return

    cursor.execute("SELECT id FROM users LIMIT 1;")
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        INSERT INTO users (name, email, password, category)
        VALUES (%(name)s, %(email)s, %(password)s, 'admin');
        """,
        {
            "name": DEFAULT_USER_NAME,
            "email": DEFAULT_USER_EMAIL,
            "password": DEFAULT_USER_PASSWORD,
        },
    )

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        tables = [
            DBSchema.users, 
            DBSchema.catalog, 
            DBSchema.manual_intake,
            DBSchema.fridge,
            DBSchema.tags,
            DBSchema.recipe,
            DBSchema.linked_tags,
            DBSchema.intake_event,
            DBSchema.portion_detail
        ]
        
        for table_sql in tables:
            cur.execute(table_sql)

        _ensure_email_column(cur)
        _ensure_default_user(cur)
            
        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()
