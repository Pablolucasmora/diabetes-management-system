from fasthtml.common import *

# 1. Configuración de cabeceras (Tu diseño original)
css = Link(rel="stylesheet", href="output.css")
app, rt = fast_app(hdrs=(css,), static_path='DayBetes_food/static', pico=False)

# --- TUS COMPONENTES (Estética original recuperada) ---

def PlusIcon(clases_extra: str = "", **hx):
    return Span(
        "✚",
        id="plus_icon",
        cls=f"text-9xl text-gray-500 cursor-pointer hover:text-gray-700 transition-all duration-500 {clases_extra}",
        **hx
    )

def BloqueIsla(texto, icono="🏝️", main=False, **hx):
    clases_base = "flex flex-col items-center justify-center p-2 md:p-3 m-[1px] rounded-full cursor-pointer transition-all duration-300 ease-in-out w-16 md:w-24 group"
    # Recuperamos tus colores exactos de cristal
    clases_estado = "bg-gray-300/40 shadow-inner ring-1 ring-white/50 scale-105" if main else "hover:bg-white/30 hover:shadow-md hover:scale-110 bg-white/5"
    
    return Button(
        Span(icono, cls="text-lg md:text-xl group-hover:scale-105 transition-all"),
        P(texto, cls="hidden md:block text-[10px] font-bold uppercase tracking-tighter"),
        cls=f"{clases_base} {clases_estado} border-none",
        **hx
    )

def IslaFlotante():
    return Div(
        BloqueIsla("Inicio", "🏠", hx_get="/", hx_target="#main_content", hx_push_url="true"),
        BloqueIsla("Stats", "📊", hx_get="/stats", hx_target="#main_content", hx_push_url="true"),
        BloqueIsla("Chat", "💬", hx_get="/chat", hx_target="#main_content", hx_push_url="true"),
        BloqueIsla("Ajustes", "⚙️", hx_get="/ajustes", hx_target="#main_content", hx_push_url="true"),
        cls="fixed bottom-14 left-1/2 -translate-x-1/2 z-50 flex items-center justify-center gap-2 md:gap-3 p-2 bg-white/5 backdrop-blur-xl border border-white/30 shadow-2xl ring-1 ring-inset ring-white/20 rounded-full"
    )

# --- RUTAS ---

@rt("/")
def get():
    # El contenido que tú diseñaste como "Página Principal"
    contenido = Div(
        H1("Menu", cls="text-4xl font-bold text-center text-gray-600 font-sans"),
        Div(
            Section(
                PlusIcon(hx_get="/toggle_menu?abierto=False", hx_target="#menu_container", hx_swap="outerHTML",
                         clases_extra="col-span-1 translate-x-[68px] place-self-right"),
                Div(id="menu_container", cls="hidden"),
                id="section_plus",
                cls="max-w-64 grid grid-cols-3 items-center justify-center bg-gray-200/50 shadow-md rounded-3xl mt-5 mb-10 w-5/6 md:w-3/5 min-h-56 p-1 transition-all duration-500"
            ),
            # InputSection integrada
            Section(
                Input(value=22, type="tel", placeholder="Search...", inputmode="numeric",
                      cls="text-center max-w-64 p-3 rounded-2xl bg-gray-200/50 border border-gray-300/30 shadow-md focus:outline-none transition-all"),
                cls="w-4/5 md:w-2/5 flex justify-center"
            ),
            cls="flex flex-col items-center justify-center gap-4"
        ),
        id="main_content" # Este es el ID que HTMX cambiará
    )
    
    # IMPORTANTE: Devolvemos el contenido envuelto en el Main con la Isla
    return Title("DayBetes"), Main(
        contenido,
        IslaFlotante(),
        cls="bg-[#f0eadb] min-h-screen w-full flex flex-col items-center justify-center"
    )

@rt("/toggle_menu")
def get(abierto: bool = False):
    # Aquí es donde estaba el fallo: al abrir el menú, devolvemos el Menú + el Icono nuevo
    if not abierto:
        opciones = ["New food", "Search", "Manual food"]
        return Div(
            Div(
                *[Button(o, cls="w-full text-gray-700 text-md p-2 hover:bg-white/60 rounded-xl transition-all border border-gray-300/30 shadow-sm mb-2") for o in opciones],
                cls="col-start-2 col-span-2 flex flex-col items-center justify-center p-2"
            ),
            PlusIcon(clases_extra="plus-active text-7xl col-start-1 col-span-1 place-self-right block",
                     hx_get="/toggle_menu?abierto=True", hx_target="#menu_container", hx_swap="outerHTML"),
            id="menu_container",
            cls="contents" # 'contents' hace que el Div no rompa el Grid del padre
        )
    return Div(id="menu_container", cls="hidden"), PlusIcon(clases_extra="col-start-1 col-span-1 translate-x-[68px] place-self-right", hx_get="/toggle_menu?abierto=False", hx_target="#menu_container", hx_swap="outerHTML")

# Repite este patrón para /stats, /chat, etc., devolviendo solo el contenido interno
@rt("/stats")
def get():
    return Div(H1("Estadísticas", cls="text-4xl rotate-x-180 font-bold text-gray-600"), id="main_content")

serve()