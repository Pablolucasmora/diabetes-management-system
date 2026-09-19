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

## 7. Platos dentro de un evento (decisión 2026-09-19)

Esta sección describe cómo se presenta en la interfaz la subdivisión de un evento en tandas (platos). El modelo de datos, la herencia del offset y la regla del nombre derivado están en `measurement_conventions.md` §4.6; aquí solo se fija lo visual y el flujo.

Principio rector: **la funcionalidad no debe notarse cuando no se usa**. Una comida de un solo plato tiene que verse y manejarse exactamente igual que antes de existir las tandas, sin un click de más.

### 7.1 La sección se llama `Plates`

Dentro de la tarjeta del evento, el bloque que antes se titulaba `Ingredients` pasa a titularse **`Plates`**, y en vez de una lista plana de filas contiene un bloque por tanda. Orden de la tarjeta, de arriba abajo:

```text
EventHeader (nombre, meal_time, tipo de comida...)
Eating out | Insulin | zone | Delete meal
MacrosSummary
Plates
  ┌ cabecera de tanda ──────────────────────────┐
  │ Arroz, Pechuga      [ +0 ] [Apply all]  ✎ 🗑 │
  │   IngredientRow                              │
  │   IngredientRow                              │
  └──────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────┐
  │ Yogur              [ +45 ] [Apply all]  ✎ 🗑 │
  │   IngredientRow                              │
  └──────────────────────────────────────────────┘
[ + Add plate ]
NotesSection
ConfirmSection (Confirm food)
```

Cada tanda es un bloque visualmente separado, no un simple texto entre filas: al leer la tarjeta tiene que verse de un vistazo dónde empieza y acaba cada plato. Las `IngredientRow` conservan el diseño que ya tienen.

Las tandas se pintan en el orden que fija `measurement_conventions.md` §4.6.1 (`offset_minutes NULLS LAST, id`), no en orden de creación.

### 7.2 Cabecera de tanda: cuándo se muestra

La cabecera se muestra si **hay dos o más tandas en el evento** o si **la tanda tiene nombre propio** (`name` no nulo). La segunda condición es necesaria: sin ella, nombrar la única tanda de un evento haría desaparecer ese nombre de la pantalla.

Cuando no se cumple ninguna de las dos —un evento con una sola tanda sin nombrar— **no se pintan ni la cabecera ni el botón de mover**, y `Apply all` baja a cada fila (§7.4). Las filas de ingrediente se ven como se veían antes de existir las tandas.

**Lo que sí se pinta siempre** es el marco de la sección: el título `Plates` y el botón `+ Add plate` (decisión 2026-09-19, confirmada al probarlo). La versión inicial de esta sección decía que con una sola tanda no se pintaría "nada de tandas"; al verlo en uso se prefirió mantener el marco visible, porque deja el acceso a crear una segunda tanda siempre a mano y no estorba. Lo condicional es la cabecera, no la sección.

### 7.3 Contenido de la cabecera

De izquierda a derecha: **título**, **offset de la tanda**, **`Apply all`**, y las acciones de editar nombre y borrar tanda.

- El **título** es el nombre de la tanda (propio o derivado, §4.6.3) y se edita igual que el nombre del evento, con el mismo control.
- El **offset de la tanda** es un input numérico editable en la propia cabecera. Es el valor que heredarán los alimentos que se añadan después a esa tanda.
- **`Apply all`** propaga ese offset a **todas las porciones de la tanda**. Existe porque cambiar el offset de la tanda no reescribe sus filas (§4.6.2): es la acción explícita para decir "esta tanda entera se comió 15 minutos más tarde". Va destacado con color, junto al input de offset.
- **Borrar tanda** está bloqueado mientras tenga ingredientes (§4.6.5); la interfaz pide moverlos o borrarlos antes, no los arrastra a otra tanda por su cuenta.

### 7.4 `Apply all` cuando no hay cabecera

`Apply all` está **en un solo sitio a la vez**, según si la cabecera se está mostrando:

| Situación | Dónde está `Apply all` |
|---|---|
| Cabecera visible | En la cabecera, junto al offset de la tanda |
| Cabecera oculta (una sola tanda sin nombre) | En cada `IngredientRow`, junto a su input de offset |

Nunca en los dos sitios, para no duplicar el mismo control en la misma pantalla. Se eligió la cabecera como sitio principal —y no una copia en cada fila— porque con muchos ingredientes un botón por fila satura la interfaz haciendo exactamente lo mismo.

Pulsado **desde una fila**, `Apply all` hace las dos cosas a la vez: escribe el offset de esa fila como `offset_minutes` de la tanda (para que lo hereden los alimentos que se añadan después) y lo propaga a todas las porciones de la tanda. Así el comportamiento es el mismo se pulse donde se pulse, y el caso de una sola tanda no necesita una excepción en el modelo: la tanda guarda su offset igual que las demás, simplemente no se ve.

### 7.5 Mover un ingrediente de tanda

Cada `IngredientRow` lleva un control **`Move`** cuando la cabecera está visible: un selector con las tandas del evento más la opción `+ New plate`. Al elegir una tanda, la fila se mueve (`UPDATE plate_id`); al elegir `+ New plate`, se crea la tanda y la fila se mueve a ella. Mover no cambia el `offset_minutes` de la fila (§4.6.5).

### 7.6 `+ Add plate`

Botón **debajo de la última tanda y encima de `NotesSection`/`Confirm food`**, a ancho completo, para que se lea como acción del evento y no de una tanda concreta.

### 7.7 Selector de tanda al añadir un alimento

En la pantalla de añadir alimento, **junto al selector de comida (meal selector) va un segundo selector: el de tanda**. Lista las tandas del evento por su nombre más la opción `+ New plate`, que crea la tanda en el momento y la deja seleccionada.

- Viene preseleccionada **la tanda de la última porción añadida al evento**, no la primera: montando el segundo plato se añaden varios alimentos seguidos al mismo. Si ninguna tanda tiene ingredientes todavía, la creada más recientemente.
- **No hay una opción de "tanda por defecto"**: el selector siempre muestra una tanda concreta seleccionada. Una opción genérica obligaría al usuario a adivinar dónde va a caer el alimento, que es justo lo que §6 prohíbe. El criterio de preselección es **el mismo** que aplica `ensure_default_plate` cuando la petición llega sin `plate_id`, de modo que lo mostrado y lo que ocurre coinciden.
- El alimento entra con el `offset_minutes` de esa tanda ya puesto (§4.6.2). En el flujo normal no se toca ningún offset.
- **Se muestra siempre que el evento tenga al menos una tanda**, aunque sea una sola y sin nombre (decisión 2026-09-19, corrige el criterio inicial de ocultarlo en ese caso): con una sola tanda sigue siendo el único sitio desde el que mandar el alimento a una tanda nueva. Solo queda vacío cuando no hay evento del que listar tandas —ninguno seleccionado, `New Meal`, o un evento que ya no está en el carrito—.
- **Se pinta ya en la carga de la página**, con las tandas del evento que el selector de comida muestra seleccionado, y se repinta al cambiar de comida. Si solo se rellenara al cambiar de comida, el selector estaría vacío justo en el caso más común: entrar y añadir un alimento a la comida que ya venía elegida.
- El selector viaja en el `hx-include` de los botones de añadir, junto al de comida: un alimento tiene que saber a qué tanda va, no solo a qué evento. Si no se está mostrando, la petición sale sin `plate_id` y eso significa exactamente "la tanda por defecto".

### 7.8 Agrupación de filas iguales

La agrupación visual de porciones del mismo alimento (`group_portions`) se hace **dentro de cada tanda**, no sobre todo el evento. Agrupar por evento colapsaría en una sola fila el mismo alimento presente en dos tandas, que es precisamente lo que la clave única de §4.6.4 permite distinguir.

### 7.9 Ancho en móvil

La tarjeta del evento mide `w-xs` (~320 px), así que la cabecera de tanda es el elemento con más riesgo de desbordar. Reglas:

- El **título** es el único elemento elástico: `min-w-0` + `truncate`. Si el nombre derivado es largo, se corta con puntos suspensivos; no empuja a los controles fuera de la tarjeta.
- El grupo **offset + `Apply all`** lleva `shrink-0`, con el input estrecho (signo y tres dígitos bastan por el rango `-300..300`) y el botón compacto.
- Si en el ancho más estrecho aun así no entra, la cabecera **envuelve a dos líneas**: título arriba; offset, `Apply all` y acciones abajo. Nunca scroll horizontal, nunca botones recortados.
- El input de offset es un control numérico y sigue §4: `inputmode="numeric"` (enteros, sin decimales).

Esto se verifica en el navegador en el ancho real, no por inspección del código.

### 7.10 Dos controles que refrescan la misma tarjeta deben sincronizarse

Cuando un botón y un input **refrescan el mismo target** y pueden dispararse casi a la vez, el botón lleva `hx-sync="#<id del input>:replace"`.

El caso que lo motiva (2026-09-19): escribir en el offset de la cabecera y pulsar `Apply all` sin salir antes del input dispara el `change` del input por el blur **y** el click del botón. Las dos peticiones reemplazan la tarjeta con `outerHTML`; el primer swap borra del DOM el elemento de la segunda, su `htmx:afterRequest` deja de llegar al listener global de `page_loading.js` —que cuenta peticiones pendientes para decidir cuándo ocultar el overlay— y **la capa de carga se queda encendida indefinidamente**. Con `replace`, la petición del botón cancela la del input y solo queda un swap.

La regla es general, no de las tandas: cualquier par de controles que compitan por el mismo `hx-target` con `outerHTML` tiene este fallo latente.

### 7.11 Un refresco parcial no mueve el scroll

Complementa §5 ("la regla no cubre los refrescos parciales"): además de no resetear el scroll al inicio, un refresco parcial debe **conservar** la posición exacta que tenía el usuario.

No basta con no tocarlo desde el código: al reemplazar la tarjeta entera con `outerHTML` desaparece del DOM el nodo que tenía el foco —un botón como `Apply all` no tiene `id` que htmx pueda restaurar— y el navegador puede reposicionar la página por su cuenta. Por eso el carrito guarda `window.scrollY` en `htmx:beforeSwap` y lo restaura en `htmx:afterSwap` y `htmx:afterSettle` para sus targets (`cart_card_event_*`, `cart_events_list`, `cart_body`), en `static/js/cart_units.js`.

### 7.12 Idioma

Toda la interfaz de esta funcionalidad se escribe **en inglés**, como el resto de la web (`Plates`, `Apply all`, `Move`, `+ Add plate`, `+ New plate`). El nombre derivado de una tanda es una excepción natural: sale de los nombres de los alimentos, que están en el idioma en que se guardaron.

Queda **pendiente de decisión** la internacionalización de la web (español/inglés a elección del usuario): no existe convención de i18n, los literales están incrustados en los componentes, y la parte cara no es traducir la interfaz sino decidir qué pasa con el contenido (nombres del catálogo, métodos de cocción, tipos de comida). Escribir los literales nuevos en inglés no cierra ninguna puerta a esa decisión.
