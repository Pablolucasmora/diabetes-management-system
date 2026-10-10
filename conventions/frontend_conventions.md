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
- **Ningún campo amplía la pantalla al enfocarlo** (decisión 2026-10-10). iOS hace zoom al enfocar un campo con letra menor de 16 px (`text-sm` son 14 px) y no lo deshace. En vez de subir todos los campos a 16 px, `static/js/browser_tweaks.js` añade `maximum-scale=1` al viewport solo en iOS. iOS sigue dejando hacer zoom con dos dedos, porque ignora ese límite para el gesto del usuario. En Android no se añade: allí no hay zoom al enfocar, y el límite sí bloquearía el zoom con dos dedos. Toda página con su propio `<head>` carga ese script, también las de acceso.

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
- **Qué hace un botón de vuelta** (decisión 2026-10-10). "Back" significa "la página de la que vengo", así que **retrocede en el historial** y nunca abre la página como una entrada nueva. Abrir el detalle como entrada nueva desde la edición hacía que las dos páginas se devolvieran la una a la otra (editar → Back → detalle → Back → editar).
  - Todos los botones de vuelta usan `back_js(<página padre>)` (`components/navigation.py`), que llama a `dbBack` (`static/js/navigation.js`). No se escribe `history.back()` ni un `hx_get` con `hx_push_url` en un botón de vuelta.
  - Si no hay una página de la web detrás, `dbBack` abre la **página padre** y sustituye la entrada actual, para que no se pueda volver a ella. Pasa cuando la página se abrió directamente o tras una recarga completa, como el `HX-Redirect` después de guardar. Padres: el detalle de un alimento para su edición, `Food` para el detalle, la creación y el escáner, y `Settings` para sus subpáginas.
  - Para saber si hay página de la web detrás, cada entrada que añade htmx guarda en `history.state` cuántas hay (`dbDepth`). `history.length` no sirve, porque cuenta también otros sitios y las páginas de delante.
  - `#main_content` lleva `hx-history-elt`. La copia que htmx guarda al salir de una página y la petición que hace si al volver no la encuentra usan ese elemento, así que una página restaurada es el mismo fragmento que devuelven las rutas.
  - `dbBack` también pone el scroll arriba, como pide esta sección.
- **Excepción**: una navegación concreta puede conservar la posición de scroll (o aterrizar en otro punto) **solo si el usuario lo pide explícitamente para ese caso**. Cuando eso ocurra, se documenta aquí el caso y el motivo, siguiendo el procedimiento de "Convenciones faltantes" de `CLAUDE.md`. No es una excepción que pueda decidirse componente a componente.
- No se consideran cambio de página, y por tanto **no** resetean el scroll, los refrescos parciales que reemplazan solo un bloque de la página actual sin cambiar de pantalla (por ejemplo `hx_target="#food-list"` al escribir en un buscador, o el re-render de una fila tras editarla).

## 6. La interfaz muestra exactamente lo que se guardaría

**Regla general** (decisión 2026-09-18): lo que un control muestra tiene que ser **exactamente** lo que se guardaría en la base de datos si la entidad se confirmara en ese instante. Un control no puede mostrar un valor que la fila no tiene.

Esto extiende `code_conventions.md` §7.14 ("Defaults mostrados en la interfaz", decisión 2026-09-11) de los defaults al estado completo del formulario: §7.14 obliga a que un default visible esté ya persistido; esta sección obliga además a que **ningún** estado visible mienta sobre la fila, tenga o no un default detrás.

Consecuencias:

- **Un campo de tres estados se pinta con un control de tres estados.** Una columna `BOOLEAN` nullable donde `NULL` significa "sin dato" no puede pintarse como un checkbox de dos posiciones: un checkbox vacío se lee como `False`, y `False` ("no estaba pesado") no es lo mismo que "no lo sé". El caso de referencia es `strictly_weighed` de `portion_detail` (decisión 2026-09-18; `macros_quality` lo fue hasta el 2026-10-09, cuando pasó a ser un dato del alimento): nace en `NULL`, el control cicla `NULL → True → False → NULL` a cada pulsación, y el estado sin dato se marca junto al control con un guion `–` pequeño para distinguirlo a simple vista de `False`.
- **Un valor que el usuario no ha introducido no se pinta como introducido.** Si no hay valor fiable, el control muestra un estado "sin elegir" explícito (§7.14), no el primer valor del enum ni un cero de relleno.
- **Un cálculo que la interfaz muestra pero no persiste debe decir que no se persiste**, o no mostrarse. Mostrar un número que parece guardado y no lo está es el mismo engaño con otra forma.
- La regla aplica igual al estado que se muestra **después** de una acción: si un refresco parcial (§9.5 de `code_conventions.md`) repinta una tarjeta, lo repintado tiene que ser lo que hay en la fila, no lo que el cliente supone que quedó.

## 7. Platos dentro de un evento (decisión 2026-09-19)

Esta sección describe cómo se presenta en la interfaz la subdivisión de un evento en tandas (platos). El modelo de datos, la herencia del offset y la regla del nombre derivado están en `measurement_conventions.md` §4.6; aquí solo se fija lo visual y el flujo.

Principio rector: **la funcionalidad no debe notarse cuando no se usa**. Una comida de un solo plato tiene que verse y manejarse exactamente igual que antes de existir las tandas, sin un click de más. Excepción: desde el 2026-10-10 la cabecera de tanda se muestra también con un solo plato (§7.2), para que el offset común esté siempre en el mismo sitio.

### 7.1 La sección se llama `Plates`

Dentro de la tarjeta del evento, el bloque que antes se titulaba `Ingredients` pasa a titularse **`Plates`**, y en vez de una lista plana de filas contiene un bloque por tanda. Orden de la tarjeta, de arriba abajo:

```text
EventHeader (nombre + borrar; hora, fecha y tipo de comida en píldoras)
MacrosSummary
Plates
  ┌ cabecera de tanda ──────────────────────────┐
  │ Arroz, Pechuga                            🗑 │
  │ Offset [ +0 ] min [Apply all]                │
  │   IngredientRow                              │
  │   IngredientRow                              │
  └──────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────┐
  │ Yogur                                     🗑 │
  │ Offset [ +45 ] min [Apply all]               │
  │   IngredientRow                              │
  └──────────────────────────────────────────────┘
[ + Add plate ]
Before you confirm: Eating out | Insulin (+ zona) | NotesSection
ConfirmSection (Eaten + Confirm meal)
```

Cada tanda es un bloque visualmente separado, no un simple texto entre filas: al leer la tarjeta tiene que verse de un vistazo dónde empieza y acaba cada plato.

**Orden y fila de ingrediente** (decisión 2026-10-10, rediseño del carrito). La tarjeta se lee de arriba abajo en el orden en que se usa: qué comida es, qué lleva, lo que importa antes de comer y la confirmación. Por eso `Eating out` e `Insulin` bajan de la cabecera a un bloque *Before you confirm*, junto a las notas, y borrar la comida pasa a la cabecera, al lado del nombre.

Cada `IngredientRow` muestra el nombre, una línea con la preparación (`raw · fridge · +15 min`, o `Preparation not set` si no hay ninguna), la cantidad con su unidad y la casilla `Strictly weighted`, que se cambia a menudo y por eso queda a la vista. Todo lo demás está en el pop-up **`Adjust`** de esa fila (`IngredientSettingsModal`): la preparación (`cooking`, `final_state`, `conservation`), `Weighed cooked`, el offset propio del ingrediente y el selector `Move` (§7.5). El pop-up es el sitio para corregir desde el carrito una preparación mal puesta u olvidada.

- La preparación se guarda con un botón (`Save preparation`), con los tres campos juntos. Un campo en `Not set` se guarda como `NULL` (§6). Los tres son parte de la clave única, así que guardar puede fusionar la fila con otra de la misma tanda (`measurement_conventions.md` §4.6.4), y por eso se repinta la tarjeta entera.
- Al abrirse, el pop-up pone el foco en su propia tarjeta y no en el primer campo: en el móvil, un selector con el foco abre su lista solo (`components/modal.py`).
- Los demás controles del pop-up se guardan solos al cambiar, como antes. Cuando el cambio repinta la tarjeta, el pop-up se vuelve a abrir (`static/js/cart_units.js`). No se reabre si se estaba cerrando, ni si su fila ha desaparecido por una fusión o un movimiento.

Las tandas se pintan en el orden que fija `measurement_conventions.md` §4.6.1 (`offset_minutes NULLS LAST, id`), no en orden de creación.

### 7.2 Cabecera de tanda: cuándo se muestra

La cabecera se muestra **siempre**, también con una sola tanda sin nombre (decisión 2026-10-10; sustituye al criterio del 2026-09-19). Así el offset común de la tanda y su `Apply all` están siempre en el mismo sitio, y la comida de un solo plato se maneja igual que la de varios.

Hasta el 2026-10-10 la cabecera solo se mostraba con dos o más tandas o con una tanda con nombre propio; con una sola tanda sin nombre se ocultaba y `Apply all` bajaba a cada fila. Se cambió al rediseñar el carrito: tener `Apply all` en dos sitios distintos según el caso confundía más que el espacio que ahorraba.

**Lo que sí se pinta siempre** es el marco de la sección: el título `Plates` y el botón `+ Add plate` (decisión 2026-09-19, confirmada al probarlo). La versión inicial de esta sección decía que con una sola tanda no se pintaría "nada de tandas"; al verlo en uso se prefirió mantener el marco visible, porque deja el acceso a crear una segunda tanda siempre a mano y no estorba. Lo condicional es la cabecera, no la sección.

### 7.3 Contenido de la cabecera

De izquierda a derecha: **título**, **offset de la tanda**, **`Apply all`**, y las acciones de editar nombre y borrar tanda.

- El **título** es el nombre de la tanda (propio o derivado, §4.6.3) y se edita igual que el nombre del evento, con el mismo control.
- El **offset de la tanda** es un input numérico editable en la propia cabecera. Es el valor que heredarán los alimentos que se añadan después a esa tanda.
- **`Apply all`** propaga ese offset a **todas las porciones de la tanda**. Existe porque cambiar el offset de la tanda no reescribe sus filas (§4.6.2): es la acción explícita para decir "esta tanda entera se comió 15 minutos más tarde". Va destacado con color, junto al input de offset.
- **Borrar tanda** está bloqueado mientras tenga ingredientes (§4.6.5); la interfaz pide moverlos o borrarlos antes, no los arrastra a otra tanda por su cuenta.

### 7.4 `Apply all`

`Apply all` está **solo en la cabecera de la tanda**, junto a su offset, y nunca en las filas: con muchos ingredientes, un botón por fila satura la interfaz haciendo exactamente lo mismo. Como la cabecera se muestra siempre (§7.2), no hay ningún caso en que tenga que bajar a las filas. Cada ingrediente conserva su propio offset en el pop-up `Adjust` (§7.1), sin `Apply all`.

### 7.5 Mover un ingrediente de tanda

Cada `IngredientRow` lleva un control **`Move`** en su pop-up `Adjust` (§7.1): un selector con las tandas del evento más la opción `+ New plate`. Al elegir una tanda, la fila se mueve (`UPDATE plate_id`); al elegir `+ New plate`, se crea la tanda y la fila se mueve a ella. Mover no cambia el `offset_minutes` de la fila (§4.6.5).

### 7.6 `+ Add plate`

Botón **debajo de la última tanda y encima del bloque *Before you confirm* (`NotesSection`) y de `Confirm meal`**, a ancho completo, para que se lea como acción del evento y no de una tanda concreta.

### 7.7 Selector de tanda al añadir un alimento

En la pantalla de añadir alimento, **junto al selector de comida (meal selector) va un segundo selector: el de tanda**. Lista las tandas del evento por su nombre más la opción `+ New plate`, que crea la tanda en el momento y la deja seleccionada.

- Viene preseleccionada **la tanda de la última porción añadida al evento**, no la primera: montando el segundo plato se añaden varios alimentos seguidos al mismo. Si ninguna tanda tiene ingredientes todavía, la creada más recientemente.
- **No hay una opción de "tanda por defecto"**: el selector siempre muestra una tanda concreta seleccionada. Una opción genérica obligaría al usuario a adivinar dónde va a caer el alimento, que es justo lo que §6 prohíbe. El criterio de preselección es **el mismo** que aplica `ensure_default_plate` cuando la petición llega sin `plate_id`, de modo que lo mostrado y lo que ocurre coinciden.
- El alimento entra con el `offset_minutes` de esa tanda ya puesto (§4.6.2). En el flujo normal no se toca ningún offset.
- **Se muestra siempre que el evento tenga al menos una tanda**, aunque sea una sola y sin nombre (decisión 2026-09-19, corrige el criterio inicial de ocultarlo en ese caso): con una sola tanda sigue siendo el único sitio desde el que mandar el alimento a una tanda nueva. Solo queda vacío cuando no hay evento del que listar tandas —ninguno seleccionado, `New Meal`, o un evento que ya no está en el carrito—.
- **Se pinta ya en la carga de la página**, con las tandas del evento que el selector de comida muestra seleccionado, y se repinta al cambiar de comida. Si solo se rellenara al cambiar de comida, el selector estaría vacío justo en el caso más común: entrar y añadir un alimento a la comida que ya venía elegida.
- El selector viaja en el `hx-include` de los botones de añadir, junto al de comida: un alimento tiene que saber a qué tanda va, no solo a qué evento. Si no se está mostrando, la petición sale sin `plate_id` y eso significa exactamente "la tanda por defecto".

### 7.8 Agrupación de filas iguales

La agrupación visual de porciones del mismo alimento (`group_portions`) se hace **dentro de cada
tanda** y **por forma de preparación y de pesada**, con la misma clave que la unicidad de §4.6.4
de `measurement_conventions.md` (`cooking`, `conservation`, `final_state`, `is_cooked_weight`):
agrupar ignorándola colapsaría en una fila los 100 g de arroz hervido y los 50 g de arroz frito,
y editar la cantidad los consolidaría en uno solo.
Cuando una tanda tiene **dos o más filas del mismo alimento**, cada una marca en pequeño, junto a
su nombre, **los valores que difieren** de la otra (solo esos, no todos siempre), para que se
entienda por qué están separadas. La diferencia de pesada se marca como `Weighed: raw` /
`Weighed: cooked`. Como la casilla `Cooked weight` es parte de la clave, al pulsarla en el
carrito se repinta la tarjeta entera, no solo el resumen de macros: puede fusionar dos filas o
cambiar las marcas de diferencia.

### 7.9 Ancho en móvil

La tarjeta del evento mide `w-[90vw]` en móvil (~325 px en un teléfono de 360 px, ~350 px en uno de 390 px; antes `w-xs`, 320 px fijos, que dejaba márgenes laterales excesivos y el selector de unidad se salía), así que la cabecera de tanda es el elemento con más riesgo de desbordar. Reglas:

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

Toda la interfaz de la web se escribe **en inglés** (`Plates`, `Apply all`, `Move`, `+ Add plate`, `+ New plate`): textos, etiquetas, placeholders, mensajes de validación, mensajes públicos de error (`errors.py`, `error_conventions.md` §2), avisos del cliente (`app_toast.js`) y las páginas de acceso. El atributo `lang` de las páginas es `en`. Lo que introduce el usuario no se traduce: el nombre derivado de una tanda sale de los nombres de los alimentos, que están en el idioma en que se guardaron, y los alias del parser de macros ("hidratos", "azúcar") son datos de entrada, no interfaz (decisión 2026-10-09).

Queda **pendiente de decisión** la internacionalización de la web (español/inglés a elección del usuario): no existe convención de i18n, los literales están incrustados en los componentes, y la parte cara no es traducir la interfaz sino decidir qué pasa con el contenido (nombres del catálogo, métodos de cocción, tipos de comida). Escribir los literales nuevos en inglés no cierra ninguna puerta a esa decisión.

## 8. Superficies, contraste y colores

Decisión 2026-10-10 (rediseño de la interfaz, rama `feat/ui-refresh`). La web conserva su identidad: tonos cálidos, esquinas redondeadas, el logo y la isla de navegación inferior. Las superficies son de **cristal líquido** (vidrio esmerilado translúcido, como en iOS) sobre un fondo beige muy claro con manchas de color suaves. Todo se define una sola vez en `static/css/input.css`.

**Colores del tema**

| Token | Uso |
|---|---|
| `page` (`#fbf8f3`) | fondo base de la página (beige muy claro) |
| `wash-peach`, `wash-blue`, `wash-green`, `wash-sun` | manchas de color del fondo (`body::before`) |
| `surface` (`#ffffff`) | superficies sólidas: paneles desplegables y modales |
| `control` (`#f7f2ea`) | fondo suave de elementos no acristalados (etiquetas, hover) |
| `line` (`#e9e0d2`) | borde de los campos, filtros y separadores |
| `line-soft` (`#efe8dd`) | borde suave y elemento activo de la navegación |
| `muted` (`#8a7d6b`) | etiquetas de sección (`web_section_label`) |
| `ink` (`#2b2622`) | acción principal (`web_button_primary`) y botón de confirmar de los pop-ups |
| `danger` (`#b91c1c`) | botón de confirmar de los pop-ups que borran o archivan |

**Clases**

- `web_glass` (utilidad): fondo blanco translúcido, desenfoque y saturación del fondo (`backdrop-filter`), borde blanco, brillo interior y reflejo diagonal. La usan `web_container` (tarjetas), `web_button` (botones), la barra inferior, el logo, el botón del carrito y la cabecera de Food.
- `web_glass_strong` (utilidad): el mismo cristal, más opaco y con más desenfoque. Es para barras con controles que quedan encima de contenido que se desplaza, como la cabecera de Food, para que lo que pasa por debajo no dificulte la lectura de los campos.
- `web_button_primary`: acción principal, sólida en `ink` y sin cristal. Como mucho hay una por pantalla.
- Los campos de texto (`web_input`) son blancos y sólidos, para que se lean bien.

**Reglas**

- Un componente usa los tokens y las clases, nunca el hexadecimal. Para añadir un color hay que acordarlo antes.
- Los paneles desplegables y los modales son sólidos (`surface`) y no contienen elementos acristalados, porque dentro de un panel blanco el cristal no se distingue. Sus opciones usan `control` con borde `line`.
- **No se usa `filter` (`blur()`, etc.) en ningún elemento** (decisión 2026-10-10). Safari en móvil y en ordenador, y a veces Chrome, pintan costuras de color (una línea fucsia) en los bordes de las capas desenfocadas que están dentro del cristal. Para desenfocar lo que hay detrás de algo abierto se usa **una sola capa fija con `backdrop-filter`** entre el contenido y lo abierto. Por ejemplo, detrás de los menús de la cabecera de Food está `#food_menu_scrim` (`food_main.py`, `food_quick_create.js`). Mientras esa capa está visible, la cabecera desactiva su propio cristal, para que no haya un `backdrop-filter` dentro de otro y para que la capa fija cubra la pantalla y no solo la cabecera. Tampoco se usan trucos de capa (`translateZ(0)`, `backface-visibility`, `isolation`) para tapar costuras: no las arreglan y esconden la causa.
- No se anida cristal dentro de cristal: los botones que van dentro de una superficie acristalada, como los del rayo y el "+" de la cabecera de Food, son sólidos (`surface`). Safari pinta costuras de color con un `backdrop-filter` dentro de otro.
- Cada superficie de cristal crea su propio contexto de apilamiento, así que una lista desplegable dentro de ella queda por debajo de la superficie siguiente aunque tenga un `z-index` alto. Mientras la lista está abierta, `static/js/dropdown_layer.js` sube todos los antepasados que crean contexto de apilamiento. No hace falta marcar nada en el componente. Los que ya tienen un `z-index` propio, como la cabecera fija o la isla de navegación, no se tocan.
- Por el mismo motivo, un elemento `fixed` dentro de una superficie de cristal se coloca respecto a esa superficie y no respecto a la pantalla. Por eso los pop-ups son un `<dialog>` abierto con `showModal()`, que el navegador pinta por encima de toda la página. El fondo oscurecido y desenfocado cubre así la pantalla entera. Se construyen siempre con `ModalLayer` / `ConfirmActionModal` y se abren y cierran con `open_modal_js` / `close_modal_js` desde Python, o con `dbOpenModal` / `dbCloseModal` desde JavaScript (`components/modal.py`, `static/js/modal.js`). Todos los pop-ups tienen el mismo diseño: el mismo fondo oscurecido y desenfocado, la misma tarjeta sólida y los mismos botones. Solo cambia el color del botón de confirmar: `modal_confirm_button(danger=True)` es rojo (`danger`) en los que borran o archivan, y en el resto es `ink`. La acción secundaria (No, Done) es `modal_secondary_button`. No se escriben colores ni clases de botón a mano dentro de un pop-up.
- Un elemento acristalado no lleva utilidades `shadow-*`, `bg-*` ni `border-*` que pisen el cristal.
- El fondo de color está en una capa fija (`body::before`), no en `background-attachment: fixed`, que Safari de iOS ignora. Por eso `body` es transparente y el color base va en `html`.
- El color de fiabilidad de los macros (`macro_color`, de verde a rojo) es un dato, no decoración, y no se sustituye por los colores de la paleta.
- Rendimiento: el desenfoque es caro. Si una lista larga va lenta en móvil, la primera medida es quitar el cristal de sus tarjetas, no de los elementos flotantes.

## 9. Estructura de las páginas

Decisión 2026-10-10 (rediseño de la interfaz, rama `feat/ui-refresh`). Cómo se montan las páginas, para que todas se lean igual. Los colores y superficies están en §8 y el movimiento en §10.

### 9.1 Páginas de crear y editar (alimento, plato, receta, añadido rápido)

Se construyen con los bloques de `components/food/foods.py`. No se monta un formulario a mano.

- **Cabecera** (`_form_header`). A la izquierda, "‹ Back" (§5). A la derecha, qué se hace, como etiqueta de sección (`NEW FOOD`, `EDIT DISH`…). Debajo, el título. La cabecera no es una tarjeta.
- **El nombre es el título** (`_name_title_input`). Se escribe y se edita en el propio título, en negrita y sin recuadro: parece texto y se edita al pulsarlo. Vacío, muestra en gris qué se espera (`Name of the food`). No hay un campo "Name" aparte.
- **Secciones** (`_form_section`). Cada una es una tarjeta con un título y sus campos en rejilla, en vez de una tarjeta por campo. En las páginas de crear, las secciones obligatorias van numeradas (`① What is it?`, `② Nutrition`). Así el usuario ve cuántos pasos tiene el formulario.
- **Lo que casi nunca hace falta va plegado** (`_optional_section`, un `<details>`): *More details*, con subgrupos (`_form_subgroup`) y una línea que resume qué hay dentro. Empieza cerrado. Se abre solo cuando ya trae datos, por ejemplo los que rellena el escáner. Es lo que evita que un formulario abrume.
- **Al final**, `Favorite` en su propia fila (`_favorite_row`) y una única acción principal a todo el ancho (`_form_submit`, `web_button_primary`: `Create food`, `Save`, `Add to meal`…).
- Las páginas de editar siguen el mismo esquema, con las secciones del alimento en vez de pasos numerados.

### 9.2 Inicio

Arriba, el saludo con el nombre de usuario (`Hi <usuario>`). Debajo, en este orden: la comida en curso (*Current meal*, que abre el carrito), las formas de añadir comida y la inyección.

### 9.3 Food

- La cabecera es fija arriba (`sticky`) y usa `web_glass_strong` (§8). Lleva el menú del rayo y el menú "+", el buscador, los filtros y el selector de comida (*Add to*). Mientras uno de sus menús está abierto, la capa `#food_menu_scrim` desenfoca el resto de la página (§8).
- Cada alimento de la lista es una tarjeta con el nombre, la marca u origen debajo y los carbohidratos por 100 g. Los propios llevan la etiqueta `Mine` y los archivados, `Archived`. Las listas van agrupadas bajo etiquetas de sección (`web_section_label`).

### 9.4 Detalle de un alimento, plato o receta

De arriba abajo: el nombre y sus datos, *Add to*, la cantidad (con *Advanced* para la preparación), `Strictly weighted` (§7.1, `measurement_conventions.md` §6.11), *Macros Summary* y *Details*. Entra bloque a bloque (§10).

### 9.5 Carrito

La página empieza con la etiqueta `CART`, el título *Planned meals* y una línea que explica qué hacer. Cada comida es una tarjeta con la estructura de §7.1.

## 10. Movimiento

Decisión 2026-10-10. Animaciones pequeñas para que los cambios se perciban continuos y no a saltos. Están todas en `static/css/input.css`, al final.

- Solo se animan `transform` y `opacity`, con duraciones de 150 a 260 ms. Ninguna animación retrasa una acción ni oculta información.
- Todo va dentro de `@media (prefers-reduced-motion: no-preference)`: si el sistema pide reducir movimiento, no hay animaciones.
- Una página nueva sube y aparece (`#main_content > *`). La animación usa `backwards`, así que al acabar no deja ningún `transform` puesto: un `transform` permanente convertiría el elemento en contenedor de sus hijos `fixed` (§8).
- La lista de alimentos entra tarjeta a tarjeta, con un retraso corto y con tope a partir de la sexta.
- La página de detalle de un alimento, un plato o una receta entra bloque a bloque, de arriba abajo, y las tarjetas de macros también (`data-stagger="true"`). Cada bloque se retrasa 40 ms respecto al anterior, con tope a partir del séptimo. El atributo sirve para cualquier página o rejilla que deba entrar así.
- Lo que muestra una sección plegable (`<details>`) aparece al abrirse.
- La tarjeta de un pop-up crece mientras aparece su fondo (`data-modal-card`, `components/modal.py`).
- Los botones (`web_button`) se hunden un poco al pulsarlos (`active:scale-95`). En móvil se quita el resaltado azul del toque.
- Los repintados parciales (una tarjeta del carrito tras cambiar un valor) **no** se animan: pasan a cada cambio y un parpadeo ahí molesta más de lo que ayuda.
