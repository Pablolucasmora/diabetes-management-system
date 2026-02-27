from DayBetes_food.database.schema import DBSchema
from DayBetes_food.database.connection import get_connection # Importamos la función, no el cursor estático

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Definimos el orden lógico (de padres a hijos)
        tablas = [
            DBSchema.usuario, 
            DBSchema.catalogo, 
            DBSchema.ingesta_manual,
            DBSchema.nevera,
            DBSchema.etiquetas,
            DBSchema.recetas,
            DBSchema.etiquetas_vinculadas,
            DBSchema.evento_ingesta,
            DBSchema.porcion_detalle
        ]
        
        for tabla_sql in tablas:
            cur.execute(tabla_sql)
            
        conn.commit()
        print("✅ Base de datos inicializada con éxito.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al inicializar la base de datos: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()