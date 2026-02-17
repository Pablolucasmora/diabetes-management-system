import os
import psycopg

def get_connection():
    # 1. Recuperamos la URL de conexión que inyectó Docker
    db_url = os.getenv("DATABASE_URL")
    
    # 2. Medida de seguridad por si Docker falla al pasar la variable
    if not db_url:
        raise ValueError("Error crítico: DATABASE_URL no encontrada en el entorno.")
    
    # 3. Psycopg se conecta usando la URL completa
    return psycopg.connect(db_url)