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
- **Un campo que admite decimales es `type="text"` con `inputmode="decimal"`, no `type="number"`** (decisión 2026-10-27). En los formularios de Food se construye con `_decimal_input` (`components/food/foods.py`). En un móvil configurado en español, el teclado decimal escribe una coma, y un `type="number"` la rechaza: el valor llega vacío o el navegador no deja enviar el formulario. El servidor acepta tanto `12,5` como `12.5` y comprueba el rango, así que en estos campos no se ponen `step`, `min` ni `max`, porque solo valen para `type="number"`. Los campos enteros (NOVA, Yuka) siguen siendo `type="number"` con `inputmode="numeric"`.
- **Excepción: un campo entero que admite negativos usa `inputmode="text"`** (decisión 2026-10-27, pedida por el usuario). El teclado numérico del iPhone no tiene la tecla "−", y así se puede escribir `-15` directamente. Hoy es el caso del offset del carrito (§7.9), que lleva además `pattern="-?[0-9]*"`.

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
  - Una página cuya página hija escribe datos que ella pinta no guarda copia: lleva `hx-history="false"`, y al volver se pide de nuevo. Por ahora, solo la ficha de receta, por su buscador de ingredientes (§6, §9.7; decisión 2026-11-06).
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

De izquierda a derecha: **título**, **offset de la tanda**, **`Apply all`**, **`Save as recipe`** (solo si la tanda tiene ingredientes, §7.13), y las acciones de editar nombre y borrar tanda.

- El **título** es el nombre de la tanda (propio o derivado, §4.6.3) y se edita igual que el nombre del evento, con el mismo control.
- El **offset de la tanda** es un input numérico editable en la propia cabecera. Es el valor que heredarán los alimentos que se añadan después a esa tanda. Se puede dejar vacío, igual que el de un ingrediente: significa offset desconocido (`measurement_conventions.md` §4.5). Un offset sin valor se muestra como campo vacío, nunca como `0`.
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

- **Con una receta** (decisión 2026-11-05). Una receta de una tanda se puede añadir a la tanda elegida. Una de varias tandas crea las suyas: en su ficha no se dibuja el selector de tanda y, desde la lista de Food, el paso previo avisa de que entra como tandas nuevas e ignora la elegida (§9.7).

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
- El input de offset es un entero que admite negativos: `type="text"` con `inputmode="text"` y `pattern="-?[0-9]*"`, por la excepción de §4 (decisión 2026-10-27; sustituye a `inputmode="numeric"`, con el que en el iPhone no se podía escribir el signo menos).

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

### 7.13 Guardar una tanda o una comida como receta

Decisión 2026-11-05; sustituye a la versión provisional del 2026-10-18.

**Dónde está**

- `Save as recipe` en la cabecera de cada tanda con ingredientes (§7.3). Una tanda vacía no tiene nada que guardar.
- `Save meal as recipe` en la tarjeta de la comida, debajo de `+ Add plate`, solo con dos o más tandas con ingredientes. Con una, el botón de la tanda ya guarda lo mismo.
- Los dos abren un pop-up con el nombre editable, ya relleno: el nombre visible de la tanda o, en la comida, el suyo o el de su primera tanda con ingredientes. Si el nombre está repetido, el pop-up se ha cerrado al pulsar y sale el aviso; al reabrirlo conserva lo escrito, para corregirlo.

**Qué se guarda** (`services/recipe.py`), en una transacción

- Una receta personal (`code_conventions.md` §11.4.1) en favoritos, con el `meal_type` del evento. Un rescate lo deja vacío, porque una receta no puede ser de rescate.
- La tanda da una receta de una tanda. La comida da una tanda por cada una con ingredientes, en el orden de `measurement_conventions.md` §4.6.1 y con su nombre, y omite las vacías.
- Cada porción con su cantidad, preparación, `strictly_weighed` e `is_cooked_weight`. El offset no se copia. La tanda y la comida no cambian.

**Cuándo no se guarda** (todas con su status por el canal de errores, `error_conventions.md` §7.1)

- Si hay un **añadido rápido**, no se guarda nada (`409`): no se reutiliza ni puede ser ingrediente (`code_conventions.md` §11.2.3).
- Si el usuario ya tiene una **receta personal con ese nombre** (`409`), un nombre vacío o demasiado largo (`422`), si no hay ingredientes (`409`) o si ya no existe (`404`).
- Si la comida ya está confirmada (`409`). El carrito solo muestra comidas `planned`.

**Al repetirlo**: la segunda petición choca con el nombre que tomó la primera y responde `409`.

**Después de guardar** el usuario se queda en el carrito: se cierra el pop-up y sale el aviso `Recipe saved`.

### 7.14 Confirmar: lo comido por tanda y las sobras (decisión 2026-11-07)

- Encima de `Confirm meal` hay un campo `Eaten` **por cada tanda con ingredientes**, con el nombre de la tanda si hay más de una. Vacío significa que se comió entera (`All of it`). Se escribe en **% por defecto** y dos pastillas eligen `%` o `g`; los gramos se comparan con el total de esa tanda (`measurement_conventions.md` §4.4).
- **Lo escrito en `Eaten` es un borrador**: se guarda en el navegador y vuelve tras recargar, hasta que la comida se confirma (`static/js/form_drafts.js`). Como el borrador se guarda por nombre de campo, el valor y la unidad llevan el id de su tanda (`ingested_value_<tanda>`, `ingested_unit_<tanda>`). Confirmado desde el pop-up de sobras, `mealConfirmed` lleva el id de la comida y `static/js/fridge.js` borra ese borrador.
- Si todas las tandas se comieron enteras, `Confirm meal` confirma directamente.
- Si alguna no, aparece antes el **pop-up de sobras** (`cart_leftovers_modal`), sin haber escrito nada. Por cada una de esas tandas muestra lo que queda de cada ingrediente y pide, con los mismos controles que `Keep part in fridge` (§7.15): dónde guardarlo (pastillas `Fridge`, por defecto, `Freezer` o `Don't keep`, que llevan el id de la tanda en el nombre), en cuántos tuppers iguales (de 1 a 10; vacío es uno) y con qué nombre (vacío, el derivado de sus ingredientes). Su `Confirm meal` confirma la comida y guarda los tuppers juntos (`measurement_conventions.md` §4.8.5); `Cancel` lo cierra sin confirmar.
- Un error del plan de sobras sale dentro del pop-up; uno de lo comido, en el aviso global (`error_conventions.md` §7.1), y el pop-up sigue abierto.
- **Borradores en general** (`static/js/form_drafts.js`): un formulario con `data-draft-key` guarda lo escrito en el navegador y lo recupera en los campos vacíos. Se descarta al guardar: con un `HX-Redirect` o, en un formulario que se queda en la página, con el evento que nombra `data-draft-done-event`. El token CSRF nunca va en un borrador.

### 7.15 Guardar parte de un ingrediente en la nevera (decisión 2026-11-07)

Para lo que se cocina de golpe (pasta, quinoa): se añade al carrito con lo pesado antes de cocinar y, ya cocinado, se reparte entre el plato y la nevera.

- En el pop-up `Adjust` de cada ingrediente de una comida planificada, la sección `Keep part in fridge`. Lo que se queda en el plato se dice de una de dos formas:
  - `In %`: el porcentaje del ingrediente que va al plato.
  - `Weighed`: el total cocinado (la olla) y lo que se pone en el plato, los dos pesados. La fracción es plato / total, exacta sin factores de cocción.
- La sección está **plegada**: se abre con su título, porque solo hace falta después de cocinar y abierta ocupa el pop-up.
- Debajo, dónde va el resto (`Fridge` por defecto o `Freezer`) y en cuántos tuppers iguales (vacío es uno). `Keep the rest` lo hace: la fila se queda con su parte, el resto va a tuppers nuevos (`measurement_conventions.md` §4.8.5), la tarjeta se repinta y aparece el aviso `Saved to the fridge`. Con `Weighed`, cada tupper lleva su parte del peso real.
- Los campos de `Weighed` solo se ven con esa opción marcada, con CSS (`group-has`), sin script.
- No se guarda como borrador: el reparto se decide en el momento (decisión del usuario, 2026-11-07).
- Es una acción en línea del carrito: un error sale en el aviso global (`code_conventions.md` §9.5).
- Borrar después la comida no deshace el reparto: lo guardado ya está en la nevera.

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
| `ice` (`rgb(176 214 226)`) | `wash-blue` opaco: junta de la tapa de los tuppers de la nevera y su escarcha (§9.8) |
| `ice-deep` (`rgb(140 196 224)`) | azul más frío del congelador: su tapa, su junta y su fondo (§9.8) |

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
- **Al final**, `Favorite` en su propia fila (`_favorite_row`), marcado por defecto en los formularios de alta, y una única acción principal a todo el ancho (`_form_submit`, `web_button_primary`: `Create food`, `Save`, `Add to meal`…).
- Las páginas de editar siguen el mismo esquema, con las secciones del alimento en vez de pasos numerados.

### 9.2 Inicio

Arriba, el saludo con el nombre de usuario (`Hi <usuario>`). Debajo, en este orden: la comida en curso (*Current meal*, que abre el carrito), las formas de añadir comida, la inyección y el rescate (`Log rescue`, §9.6). Entre las formas de añadir comida está `From fridge`, que abre Food en la píldora `Fridge` (§9.8), con la comida en curso elegida en *Add to* como siempre.

### 9.3 Food

- La cabecera es fija arriba (`sticky`) y usa `web_glass_strong` (§8). Lleva el botón del rayo, que abre el pop-up de rescate (§9.6), el menú "+", el buscador, los filtros y el selector de comida (*Add to*). Mientras el menú "+" está abierto, la capa `#food_menu_scrim` desenfoca el resto de la página (§8).
- **Filtros** (decisión 2026-11-06). Se ajustan con un botón negro dentro del buscador, a la derecha, que abre un pop-up (`ModalLayer`, §8, id `food_filters_modal`) con `Cancel` y `Confirm`, y `Reset` arriba a la derecha, que quita todos los filtros. Lo elegido es un borrador, también el `Reset`: solo `Confirm` lo aplica y refresca la lista; `Cancel` o pulsar fuera lo descartan. El botón solo aparece en las listas que tienen algo que filtrar y lleva una marca mientras hay un filtro activo, porque desde fuera del pop-up no se vería. Por ahora, solo `Recipes`, con el tipo de comida: una selección múltiple de píldoras, que busca entre todos los elegidos (`code_conventions.md` §11.7). Un filtro nuevo es un control en el pop-up y un campo oculto que incluyen las peticiones de la lista.
- El `+` de una receta abre el paso previo (§9.7).
- **Cinco píldoras**: `Search`, `Food`, `Recipes`, `Favs` y `Fridge` (decisión 2026-11-07: la nevera tiene píldora propia para que se llegue a ella de un toque, §9.8). En móvil van más juntas (`gap-1.5`) para que quepan las cinco. `/food?filter=fridge` abre la página en `Fridge`; otro valor es un `422`.
- Cada alimento de la lista es una tarjeta con el nombre, la marca u origen debajo y los carbohidratos por 100 g. Los propios llevan la etiqueta `Mine` y los archivados, `Archived`. Las listas van agrupadas bajo etiquetas de sección (`web_section_label`).
- Sin búsqueda, la lista muestra 15 resultados y carga la página siguiente al llegar al final. Con búsqueda muestra 8 y las páginas siguientes, también de 8, se piden con un botón `Load more`, pequeño y centrado, porque debajo está la sección de Open Food Facts (`measurement_conventions.md` §12.2) y la carga automática no dejaría llegar a ella. Debajo van `From Ciqual` y `From Open Food Facts`, con 8 resultados cada una y su propio `Load more` (`/food/list/external`).

#### 9.3.1 Menú de acciones de una fila (en prueba)

Decisión 2026-10-27, acordada con el usuario como prueba de diseño.

- **Gesto.** Mantener pulsada una fila de la lista de Food 500 ms sin mover el dedo abre un pop-up de acciones. Si el dedo se mueve más de 10 px, es un scroll y se cancela. En el ordenador, el clic derecho abre el mismo pop-up. Al soltar después de una pulsación larga no se abre el detalle. La estrella y el "+" de la fila mantienen su propio toque. La fila no permite seleccionar texto ni abre el menú nativo de iOS. A partir de 150 ms se hunde un poco (§10) y, al abrirse el pop-up, el móvil vibra brevemente si el navegador tiene la API de vibración (Android). En el iPhone no hay vibración: Safari no tiene esa API, y el truco del interruptor nativo oculto (`<input type="checkbox" switch>`) no da el toque cuando el pop-up se abre desde el temporizador de la pulsación larga (probado en iOS 27.2, 2026-10-27). El gesto está en `static/js/food_actions.js`.
- **Forma.** Es un pop-up (`ModalLayer`, §8, id `food_actions_modal`), no un panel anclado a la fila. Arriba muestra el nombre del alimento y, debajo, la marca, el origen o `Recipe`, con una × para cerrar. Debajo van las opciones como filas `control`. Su contenido se pide al servidor cada vez que se abre, y el pop-up se abre cuando ese contenido llega (como en §9.6). Las vistas interiores (recetas y confirmación de copia) sustituyen el cuerpo del pop-up y llevan "‹" para volver al menú. Al cambiar de vista se anima igual que el pop-up de rescate (§10).
- **Opciones.** Cada una aparece solo si el usuario tiene permiso, con el mismo criterio que el detalle (§9.4):
  - `Edit food` / `Edit manual` / `Edit recipe`: solo si es suyo y está activo. Abre la página de editar.
  - `Make a copy`: siempre, también en lo propio (decisión 2026-10-27, `code_conventions.md` §11.2.2). Pide la misma confirmación que el detalle, usa `POST /food/copy/...` y abre la edición de la copia.
  - `Add to recipe`: solo para alimentos y platos (`catalog`, `manual_intake`), porque una receta no puede ser ingrediente. Lista las recetas propias del usuario. Al elegir una, se añade con la cantidad inicial de siempre (una ración, o 100 g si no tiene) usando la ruta de añadir ingrediente que ya existe, que suma la cantidad solo si el alimento ya estaba en esa tanda con la misma preparación (`measurement_conventions.md` §4.7). Si la receta tiene dos o más tandas, una vista más pregunta a cuál (decisión 2026-11-05). El pop-up se cierra y aparece el aviso `Added to <receta>` (`dbShowAppNotice`).
  - `Save to fridge`: solo para alimentos y platos. Una vista con la cantidad, que empieza en una ración o en 100 g si no tiene, y dos botones, `To fridge` y `To freezer`, que crean un tupper nuevo (`measurement_conventions.md` §4.8.5). El pop-up se cierra y aparece el aviso `Saved to the fridge` o `Saved to the freezer` (decisión 2026-11-07).

**Respuestas HTMX**

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /food/actions/{entry_type}/{entry_id}` | `#food_actions_modal_body` | `innerHTML` | el menú | sin sesión: `401`; tipo desconocido: `422` (`code_conventions.md` §7.7); no visible: `404`. Todo por el canal de errores |
| `GET /food/actions/{entry_type}/{entry_id}/recipes` | `#food_actions_modal_body` | `innerHTML` | la lista de recetas propias | igual; `422` también para una receta, que no puede ser ingrediente |
| `GET /food/actions/{entry_type}/{entry_id}/copy` | `#food_actions_modal_body` | `innerHTML` | la confirmación | igual |

Todas exigen el header `HX-Request` (`403` si falta).

#### 9.3.2 Estrella de favorito de una fila

Pulsar la estrella activa el favorito y volver a pulsarla lo desactiva. Cada estrella manda en `hx-vals` el estado que pide (`favorite=true|false`), calculado en el servidor a partir de la fila guardada, así que repetir una petición nunca deshace la anterior. Mientras responde, el botón está deshabilitado. Su texto accesible dice lo que hará: `Add to favorites` o `Remove from favorites`.

Si el favorito es lo único que da acceso a un alimento o plato retenido (`code_conventions.md` §11.2.5), quitarlo pide confirmación en el pop-up de la fila (§9.3.1), y al confirmar se retira la tarjeta. Lo decide el servidor en el momento de la pulsación, no al pintar la lista. Sin esa condición se quita con un solo toque, y la tarjeta se queda con la estrella vacía.

**Respuestas HTMX** de `POST /food/favorite/{entry_type}/{entry_id}`, que exige el header `HX-Request` (`403` si falta):

| Caso | `hx-target` final | `hx-swap` final | Respuesta |
|---|---|---|---|
| Añadir o quitar, y sigue visible | la estrella | `outerHTML` | la estrella con el estado guardado |
| Quitar lo único que da acceso, sin `confirmed=true` | `#food_actions_modal_body` (`HX-Retarget`) | `innerHTML` (`HX-Reswap`) | la confirmación; no cambia nada |
| Quitar, y deja de ser visible | la tarjeta (`HX-Retarget`) | `outerHTML` (`HX-Reswap`) | vacía: la tarjeta desaparece |

Errores, por el canal común: sin sesión, `401`; tipo desconocido, `favorite` ausente, vacío o no válido, y `confirmed` no válido, `422`; añadir algo que no ve, `404`; añadir algo retenido, `409`. Repetir es un no-op: la misma estrella, o la misma respuesta vacía si ya no se ve. No lanza eventos `HX-Trigger` ni navega.

### 9.4 Detalle de un alimento, plato o receta

**Receta** (decisión 2026-11-05). De arriba abajo: el nombre, *Add to*, *Macros Summary*, *Details*, los ingredientes y las notas, con sus saltos de línea. No hay cantidad ni `To plate`: `Add to meal` abre el paso previo (§9.7). Quien no es propietario ve los ingredientes en filas de solo lectura y solo puede copiarla y añadirla. Un macro que ningún ingrediente conoce se pinta `—`, y si solo lo conocen algunos se pinta su suma con una línea que lo dice (`measurement_conventions.md` §6.9.4). Lo que cambia los ingredientes repinta también el resumen (§6).


De arriba abajo: el nombre y sus datos, *Add to*, la cantidad (con *Advanced* para la preparación), `Strictly weighted` (§7.1, `measurement_conventions.md` §6.11), *Macros Summary* y *Details*. Debajo, las acciones: `Edit` y `Log`; si el usuario no puede editarlo, `Make a copy` ocupa el sitio de `Edit`. Si puede editarlo, `Make a copy` va en su propia fila debajo, encima de `Publish` (decisión 2026-10-27). Copiar pide confirmación y abre la edición de la copia. Entra bloque a bloque (§10). En un alimento o plato propio y activo aparece además el botón `Rescue` (§9.6).

En un alimento o un plato, debajo de `Edit` y `Log food`, dos botones visibles, `Save to fridge` y `Save to freezer` (decisión 2026-11-07, que sustituye a ofrecerlos dentro de *Add to*, donde no se encontraban): guardan la cantidad de arriba entera en un tupper nuevo, con su preparación y pesada y sin plato (`measurement_conventions.md` §4.8.5). La página no cambia y aparece el aviso `Saved to the fridge` o `Saved to the freezer`. Una receta se guarda desde su paso previo (§9.7). Al registrar con `Log food`, si la cantidad cocinada es mayor que la del plato, la línea `Will be saved in fridge` dice lo que se guarda en un tupper de la nevera, y se guarda de verdad.

### 9.5 Carrito

La página empieza con la etiqueta `CART`, el título *Planned meals* y una línea que explica qué hacer. Cada comida es una tarjeta con la estructura de §7.1.

### 9.6 Rescate

Decisión 2026-10-11. Un rescate es lo que se toma para tratar una hipoglucemia. Se registra desde un pop-up y crea directamente una comida ya consumida.

**Dónde está**

- El botón del rayo de la cabecera de Food (§9.3) y el botón `Log rescue` de Inicio (§9.2) abren el mismo pop-up (`ModalLayer`, §8, id `rescue_modal`). No hay panel desplegable.
- El contenido del pop-up se pide al servidor cada vez que se abre (`GET /food/rescue/form`). Así la fecha y la hora son las de ese momento y el formulario sale vacío. La respuesta trae ya la lista inicial de alimentos, y `static/js/rescue.js` abre el pop-up cuando llega: se pinta completo, con una sola animación de entrada (§10), en vez de abrirse vacío y crecer por partes.

**Qué alimentos se ofrecen**

- Con el buscador vacío salen los alimentos de rescate: los que tienen la etiqueta de rescate y los que este usuario ya ha usado en comidas `rescue`, primero los usados más recientemente.
- Al escribir, los resultados **sustituyen** a los alimentos de rescate en el mismo sitio, y al vaciar el buscador vuelven los de rescate. La lista declara su propio `hx-target`: sin él heredaría el del formulario (`#rescue_form_error`) y los resultados aparecerían debajo. Enter en el buscador (la tecla Buscar del teclado del móvil) no envía el rescate: solo cierra el teclado.
- La búsqueda abarca todos los alimentos (`catalog`) y platos (`manual_intake`) que el usuario puede ver, con la misma regla de visibilidad que el resto de búsquedas, incluidos los archivados que conserva (`code_conventions.md` §11.2). Los de rescate van primero.
- Cada opción es una fila `control` compacta (§8) con el nombre y, debajo, la marca u origen y los hidratos del alimento (por ración si la tiene, si no por 100 g). La lista tiene una altura máxima con scroll propio. Sin alimentos de rescate, una línea explica que basta con buscar cualquiera y que los registrados aparecerán ahí.
- La etiqueta se identifica por la constante `RESCUE_TAG_NAME` de `domain/constants.py`, con el valor `rescate` que ya está guardado (un valor persistido no se renombra, `code_conventions.md` §4.2). Su nombre no se escribe a mano en el SQL.

**Líneas**

- Al elegir un alimento se añade su línea (nombre, cantidad, unidad y un botón para quitarla) y el buscador se oculta. `+ Add another food` lo vuelve a mostrar para añadir otra línea. Si se quitan todas, el buscador vuelve a aparecer.
- La línea la pinta el servidor (`GET /food/rescue/line/{entry_type}/{entry_id}`): el nombre con un botón para quitarla y, debajo, la cantidad con botones − y + y la unidad. Los botones − y + solo mueven el número en el navegador (1 ración, 10 g, 1 oz, 0,25 lb) y nunca lo bajan a 0. La unidad es un `<select>` de `AmountInputUnit` sin `%`: `portion` solo aparece si el alimento tiene ración, y entonces la línea nace con `1 portion`. Sin ración, nace en `g` y con la cantidad vacía.
- Se envían `amount_value` y `amount_unit` por línea. El servidor convierte a gramos con `amount_to_grams` y lee la ración del alimento en la base, nunca de un campo oculto (decisión 2026-09-22, `code_conventions.md` §7.13).
- No hay "% comido" ni "sobrante": no se guardan en ningún sitio (§6).
- **Elegir un alimento que ya está en la lista no añade otra línea: suma a la existente**, como el carrito. Si la línea está en raciones, suma 1 ración; si está en gramos y el alimento tiene ración, suma su peso en gramos. En oz, lb o sin ración no hay una cantidad fiable que sumar, y la línea solo se resalta para que el usuario la ajuste. Al guardar, el servidor fusiona igualmente las porciones repetidas (§4.6.4).
- **Ningún campo se enfoca solo** (ni al elegir un alimento, ni al quitarlo, ni al abrir el pop-up): en el móvil abriría el teclado sin que el usuario lo pida.
- No se guarda estado del pop-up en `localStorage`.

**Diseño**

- Compacto, para que quepa en la pantalla de un móvil: el título `Rescue` con una × para cerrar, el buscador, la lista, las líneas, la fecha y la hora en una fila sin etiqueta, y *Cancel* / *Log rescue* a todo el ancho. Sin textos de ayuda fijos.
- Nada sobresale de la tarjeta en el móvil. Un nombre de alimento largo ocupa como mucho dos líneas y después se corta con "…" (`line-clamp-2`, `break-words` para una palabra sin espacios). La fecha y la hora van en columnas `minmax(0, 1fr)` con `appearance-none` y el texto centrado, porque iOS da a esos controles nativos un ancho propio mayor que la columna (§3).

**Fecha y hora**

- Dos campos, `date` y `time`, rellenos con el momento de abrir el pop-up y editables. Se admite cualquier momento, también futuro, con el mismo criterio que las inyecciones (decisión 2026-09-06).

**Qué se guarda** (`POST /food/rescue/log`)

- Cada envío crea un evento nuevo, aunque haya un rescate reciente: `meal_type = rescue`, `insulin_dose = FALSE` (un rescate no lleva insulina y nunca crea una inyección automática), una sola tanda con offset 0 y una porción por línea. Si un alimento se repite con la misma preparación, se suman sus cantidades (`measurement_conventions.md` §4.6.4).
- El evento se crea en `planned` y se confirma al 100 % en la misma transacción, con la misma confirmación que usa el carrito (`services/intake_event.py`). Así calcula `ingested_amount` y `amount_confidence` con las mismas reglas que cualquier comida (`measurement_conventions.md` §6.9.1).
- Todo va en una transacción. Si una línea no es válida, no se guarda nada.

**Respuestas HTMX**

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /food/rescue/form` | `#rescue_modal_body` | `innerHTML` | el formulario, con la lista inicial de alimentos dentro | sin sesión: `401` por el canal de errores |
| `GET /food/rescue/options?q=` (solo al escribir en el buscador) | `#rescue_picker_results` | `innerHTML` | la lista de alimentos | — |
| `GET /food/rescue/line/{entry_type}/{entry_id}` | `#rescue_lines` | `beforeend` | una línea | `404` por el canal de errores (`error_conventions.md` §7.1) |
| `POST /food/rescue/log` | `#rescue_form_error` | `innerHTML` | cuerpo vacío y el evento `rescueRegistered` (`HX-Trigger`). `static/js/rescue.js` cierra el pop-up y muestra el aviso de éxito `Rescue registered` (`dbShowAppNotice`, `error_conventions.md` §7.1) | validación: `200` y el mensaje en `#rescue_form_error` (`code_conventions.md` §9.5). Sesión, alimento inexistente o conflicto: su status por el canal de errores |

Todas exigen el header `HX-Request` (`403` si falta).

**Marcar un alimento como rescate (provisional)**

- Mientras la interfaz de etiquetas siga oculta (`TAGS_UI_ENABLED = False`), el detalle de un alimento o plato (§9.4) muestra un botón `Rescue` de dos estados (`POST /food/rescue/mark/{entry_type}/{entry_id}`, `rescue=true|false`). Pone o quita **solo** la etiqueta `RESCUE_TAG_NAME` en `linked_tags` y no toca las demás. La respuesta vuelve a pintar el botón con lo que ha quedado guardado (§6).
- Solo aparece si el usuario puede editar el alimento: es suyo y no está archivado. Es el mismo permiso que hoy permite cambiar sus etiquetas. Solo existe para `catalog` y `manual_intake`, no para recetas. Un alimento de la biblioteca general o de otro usuario se usa una vez buscándolo, y desde entonces sale por el historial.
- La etiqueta es global: si se marca un alimento publicado, también aparece como rescate a los demás usuarios. Se acepta mientras dure la medida provisional.
- Cuando vuelva la interfaz de etiquetas, el botón se quita y la etiqueta se gestiona con el selector normal (`audit/deuda_pendiente.md`).

### 9.7 Recetas: paso previo, tandas e ingredientes

Decisión 2026-11-05. El modelo está en `measurement_conventions.md` §4.7 y el contrato en `code_conventions.md` §11.2.4.

**Paso previo al añadir a una comida**

- El `+` de la fila y `Add to meal` de la ficha abren el pop-up `recipe_add_modal`. Su contenido se pide al servidor (`GET /food/recipe/{id}/add/form`) con la comida y la tanda elegidas, y `static/js/recipe_add.js` lo abre cuando llega, como en el rescate (§9.6).
- Con `servings`, un campo `Servings` con `1`. Sin él, no aparece, pero el paso sigue, para ajustar la preparación.
- Una línea por ingrediente, con su cantidad por ración. Se despliega para cambiar `cooking`, `final_state` y `conservation`, ya rellenos con lo de la receta. Con varias tandas, agrupadas y con un aviso de que entran como tandas nuevas.
- `POST /add_recipe/{id}` recibe la comida, la tanda, las raciones y la preparación por ingrediente, nunca cantidades. Validación: `200` + fragmento en `#recipe_add_error`. Una comida o tanda que no existe, `404`; una comida ya confirmada o una receta sin ingredientes, `409`. Al terminar, el evento `recipeAdded` cierra el pop-up y muestra `Added to the meal`.
- Repetirlo añade la receta otra vez: es otra ración, no un duplicado (§9.6 de `code_conventions.md`). El botón se deshabilita durante la petición.
- Debajo, `Save to fridge` y `Save to freezer` guardan esas mismas raciones, con la preparación elegida, en un tupper nuevo con el nombre de la receta (decisión 2026-11-07, `measurement_conventions.md` §4.8.5). La comida y la tanda no se usan. El pop-up se cierra y aparece el aviso `Saved to the fridge` o `Saved to the freezer`.

**Tandas en la ficha**

- Con una tanda el concepto no se ve: solo `Add ingredient` y un `+ Add plate` discreto debajo, que no aparece hasta que la receta tiene una tanda. Es distinto del carrito, donde la cabecera sale siempre (§7.2), porque aquí no hay offset común que mostrar.
- Con dos o más, cada tanda lleva una cabecera con su nombre editable (vacío, el derivado), subir, bajar y borrar, y su propio `Add ingredient`. Cada ingrediente tiene un selector para moverlo de tanda.
- Borrar una tanda con ingredientes responde `409` y pide moverlos o borrarlos.
- Toda acción repinta el bloque `#recipe_ingredients_{id}` y, fuera de banda, el resumen.

**Por ingrediente**: cantidad, preparación y `Weighed cooked`, con el mismo criterio que el carrito (§7.4). `Strictly weighted` se ajusta en el carrito.

**Buscador de ingredientes** (`/food/recipe/{id}/ingredients/form`)

- Es el de Food sin isla, sin menú "+", sin selector de comida y sin menú de pulsación larga. Solo alimentos: nunca ofrece recetas. La isla se oculta con un `Style` dentro de la propia página, que desaparece con ella.
- Filtros `Food` y `Favs`, y la misma paginación de Food por bloques de 8, con `Load more`. Cada `+` añade a la tanda desde la que se entró, o a la última, y muestra `Added to <receta>`.
- Con búsqueda, en `Food`, salen también Ciqual y Open Food Facts (`measurement_conventions.md` §12). Al pulsar uno se abre su formulario precargado: al guardar, el alimento se añade a la receta y se vuelve al buscador. Nunca se crea un alimento sin revisarlo.

**Tipos de comida**: el formulario tiene el tipo principal (`Meal type`) y, en píldoras, los adicionales (`Also for`). El principal es el que toma una comida creada desde la receta; los adicionales solo sirven para encontrarla con el filtro (decisión 2026-11-06). Elegir adicionales sin principal da un error de validación.

**Notas**: texto libre del usuario, con una caja de 8 filas que no selecciona el texto al tocarla y hasta `RECIPE_NOTES_MAX_LENGTH` caracteres. Un borrador se descarta al guardar con éxito, para que no vuelva a rellenar un campo vaciado a propósito (en los tres formularios de alimentos).

### 9.8 Nevera (decisión 2026-11-07)

Píldora `Fridge` de Food (§9.3). Modelo y cantidades en `measurement_conventions.md` §4.8.

- **Arriba**, el selector de comida de la cabecera y, junto a él, el de tanda (§7.7): son el destino del `+` de cada tupper.
- **Dos secciones**, `Fridge` y debajo `Freezer` (`web_section_label`), con todos los tuppers abiertos, sin paginar ni buscador: nunca habrá muchos por usuario, y lo escrito en el buscador de la cabecera no filtra esta pestaña. Dentro de cada sección, por `expires_at`, el que caduca antes primero. Una sección sin tuppers dice `Empty.`.
- **Cada tupper es una tarjeta** con el nombre, su contenido con la cantidad guardada de cada ingrediente (para que se vea lo que queda tras sacar una parte), los días desde que entró y los que le quedan (`3 days in · 7 days left`) y el peso real, si se conoce. A la derecha, un botón que lo mueve al otro sitio, sin confirmación porque se deshace con el mismo botón, y el `+`, que abre el paso de sacar (abajo).
- **Caducado**: lleva la etiqueta `Expired` y la línea de días en `danger`, no un borde rojo, porque la tarjeta es de cristal (§8). Sus botones pasan a ser `Discard` y `Eat`. `Eat` es el `+` con 100 %.
- **Pulsación larga** (§9.3.1), en el mismo pop-up que las filas de alimentos: `Edit` y `Discard`. `Edit` es un formulario con el nombre, la fecha de caducidad y el peso real, que se guardan juntos (`code_conventions.md` §3.4). Un nombre vacío vuelve al derivado y un peso vacío, a sin pesar. Tirar pide confirmación, también desde el `Discard` de un caducado.
- **Sacar.** Una vista del pop-up de acciones: la cantidad en % (100 % por defecto) y, solo si el tupper tiene peso real, gramos (`measurement_conventions.md` §4.8.3). `Add to meal` lo añade a la comida y tanda elegidas en la cabecera, el pop-up se cierra, la lista se repinta y aparece el aviso `Added to your meal`. Si luego se borra la comida o el ingrediente en el carrito, vuelve al tupper (§4.8.6).
- **Vacío**: una línea que explica cómo se guarda un tupper (desde la página de un alimento o un plato).
- **Aspecto de nevera** (decisión 2026-11-07). La pestaña se distingue del resto con muy poco, todo en `static/css/input.css` y sin `filter` (§8):
  - **Escarcha**: una franja muy tenue de `wash-blue` en cada lateral de la pantalla, que se desvanece hacia el centro. Es una capa fija que solo existe mientras la lista de la nevera está en la página (`body:has([data-fridge-list])::after`), por debajo del contenido, como el fondo de color.
  - **Copos**: uno pequeño a cada lado del título `Fridge`, fuera de la columna de tarjetas, y otro delante de `Freezer`. Son SVG con `currentColor` en `ice` o `ice-deep`.
  - **Cada tupper es un tupper de cristal**: la tarjeta de cristal (`web_container`) es el cuerpo. Arriba lleva una tapa, una franja de `wash-blue` con una junta de `ice` debajo, y en el centro una pestaña de cierre translúcida que cae sobre el borde (`.fridge_tupper`, con pseudoelementos). No lleva cierres laterales ni etiqueta.
  - **Congelador**: su sección va dentro de un fondo suave de `ice-deep` con esquinas redondeadas (`.fridge_freezer`), que no es de cristal. Sus tuppers miden lo mismo que los de la nevera y el fondo crece a su alrededor con su margen, así que es algo más ancho que la columna. Sus tuppers usan `ice-deep` en la tapa y la junta.
  - Un tupper caducado no cambia de forma: se marca solo con la etiqueta `Expired` y la línea de días en `danger` (arriba).

## 10. Movimiento

Decisión 2026-10-10. Animaciones pequeñas para que los cambios se perciban continuos y no a saltos. Están todas en `static/css/input.css`, al final.

- Solo se animan `transform` y `opacity`, con duraciones de 150 a 260 ms. Ninguna animación retrasa una acción ni oculta información.
- Todo va dentro de `@media (prefers-reduced-motion: no-preference)`: si el sistema pide reducir movimiento, no hay animaciones.
- Una página nueva sube y aparece (`#main_content > *`). La animación usa `backwards`, así que al acabar no deja ningún `transform` puesto: un `transform` permanente convertiría el elemento en contenedor de sus hijos `fixed` (§8).
- La lista de alimentos entra tarjeta a tarjeta, con un retraso corto y con tope a partir de la sexta.
- La página de detalle de un alimento, un plato o una receta entra bloque a bloque, de arriba abajo, y las tarjetas de macros también (`data-stagger="true"`). Cada bloque se retrasa 40 ms respecto al anterior, con tope a partir del séptimo. El atributo sirve para cualquier página o rejilla que deba entrar así.
- Lo que muestra una sección plegable (`<details>`) aparece al abrirse.
- La tarjeta de un pop-up crece mientras aparece su fondo (`data-modal-card`, `components/modal.py`).
- En el pop-up de rescate (§9.6), al elegir un alimento las opciones se desvanecen y la línea nueva entra cuando ya han desaparecido, para que no se pisen. Al quitar una línea se desvanece, y las opciones y `+ Add another food` aparecen suavemente.
- **Excepción: la altura de la tarjeta del pop-up de rescate** (decisión 2026-10-11, pedida expresamente por el usuario para este caso). Cuando cambia su contenido (al elegir, sumar o quitar un alimento, al pulsar `+ Add another food`, con resultados nuevos de búsqueda o con un error de validación), la tarjeta pasa de su altura anterior a la nueva en 220 ms en vez de saltar (`static/js/rescue.js`, `animateCardHeight`). Mide la altura antes y después del cambio, anima `height` entre las dos y luego la deja libre. Una línea nueva no ocupa espacio hasta que las opciones se han desvanecido, de modo que la tarjeta cambia de tamaño una sola vez y no crece para luego encoger. Animar `height` obliga a recalcular el layout en cada frame, por eso esta excepción no se extiende a otros componentes sin acordarlo.
- **La excepción se extiende al pop-up de acciones de una fila de Food** (§9.3.1; decisión 2026-10-27, pedida expresamente por el usuario). Al pulsar `Add to recipe`, `Make a copy` o "‹", la vista actual se desvanece en 150 ms mientras se pide la siguiente. La vista nueva no se muestra, y la tarjeta conserva su altura, hasta que termina el desvanecimiento. Después la tarjeta pasa a la altura nueva en 220 ms y la vista nueva entra subiendo (`static/js/food_actions.js`). Con movimiento reducido no hay animación ni espera.
- Las utilidades de movimiento de los pop-ups (desvanecer, entrar subiendo, animar la altura de la tarjeta) están una sola vez en `static/js/modal.js` (`window.dbModalMotion`) y las usan el rescate y el menú de acciones. Un pop-up nuevo que se anime las reutiliza en vez de copiarlas.
- Los botones (`web_button`) se hunden un poco al pulsarlos (`active:scale-95`). En móvil se quita el resaltado azul del toque.
- Los repintados parciales (una tarjeta del carrito tras cambiar un valor) **no** se animan: pasan a cada cambio y un parpadeo ahí molesta más de lo que ayuda.
