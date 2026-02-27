from DayBetes_food.database.schema import DBSchema
from DayBetes_food.database.connection import get_connection

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
