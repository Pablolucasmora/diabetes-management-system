from .database_manager import DatabaseManager

# Creamos la instancia global una sola vez
db_manager = DatabaseManager(db_path="diabetes_app.db")

def get_db_manager():
    """
    Permite que cualquier archivo use db_manager.execute_query() 
    sin tener que importar la clase ni crear objetos nuevos.
    """
    return db_manager