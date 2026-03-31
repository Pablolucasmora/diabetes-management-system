from fasthtml.common import *

from DayBetes_food.components.stats.stats_shared import NUTRIENT_SPECS, format_amount


def stats_header(today, today_events_count: int):
    return Div(
        H1("Stats", cls="text-xl font-bold text-center"),
        P(
            f"Ingesta del dia {today.strftime('%d/%m/%Y')} ({today_events_count} comidas consumidas).",
            cls="text-sm text-gray-600 text-center",
        ),
        cls="web_container p-6 flex flex-col items-center gap-2 w-full",
    )


def daily_totals_section(
    today_events_count: int,
    historical_days_count: int,
    today_totals: dict,
    daily_average_totals: dict,
):
    return Div(
        H2("Totales y promedios diarios", cls="text-base md:text-lg font-semibold"),
        Div(
            Div(
                Div(
                    H3("Hoy", cls="text-base font-semibold text-gray-900"),
                    Span(
                        f"{today_events_count} comida(s) hoy · media de {historical_days_count} dia(s)",
                        cls="text-xs text-gray-600",
                    ),
                    cls="flex items-center justify-between gap-2",
                ),
                Table(
                    Thead(
                        Tr(
                            Th("Nutriente", cls="text-left py-1.5 pr-2 text-xs text-gray-600 font-medium"),
                            Th("Total hoy", cls="text-right py-1.5 px-1 text-xs text-gray-600 font-medium"),
                            Th("Media diaria", cls="text-right py-1.5 pl-1 text-xs text-gray-600 font-medium"),
                            cls="border-b border-gray-200",
                        )
                    ),
                    Tbody(
                        *[
                            Tr(
                                Td(label, cls="py-1.5 pr-2 text-sm text-gray-800"),
                                Td(
                                    f"{format_amount(today_totals.get(nutrient_key, 0.0), unit)} {unit}",
                                    cls="py-1.5 px-1 text-right text-sm font-medium tabular-nums",
                                ),
                                Td(
                                    f"{format_amount(daily_average_totals.get(nutrient_key, 0.0), unit)} {unit}",
                                    cls="py-1.5 pl-1 text-right text-sm font-medium text-gray-700 tabular-nums",
                                ),
                                cls="border-b border-gray-100 last:border-b-0",
                            )
                            for nutrient_key, label, unit in NUTRIENT_SPECS
                        ]
                    ),
                    cls="w-full",
                ),
                cls="web_container rounded-2xl p-4 flex flex-col gap-2",
            ),
            cls="grid grid-cols-1 gap-2 md:gap-3",
        ),
        cls="w-full flex flex-col gap-2",
    )


def _meal_type_card(meal_label: str, count: int, totals: dict, averages: dict):
    return Div(
        Div(
            H3(meal_label, cls="text-base font-semibold text-gray-900"),
            Span(f"{count} comida(s)", cls="text-xs text-gray-600"),
            cls="flex items-center justify-between gap-2",
        ),
        Table(
            Thead(
                Tr(
                    Th("Nutriente", cls="text-left py-1.5 pr-2 text-xs text-gray-600 font-medium"),
                    Th("Total", cls="text-right py-1.5 px-1 text-xs text-gray-600 font-medium"),
                    Th("Prom", cls="text-right py-1.5 pl-1 text-xs text-gray-600 font-medium"),
                    cls="border-b border-gray-200",
                )
            ),
            Tbody(
                *[
                    Tr(
                        Td(label, cls="py-1.5 pr-2 text-sm text-gray-800"),
                        Td(
                            f"{format_amount(totals.get(nutrient_key, 0.0), unit)} {unit}",
                            cls="py-1.5 px-1 text-right text-sm font-medium tabular-nums",
                        ),
                        Td(
                            f"{format_amount(averages.get(nutrient_key, 0.0), unit)} {unit}",
                            cls="py-1.5 pl-1 text-right text-sm font-medium text-gray-700 tabular-nums",
                        ),
                        cls="border-b border-gray-100 last:border-b-0",
                    )
                    for nutrient_key, label, unit in NUTRIENT_SPECS
                ]
            ),
            cls="w-full",
        ),
        cls="web_container rounded-2xl p-4 flex flex-col gap-2",
    )


def meal_breakdown_section(meal_groups: list[dict]):
    meal_cards = [
        _meal_type_card(
            meal_label=str(group.get("label") or ""),
            count=int(group.get("count") or 0),
            totals=group.get("totals") or {},
            averages=group.get("averages") or {},
        )
        for group in meal_groups
    ]
    return Div(
        H2("Desglose por tipo de comida", cls="text-base md:text-lg font-semibold"),
        Div(
            *meal_cards,
            cls="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 md:gap-3",
        )
        if meal_cards
        else Div(
            P("No hay comidas consumidas hoy para desglosar.", cls="text-sm text-gray-600"),
            cls="web_container rounded-2xl p-4 w-full",
        ),
        cls="w-full flex flex-col gap-2",
    )


def no_user_section():
    return Div(
        Div(
            H1("Stats", cls="text-xl font-bold text-center"),
            P("No hay usuario disponible.", cls="text-sm text-gray-600 text-center"),
            cls="web_container p-6 flex flex-col items-center gap-2",
        )
    )
