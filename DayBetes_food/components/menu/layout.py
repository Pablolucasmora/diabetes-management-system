from fasthtml.common import *

def BlockIsland(text, icon="images/ui/menu.svg", name="nav", value="home", **hx):
    return Label(
        Input(
            type="radio",
            name=name,
            value=value,
            cls="hidden peer",
        ),

        Img(id=value, src=icon, cls="""
            w-6 h-6
            text-lg md:text-xl 
            transition-all duration-300
            group-has-[:checked]:scale-110
        """),

        P(text, cls="""
            hidden md:block mt-1
            text-[10px] font-bold uppercase tracking-tighter
        """),

        cls="""
            flex flex-col items-center justify-center
            p-2 md:p-3 
            rounded-full
            cursor-pointer
            transition-all duration-300 ease-in-out
            w-16 md:w-24
            border-none
            group

            bg-transparent
            hover:shadow-md
        """,
        data_nav_item=value,
        **hx
    )

def FloatingIsland():
    show_cart_js = """
        var b = document.querySelector('#cart_button');
        if(!b) return;
        b.classList.remove('invisible','opacity-0','pointer-events-none');
        requestAnimationFrame(function(){ b.classList.add('opacity-100'); });
    """

    return Div(
        Div(
            Div(
                id="island_active_indicator",
                cls="""
                    absolute left-0 top-0 z-0
                    rounded-full bg-gray-300/40
                    ring-1 ring-white/50 shadow-inner
                    transition-all duration-300 ease-in-out
                    pointer-events-none
                    opacity-0
                """,
            ),
            BlockIsland("Menu", icon="images/ui/menu.svg", value="menu", hx_get="/menu", hx_target="#main_content", hx_swap="innerHTML", hx_push_url="true", **{"hx-on:click": show_cart_js}),
            BlockIsland("Stats", icon="images/ui/stats.svg", value="stats", hx_get="/stats", hx_target="#main_content", hx_push_url="true"),
            BlockIsland("Food", icon="images/ui/food.svg", value="food", hx_get="/food", hx_target="#main_content", hx_push_url="true", **{"hx-on:click": show_cart_js}),
            BlockIsland("Settings", icon="images/ui/settings.svg", value="settings", hx_get="/settings", hx_target="#main_content", hx_push_url="true"),
            cls="""
                relative
                flex items-center justify-center
                gap-2 md:gap-3
                p-2
                overflow-hidden

                bg-white/5 backdrop-blur-xl
                border border-white/80
                shadow-lg
                ring-1 ring-inset ring-white/20
                rounded-full
            """
        ),
        cls="""
            fixed bottom-6 left-1/2 -translate-x-1/2
            z-50
        """
    )

def IslandLogo():
    return Div(
        Img(id="logo", src="images/ui/Logo_DayBetes_food.svg",
            cls="""
                lg:w-64 md:w-64
                w-48 
                transition-all 
            """
        ),
        cls="""
            bg-[#f6f2eb]/50 backdrop-blur-lg
            border-[1px] border-white/80
            rounded-4xl shadow-lg
            px-16 py-5 md:mt-2 lg:mt-2 mt-0 m-8 z-50
            fixed top-5
        """
    )

def Cart(display=True):
    base_classes="""
        fixed md:bottom-31 lg:bottom-31 bottom-24
        left-1/2 -translate-x-1/2 md:translate-x-29
        lg:translate-x-29 translate-x-20
        transition-all duration-250 ease-in-out
        web_button
        md:p-4 lg:p-4 p-3 bg-[#f6f2eb]/50 backdrop-blur-lg
        rounded-3xl md:rounded-4xl lg:rounded-4xl md:w-22 lg:w-22
        opacity-100
    """

    if not display:
        base_classes += " invisible opacity-0 pointer-events-none"

    return Div(
        Img(src="images/ui/cart.svg", cls="w-6 h-6 justify-self-center"),
        P("Cart", cls="""
            hidden md:block mt-1
            text-[10px] text-center font-bold uppercase tracking-tighter
        """),
        cls=base_classes,
        id="cart_button",
        hx_get="/cart",
        hx_target="#main_content",
        **{
            "hx-on:click": (
                "this.classList.remove('opacity-100');"
                "this.classList.add('opacity-0','pointer-events-none');"
                "setTimeout(() => this.classList.add('invisible'), 260);"
            )
        },
        hx_push_url="true"
    )
