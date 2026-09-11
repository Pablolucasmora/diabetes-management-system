# Convenciones de frontend - DayBetes

Este documento define cómo se construye el HTML/CSS de los componentes de DayBetes (FastHTML + Tailwind) para que el criterio de diseño responsive, tamaño de inputs y teclado en móvil sea el mismo en toda la web, en vez de decidirse componente a componente.

Este documento complementa `conventions/code_conventions.md`.

## 1. Breakpoints y mobile-first

- Las clases de Tailwind **sin prefijo** son el diseño para pantallas que no son ni `md` ni `lg` (móvil). No se usa el prefijo `sm:` en ningún componente.
- Las clases con prefijo `md:` y `lg:` son el diseño de ordenador/tablet grande.
- Un componente nuevo se escribe primero para móvil (clases sin prefijo) y luego se le añaden `md:`/`lg:` solo donde el diseño de ordenador deba diferir.
- No se introduce ningún otro prefijo de breakpoint (`sm:`, `xl:`, `2xl:`, valores custom en píxeles) sin acordarlo antes, siguiendo el procedimiento de "Convenciones faltantes" de `CLAUDE.md`.

## 2. Tamaño de los inputs de texto

- Todo `Input` de texto (incluye `type="text"`, `type="number"`, `type="email"`, etc., y los `textarea`) usa `text-sm` como tamaño de fuente. No se reduce a `text-xs` en móvil ni se amplía en `md:`/`lg:` salvo que exista una razón documentada para ese input concreto.
- Esta regla es independiente de los breakpoints de la sección 1: el tamaño de fuente de un input de texto no cambia entre móvil y ordenador.
- La sección 3 documenta la excepción para controles nativos del navegador (`time`, `date`, `number` con spinner), que no siguen esta regla porque su render no depende de `text-sm`.

## 3. Excepción: controles nativos del navegador (`time`, `date`, `number` con spinner)

Los inputs cuyo control visual lo dibuja el navegador (`type="time"`, `type="date"`, `type="datetime-local"`, `type="number"` con las flechas de incremento) **no** siguen directamente la regla de la sección 2. Su tamaño interno (segmentos de hora, calendario, spinner) lo decide el user-agent, no el `text-sm`/padding que le apliquemos, y por eso se comportan distinto en pantallas estrechas:

- En rejillas o filas donde varios de estos controles comparten ancho (por ejemplo, `start_time`/`end_time` en la misma fila), cada input lleva `min-w-0` y `overflow-hidden`. Sin `overflow-hidden`, el render interno del control puede pintarse fuera de los límites de su caja e invadir visualmente al control vecino cuando el espacio es estrecho — así fue como se detectó esta regla, en `meal_type_schedule_row` (`DayBetes_food/components/settings/settings_main.py`).
- El padding de estos controles puede reducirse en móvil (sin prefijo) respecto al valor de `md:`/`lg:`, siguiendo el mobile-first de la sección 1, en vez de mantener fijo el mismo padding que un input de texto normal.
- Esta excepción no autoriza a saltarse `text-sm` "porque es un input raro": si el control no es nativo (por ejemplo, un `<input type="text">` que solo parece un selector), sigue la regla general de la sección 2.

## 4. Teclado numérico en inputs numéricos

- Todo input que captura un valor numérico (cantidad, dosis, gramos, minutos, etc.) debe abrir el teclado numérico del dispositivo móvil mediante el atributo `inputmode`, aunque el propio `type` ya sea `"number"`.
- El valor de `inputmode` se elige según si el campo admite decimales, no se usa siempre el mismo:
  - `inputmode="decimal"` si el campo admite decimales (típicamente cuando lleva `step` con parte fraccionaria, p. ej. `step="0.1"`).
  - `inputmode="numeric"` si el campo es siempre un entero (p. ej. `step="1"` o sin decimales posibles).
- `inputmode="number"` **no es un valor válido** del atributo (los valores válidos son `none`, `text`, `decimal`, `numeric`, `tel`, `search`, `email`, `url`) y no debe usarse. Un input numérico tampoco debe quedarse con `inputmode="text"`.
- Un input con `inputmode` incorrecto o ausente en un campo numérico se considera un defecto a corregir, no una variación de estilo aceptable.
