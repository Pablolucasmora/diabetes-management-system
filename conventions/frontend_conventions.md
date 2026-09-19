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

## 5. Posición del scroll al cambiar de página

- **Regla general**: cada vez que se cambia de página, la página nueva debe empezar en su punto más alto (el inicio). El usuario nunca debe aterrizar en una página nueva a media altura y tener que subir para ver la cabecera, el buscador o los filtros.
- La regla aplica a cualquier navegación, aunque no recargue el navegador: en DayBetes la mayoría son swaps de htmx sobre `#main_content` (`hx_get`/`hx_post` + `hx_target="#main_content"`), y htmx **no** reposiciona el scroll por sí solo — conserva el del documento anterior. Si el botón que navega está al final de la página actual, la página nueva aparece desplazada hacia abajo.
- **Cómo se cumple**: el elemento que dispara la navegación lleva el reset explícito de scroll junto a sus atributos de htmx:

  ```python
  **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
  ```

  Se usa `behavior: 'auto'` (salto inmediato, sin animación): el scroll se reposiciona antes de que llegue el contenido nuevo, y una animación suave aquí solo se percibe como un rebote.
- La regla también cubre los botones de vuelta ("Back", "Back to recipe", "Cancel"), no solo los de ida: volver a una página es cambiar de página.
- **Excepción**: una navegación concreta puede conservar la posición de scroll (o aterrizar en otro punto) **solo si el usuario lo pide explícitamente para ese caso**. Cuando eso ocurra, se documenta aquí el caso y el motivo, siguiendo el procedimiento de "Convenciones faltantes" de `CLAUDE.md`. No es una excepción que pueda decidirse componente a componente.
- No se consideran cambio de página, y por tanto **no** resetean el scroll, los refrescos parciales que reemplazan solo un bloque de la página actual sin cambiar de pantalla (por ejemplo `hx_target="#food-list"` al escribir en un buscador, o el re-render de una fila tras editarla).

## 6. La interfaz muestra exactamente lo que se guardaría

**Regla general** (decisión 2026-09-18): lo que un control muestra tiene que ser **exactamente** lo que se guardaría en la base de datos si la entidad se confirmara en ese instante. Un control no puede mostrar un valor que la fila no tiene.

Esto extiende `code_conventions.md` §7.14 ("Defaults mostrados en la interfaz", decisión 2026-09-11) de los defaults al estado completo del formulario: §7.14 obliga a que un default visible esté ya persistido; esta sección obliga además a que **ningún** estado visible mienta sobre la fila, tenga o no un default detrás.

Consecuencias:

- **Un campo de tres estados se pinta con un control de tres estados.** Una columna `BOOLEAN` nullable donde `NULL` significa "sin dato" no puede pintarse como un checkbox de dos posiciones: un checkbox vacío se lee como `False`, y `False` ("no estaba pesado") no es lo mismo que "no lo sé". El caso de referencia son `strictly_weighed` y `macros_quality` de `portion_detail` (decisión 2026-09-18): nacen en `NULL`, el control cicla `NULL → True → False → NULL` a cada pulsación, y el estado sin dato se marca junto al control con un guion `–` pequeño para distinguirlo a simple vista de `False`.
- **Un valor que el usuario no ha introducido no se pinta como introducido.** Si no hay valor fiable, el control muestra un estado "sin elegir" explícito (§7.14), no el primer valor del enum ni un cero de relleno.
- **Un cálculo que la interfaz muestra pero no persiste debe decir que no se persiste**, o no mostrarse. Mostrar un número que parece guardado y no lo está es el mismo engaño con otra forma.
- La regla aplica igual al estado que se muestra **después** de una acción: si un refresco parcial (§9.5 de `code_conventions.md`) repinta una tarjeta, lo repintado tiene que ser lo que hay en la fila, no lo que el cliente supone que quedó.
