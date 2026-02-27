from fasthtml.common import *

def quick_actions():
    actions = Div(
        Div(Button("Search", cls="boton_web"),
            Button("Food", cls="boton_web"),
            Button("Log", cls="boton_web"),
            cls="""
            contenedor_web
            grid grid-cols-2 grid-rows-2 md:p-4 lg:p-4 p-3 md:gap-y-3 lg:gap-y-3 gap-y-3
            md:gap-x-2 lg:gap-x-2 gap-x-1
        
        """),
        Div( H1("Carrito", cls="font-bold text-center"),
            cls="""
            contenedor_web
            grid grid-cols-2 grid-rows-2 md:p-4 lg:p-4 p-3 md:gap-y-3 lg:gap-y-3 gap-y-3
            md:gap-x-2 lg:gap-x-2 gap-x-1
        
        """),
        cls= """
            transition-all
            md:w-md lg:w-md
            w-xs
            md:h-40 md:h-40
            h-32
            grid grid-cols-2 gap-6 
            
 0
        """)

    return actions

