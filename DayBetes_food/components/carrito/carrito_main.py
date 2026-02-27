from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_eventos_carrito, get_all_usuarios


def CarritoCard(evento):
    """Card de evento planificado"""
    return Div(
        H3(f"Evento #{evento['id']}", cls="font-bold"),
        P(f"Estado: {evento['estado']}"),
        P(f"Hora: {evento['hora_comida']}"),
        cls="border p-2 rounded mb-2 bg-white"
    )


def carrito_main(conexion):
    usuarios = get_all_usuarios(conexion)
    if not usuarios:
        return Div(H2("No hay usuarios"), cls="flex flex-col items-center")
    
    user_id = usuarios[0]["id"]
    eventos = get_eventos_carrito(conexion, user_id)
    
    if not eventos:
        return Div(
            H1("Carrito vacío", cls="text-gray-500"),
            P("Añade alimentos desde Food"),
            cls="""
                flex flex-col items-center 
                justify-center gap-6 
                md:mt-7 lg:mt-7 mt-2
            """
        )
    
    return Div(
        H1("Carrito de comida", cls="text-xl font-bold mb-4"),
        *[CarritoCard(evento) for evento in eventos],
        cls="""
            flex flex-col items-center 
            justify-center gap-6 
            md:mt-7 lg:mt-7 mt-2
        """
    )