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
- **Un campo que admite decimales es `type="text"` con `inputmode="decimal"`, no `type="number"`** (decisión 2026-10-27). En los formularios de Food se construye con `_decimal_input` (`components/food/food_widgets.py`). En un móvil configurado en español, el teclado decimal escribe una coma, y un `type="number"` la rechaza: el valor llega vacío o el navegador no deja enviar el formulario. El servidor acepta tanto `12,5` como `12.5` y comprueba el rango, así que en estos campos no se ponen `step`, `min` ni `max`, porque solo valen para `type="number"`. Los campos enteros (NOVA, Yuka) siguen siendo `type="number"` con `inputmode="numeric"`.
- **Excepción: un campo entero que admite negativos es `type="number"` sin `inputmode`** (decisión del usuario del 2026-11-25, que sustituye a la del 2026-10-27, `inputmode="text"`). El teclado de `inputmode="numeric"` del iPhone no tiene la tecla "−"; el de un `type="number"` a secas abre por los números y los signos, y el de Android también la tiene. Lleva `no_spinner`, que quita las flechas, y `step="any"`, para que un valor no válido lo rechace el servidor con su aviso. El navegador da como vacío lo que no es un número, así que el valor se envía como no válido en ese caso y no como vacío, que borraría el dato. Hoy es el caso del offset del carrito (§7.9).
- **Un campo de hora que se guarda solo lo hace al salir de él** (`hx-trigger="blur"`), no con `change`: un `type="time"` avisa con cada cifra, y guardar repinta la tarjeta mientras se escribe. Si un vacío borra el dato, `blur changed`.

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
  - **El estado de la vista va en la URL** (decisión del usuario, 2026-11-15). Al volver, una página tiene que aparecer como se dejó: en la pestaña y subpestaña en que estaba y con lo que mostraba. La copia de htmx no basta, porque no guarda el valor de los campos (`.value`), y además vuelve a lanzar los `hx-trigger="load"` de la página. Si la copia falta, htmx pide la URL tal cual. Por eso:
    - Cada cambio de vista que no es cambiar de página (una pestaña o un filtro de Food, la conversación de DiaBot) **sustituye** la URL de la entrada actual (`history.replaceState` o la cabecera `HX-Replace-Url`), sin añadir una entrada nueva. La ruta de la página acepta esos parámetros y la pinta directamente en ese estado.
    - Las páginas con ese estado no guardan copia (`hx-history="false"`): al volver se piden de nuevo con su URL, y salen con los datos al día. Hoy son `Food` y DiaBot.
    - **Lo que escribe el usuario no va en la URL** (es dato de salud y quedaría en el historial del navegador). El texto del buscador de Food se guarda en `sessionStorage` junto a la URL a la que pertenece, y solo se recupera al volver a esa entrada con Atrás (`popstate`). Si se abre Food de nuevo (la barra inferior, un botón), empieza vacío.
  - **El carrito tiene Back** (`back_js("/menu")`). Vuelve a la página desde la que se abrió (DiaBot, Food, Menu…) en el estado en que estaba.
- **Excepción**: una navegación concreta puede conservar la posición de scroll (o aterrizar en otro punto) **solo si el usuario lo pide explícitamente para ese caso**. Cuando eso ocurra, se documenta aquí el caso y el motivo, siguiendo el procedimiento de "Convenciones faltantes" de `CLAUDE.md`. No es una excepción que pueda decidirse componente a componente.
  - **Carrito desde DiaBot** (pedido por el usuario, 2026-11-15). Los botones de DiaBot que abren el carrito (el del carrito de la cabecera y `Review`) lo abren con la parte de arriba de la tarjeta de la comida elegida en `Add to` a la vista (la hora y el nombre), justo debajo del logo. Así se ve directamente la comida de la conversación. Con `New meal` o `No meal`, o si la tarjeta no está, se abre arriba (`dbOpenCartFromAssistant`, `static/js/assistant.js`).
- No se consideran cambio de página, y por tanto **no** resetean el scroll, los refrescos parciales que reemplazan solo un bloque de la página actual sin cambiar de pantalla (por ejemplo `hx_target="#food-list"` al escribir en un buscador, o el re-render de una fila tras editarla).

## 6. La interfaz muestra exactamente lo que se guardaría

**Regla general** (decisión 2026-09-18): lo que un control muestra tiene que ser **exactamente** lo que se guardaría en la base de datos si la entidad se confirmara en ese instante. Un control no puede mostrar un valor que la fila no tiene.

Esto extiende `code_conventions.md` §7.14 ("Defaults mostrados en la interfaz", decisión 2026-09-11) de los defaults al estado completo del formulario: §7.14 obliga a que un default visible esté ya persistido; esta sección obliga además a que **ningún** estado visible mienta sobre la fila, tenga o no un default detrás.

Consecuencias:

- **Un campo de tres estados se pinta con un control de tres estados.** Una columna `BOOLEAN` nullable donde `NULL` significa "sin dato" no puede pintarse como un checkbox de dos posiciones: un checkbox vacío se lee como `False`, y `False` ("no estaba pesado") no es lo mismo que "no lo sé". Lo mismo vale para una lista cerrada que admite "no indicado": su `<select>` tiene una opción vacía propia (`- Not given`), distinta de cualquier valor. Hoy no queda ningún campo de tres estados en las porciones: `strictly_weighed` (decisión 2026-09-18) pasó el 2026-11-12 a la lista `amount_method` (U2, `study_conventions.md` §6.3), y `macros_quality` dejó de ser de la porción el 2026-10-09.
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
Meal ended [ --:-- ] [Now]   (cada tanda menos la última lleva al pie Plate ended, §7.16)
[ + Add plate ]
Before you confirm: Eating out | Insulin (+ zona) | NotesSection
ConfirmSection (Eaten + Confirm meal)
```

Cada tanda es un bloque visualmente separado, no un simple texto entre filas: al leer la tarjeta tiene que verse de un vistazo dónde empieza y acaba cada plato.

**Orden y fila de ingrediente** (decisión 2026-10-10, rediseño del carrito). La tarjeta se lee de arriba abajo en el orden en que se usa: qué comida es, qué lleva, lo que importa antes de comer y la confirmación. Por eso `Eating out` e `Insulin` bajan de la cabecera a un bloque *Before you confirm*, junto a las notas, y borrar la comida pasa a la cabecera, al lado del nombre.

Cada `IngredientRow` muestra el nombre, una línea con la preparación (`raw · fridge · +15 min`, o `Preparation not set` si no hay ninguna), la cantidad con su unidad y el selector `Amount from` (cómo se obtuvo la cantidad, U2), que se cambia a menudo y por eso queda a la vista. Todo lo demás está en el pop-up **`Adjust`** de esa fila (`IngredientSettingsModal`): la preparación (`cooking`, `final_state`, `conservation`), `Weighed cooked`, el offset propio del ingrediente y el selector `Move` (§7.5). El pop-up es el sitio para corregir desde el carrito una preparación mal puesta u olvidada.

**Preparación por confirmar** (decisión del usuario del 2026-11-24). Para que la preparación se ponga sin abrir `Adjust`, que daba pereza, sin hacer el carrito denso.

- **Cuándo sale.** En una fila de una comida con `cooking` o `conservation` sin dato, debajo de la línea de preparación. Solo salen los campos que faltan: lo puesto en la ficha (§9.4) o por DiaBot no se vuelve a preguntar. La textura final no sale, porque nace con el estado inicial del alimento (`measurement_conventions.md` §6.11), ni tampoco la madurez de la fruta: las dos se cambian en `Adjust`. No sale en un añadido rápido, que no tiene alimento del que sacar opciones.
- **Qué ofrece.** Por campo, una línea con su nombre (`COOKED`, `KEPT`, como en DiaBot, §9.11) y **dos** píldoras con las mismas etiquetas que DiaBot (`Boiled`, `Fridge`…), la más probable primero (orden en el punto siguiente). Si un campo no tiene ninguna opción, no sale; si no sale ninguno, el bloque tampoco.
- **De dónde salen las dos opciones**, de lo más concreto a lo más general, completando hasta dos sin repetir: (1) los valores que más veces ha tenido **ese alimento** en las comidas confirmadas del usuario de los últimos 90 días, el criterio de lo habitual de DiaBot (§9.11); (2) los de los alimentos del usuario con el **mismo subtipo** (`catalog.subtype`, o `manual_intake.subtype` en un plato); (3) en un alimento de `catalog`, los de su **misma categoría**. Un plato sin subtipo se queda en (1). Las empatadas, la más reciente primero.
- **Marcada de antemano.** La primera opción de cada campo sale ya elegida (en tinta, como una píldora elegida de DiaBot) y las demás en `control`. Elegir es local: tocar otra cambia la elegida y tocar la elegida la desmarca, sin enviar nada.
- **El tick.** Debajo de las opciones, un botón con un ✓ (`aria-label` "Confirm preparation"). Es lo único que guarda: escribe a la vez los campos del bloque que tienen una píldora elegida, y uno desmarcado se queda sin dato. Mientras se guarda, el bloque se pliega y se desvanece (§10) y después se repinta la tarjeta, porque guardar puede fusionar la fila con otra igual de la tanda (`measurement_conventions.md` §4.6.4). Lo que se ha guardado se lee en la línea de preparación, y cambiarlo ya es en `Adjust`.
- **Descartar** (decisión del usuario del 2026-11-24, que sustituye a "sin tick, se queda", del mismo día). Arriba a la derecha del bloque, un botón redondo con el icono de descartar (`static/images/content/dismiss.svg`, un aspa en un círculo; `aria-label` "Dismiss…", `title` `Dismiss`) quita el bloque sin guardar nada: los campos siguen sin dato. Se recuerda **en el navegador** (`localStorage`, clave `prep_dismissed_{id de la fila}`), así que el bloque no vuelve al repintar la tarjeta. Es una comodidad de la interfaz, no un dato del estudio, y por eso no va a la base de datos: otro navegador lo vuelve a mostrar, y una fila nueva (también la que sale de una fusión) también. Sin tick ni `Dismiss`, el bloque sigue en la fila como recordatorio hasta que se confirma o se pone la preparación en `Adjust`.
- Lo habitual nunca se guarda solo: marcar de antemano no escribe nada, y la preparación solo se guarda con el toque del usuario en el tick (§9.11, "Lo habitual solo ordena").

- La preparación se guarda con un botón (`Save preparation`), con los tres campos juntos. Un campo en `Not set` se guarda como `NULL` (§6). Los tres son parte de la clave única, así que guardar puede fusionar la fila con otra de la misma tanda (`measurement_conventions.md` §4.6.4), y por eso se repinta la tarjeta entera.
- En una fruta (alimento de `catalog` con categoría `fruits`), el grupo añade `Ripeness` (`unripe`, `ripe`, `overripe` o `Not set`), que se guarda con el mismo botón y también es parte de la clave (decisión del usuario, 2026-11-12; `study_conventions.md` §6.3). La línea de preparación de la fila la muestra, y la marca de diferencias entre dos filas del mismo alimento también.
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
- **Minutos u hora** (decisión del usuario del 2026-11-15, `measurement_conventions.md` §4.5.1). Junto al offset, un botón pequeño alterna entre minutos y hora: en minutos el campo es el entero de siempre; con hora, un `<input type="time">` con la hora exacta. El botón lleva el nombre de la forma a la que cambia (`Time` o `Min`) y al pulsarlo guarda el cambio: a `min` borra la hora y deja el entero; a `time` guarda como hora `meal_time + offset` (si no hay offset, solo muestra el campo vacío, sin guardar nada). Con hora, al lado se muestra el offset que resulta (`+45 min`, o `out of range`). El pop-up `Adjust` del ingrediente lleva el mismo control.
- **`Apply all`** propaga ese offset a **todas las porciones de la tanda**, en la forma activa: con hora, escribe la hora y su offset en todas. Existe porque cambiar el offset de la tanda no reescribe sus filas (§4.6.2): es la acción explícita para decir "esta tanda entera se comió 15 minutos más tarde". Va destacado con color, junto al input de offset.
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
- **Una comida creada al añadir queda elegida** (2026-11-08). Si se añade algo sin comida elegida, la ruta crea una y responde además con el evento `mealCreated` (`HX-Trigger`, `{"id", "label"}`). `static/js/meal_selector.js` la añade al selector de comida, la deja seleccionada y lanza su `change`, que repinta el selector de tanda. Sin esto, cada añadido seguido sin recargar creaba una comida distinta, y el selector mostraba "sin comida" cuando ya existía una (§6). Lo emiten `/add_food`, `/add_manual_intake`, `/add_recipe` y sacar de la nevera; las rutas que redirigen (`/food/log`, `/food/quick_add`) no lo necesitan, porque la página se vuelve a pintar.

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
- El offset en minutos es un entero que admite negativos: `type="number"` sin `inputmode`, por la excepción de §4. La hora exacta se guarda al salir del campo, como la hora de la comida (§4).

Esto se verifica en el navegador en el ancho real, no por inspección del código.

### 7.10 Dos controles que refrescan la misma tarjeta deben sincronizarse

Cuando un botón y un input **refrescan el mismo target** y pueden dispararse casi a la vez, el botón lleva `hx-sync="#<id del input>:replace"`.

El caso que lo motiva (2026-09-19): escribir en el offset de la cabecera y pulsar `Apply all` sin salir antes del input dispara el `change` del input por el blur **y** el click del botón. Las dos peticiones reemplazan la tarjeta con `outerHTML`; el primer swap borra del DOM el elemento de la segunda, su `htmx:afterRequest` deja de llegar al listener global de `page_loading.js` —que cuenta peticiones pendientes para decidir cuándo ocultar el overlay— y **la capa de carga se queda encendida indefinidamente**. Con `replace`, la petición del botón cancela la del input y solo queda un swap.

La regla es general, no de las tandas: cualquier par de controles que compitan por el mismo `hx-target` con `outerHTML` tiene este fallo latente.

### 7.11 Un refresco parcial no mueve el scroll

Complementa §5 ("la regla no cubre los refrescos parciales"): además de no resetear el scroll al inicio, un refresco parcial debe **conservar** la posición exacta que tenía el usuario.

No basta con no tocarlo desde el código: al reemplazar la tarjeta entera con `outerHTML` desaparece del DOM el nodo que tenía el foco —un botón como `Apply all` no tiene `id` que htmx pueda restaurar— y el navegador puede reposicionar la página por su cuenta. Por eso el carrito guarda `window.scrollY` en `htmx:beforeSwap` y lo restaura en `htmx:afterSwap` y `htmx:afterSettle` para sus targets (`cart_card_event_*`, `cart_events_list`, `cart_body`), en `static/js/cart_units.js`.

Lo mismo vale para una caja con scroll propio dentro de lo que se repinta: la lista de alimentos de la barra de DiaBot conserva su posición y las tandas abiertas al elegir una preparación o al repintarse la barra (`static/js/assistant.js`, 2026-11-25).

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
- Cada porción con su cantidad, preparación, `amount_method` e `is_cooked_weight`. El offset y la madurez de una fruta no se copian: una receta no tiene madurez (`study_conventions.md` §6.3). La tanda y la comida no cambian.

**Cuándo no se guarda** (todas con su status por el canal de errores, `error_conventions.md` §7.1)

- Si hay un **añadido rápido**, no se guarda nada (`409`): no se reutiliza ni puede ser ingrediente (`code_conventions.md` §11.2.3).
- Si el usuario ya tiene una **receta personal con ese nombre** (`409`), un nombre vacío o demasiado largo (`422`), si no hay ingredientes (`409`) o si ya no existe (`404`).
- Si la comida ya está confirmada (`409`). El carrito solo muestra comidas `planned`.

**Al repetirlo**: la segunda petición choca con el nombre que tomó la primera y responde `409`.

**Después de guardar** el usuario se queda en el carrito: se cierra el pop-up y sale el aviso `Recipe saved`.

### 7.14 Confirmar: lo comido por tanda y las sobras (decisión 2026-11-07)

- Encima de `Confirm meal` hay un campo `Eaten` **por cada tanda con ingredientes**, con el nombre de la tanda si hay más de una. Vacío significa que se comió entera (`All of it`). Se escribe en **% por defecto** y dos pastillas eligen `%` o `g`; los gramos se comparan con el total de esa tanda (`measurement_conventions.md` §4.4). Al lado, la pastilla `Weighed` (casilla, desmarcada por defecto) dice si lo comido se pesó; desmarcada es a ojo (`eaten_method_<tanda>`, `study_conventions.md` §6.3, decisión 2026-11-21). Viaja con el borrador y con el pop-up de sobras.
- **Lo escrito en `Eaten` es un borrador**: se guarda en el navegador y vuelve tras recargar, hasta que la comida se confirma (`static/js/form_drafts.js`). Como el borrador se guarda por nombre de campo, el valor y la unidad llevan el id de su tanda (`ingested_value_<tanda>`, `ingested_unit_<tanda>`). Confirmado desde el pop-up de sobras, `mealConfirmed` lleva el id de la comida y `static/js/fridge.js` borra ese borrador.
- **Lo servido y lo que se va a comer** (decisión del usuario del 2026-11-21). El resumen `Meal macros` de la tarjeta muestra siempre lo servido (`Served`, cada macro con su total). En cuanto alguna tanda tiene en `Eaten` menos de toda la tanda, aparece además la línea `Eating` con los gramos y kcal que se van a comer, y cada macro pasa a mostrar lo que se va a comer con lo servido debajo (`of …`). Es solo un cálculo de la interfaz (`static/js/cart_eaten.js`) sobre los totales servidos de cada tanda, que el servidor pone en el resumen: no se guarda ni se envía nada. Sirve para pincharse según lo que se va a comer antes de confirmar, por ejemplo al apartar un tupper. Se usa la misma fracción que al confirmar (`measurement_conventions.md` §4.4). Un valor que el confirm rechazaría deja esa tanda entera en el cálculo, y el confirm dice por qué. La cobertura y los colores siguen calculándose sobre lo servido.
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

### 7.16 Hora de fin (decisión del usuario del 2026-11-26)

El dato y sus reglas están en `study_conventions.md` §6.3.

- **Dónde.** Al pie de cada tanda menos la última, `Plate ended`; y debajo de la última tanda, antes de `+ Add plate`, `Meal ended`, que es el fin de la comida y de su última tanda.
- **Cómo.** Una etiqueta, un `<input type="time">` y, justo al lado, un botón `Now` (`EndControl`, `components/cart/cart_components.py`). El campo guarda al salir de él si cambió (`blur changed`, §4), y vaciarlo borra el fin. `Now` guarda el minuto actual de un toque; los dos comparten la cola del contenedor (`hx-sync`, §7.10), así que pulsar `Now` mientras se escribía sustituye a lo escrito.
- Un error (antes del inicio o en el futuro) sale en el aviso global, como el resto de acciones del carrito.

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
| `danger` (`#b91c1c`) | botón de confirmar de los pop-ups que borran o archivan; un boli de insulina caducado (§9.9) |
| `warning` (`#c2410c`) | aviso de algo que está a punto de acabarse: un boli de insulina al que le quedan pocos días o pocas unidades (§9.9). Acordado el 2026-11-08 |
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
- Rendimiento: el desenfoque es caro. Si una lista larga va lenta en móvil, la primera medida es quitar el cristal de sus tarjetas, no de los elementos flotantes. Aplicado el 2026-11-25: las filas de lista (`food_entry`) llevan el fondo del cristal, algo más blanco, sin `backdrop-filter`, y los botones de dentro no son `web_button`.

## 9. Estructura de las páginas

Decisión 2026-10-10 (rediseño de la interfaz, rama `feat/ui-refresh`). Cómo se montan las páginas, para que todas se lean igual. Los colores y superficies están en §8 y el movimiento en §10.

### 9.1 Páginas de crear y editar (alimento, plato, receta, añadido rápido)

Se construyen con los bloques de `components/food/food_widgets.py` y `food_forms.py`. No se monta un formulario a mano.

- **Cabecera** (`_form_header`). A la izquierda, "‹ Back" (§5). A la derecha, qué se hace, como etiqueta de sección (`NEW FOOD`, `EDIT DISH`…). Debajo, el título. La cabecera no es una tarjeta.
- **El nombre es el título** (`_name_title_input`). Se escribe y se edita en el propio título, en negrita y sin recuadro: parece texto y se edita al pulsarlo. Vacío, muestra en gris qué se espera (`Name of the food`). No hay un campo "Name" aparte.
- **Secciones** (`_form_section`). Cada una es una tarjeta con un título y sus campos en rejilla, en vez de una tarjeta por campo. En las páginas de crear, las secciones obligatorias van numeradas (`① What is it?`, `② Nutrition`). Así el usuario ve cuántos pasos tiene el formulario.
- **Lo que casi nunca hace falta va plegado** (`_optional_section`, un `<details>`): *More details*, con subgrupos (`_form_subgroup`) y una línea que resume qué hay dentro. Empieza cerrado. Se abre solo cuando ya trae datos, por ejemplo los que rellena el escáner. Es lo que evita que un formulario abrume.
- **Al final**, `Favorite` en su propia fila (`_favorite_row`), marcado por defecto en los formularios de alta, y una única acción principal a todo el ancho (`_form_submit`, `web_button_primary`: `Create food`, `Save`, `Add to meal`…).
- Las páginas de editar siguen el mismo esquema, con las secciones del alimento en vez de pasos numerados.
- Los formularios no llevan etiquetas: se ponen desde la ficha (§9.4.1), también en lo que el usuario no puede editar.

### 9.2 Inicio

Arriba, el saludo con el nombre de usuario (`Hi <usuario>`). Debajo, en este orden: la comida en curso (*Current meal*, que abre el carrito), las formas de añadir comida, la inyección y el rescate (`Log rescue`, §9.6). Entre las formas de añadir comida está `From fridge`, que abre Food en la píldora `Fridge` (§9.8), con la comida en curso elegida en *Add to* como siempre.

**Alimentos por revisar** (decisión del usuario del 2026-11-21). Si el usuario tiene alimentos o platos provisionales (`code_conventions.md` §8.12, **Alimentos provisionales**), debajo de la comida en curso aparece una fila de aviso: `N foods to review` (`1 food to review` si es uno). Abre Food en la lista `To review`. Sin pendientes, la fila no existe.

### 9.3 Food

- La cabecera es fija arriba (`sticky`) y usa `web_glass_strong` (§8). Lleva el botón del rayo, que abre el pop-up de rescate (§9.6), un hueco libre entre los dos (DiaBot está en la isla, §9.11), el menú "+", el buscador, los filtros y el selector de comida (*Add to*). Mientras el menú "+" está abierto, la capa `#food_menu_scrim` desenfoca el resto de la página (§8).
- **Filtros** (decisión 2026-11-06). Se ajustan con un botón negro dentro del buscador, a la derecha, que abre un pop-up (`ModalLayer`, §8, id `food_filters_modal`) con `Cancel` y `Confirm`, y `Reset` arriba a la derecha, que quita todos los filtros. Lo elegido es un borrador, también el `Reset`: solo `Confirm` lo aplica y refresca la lista; `Cancel` o pulsar fuera lo descartan. El botón solo aparece en las listas que tienen algo que filtrar y lleva una marca mientras hay un filtro activo, porque desde fuera del pop-up no se vería. Por ahora, solo `Recipes`, con el tipo de comida: una selección múltiple de píldoras, que busca entre todos los elegidos (`code_conventions.md` §11.7). Un filtro nuevo es un control en el pop-up y un campo oculto que incluyen las peticiones de la lista.
- El `+` de una receta abre el paso previo (§9.7).
- **Cinco píldoras**: `Search`, `Food`, `Recipes`, `Favs` y `Fridge` (decisión 2026-11-07: la nevera tiene píldora propia para que se llegue a ella de un toque, §9.8). En móvil van más juntas (`gap-1.5`) para que quepan las cinco. `/food?filter=fridge` abre la página en `Fridge`; otro valor es un `422`.
- **Lista `To review`** (decisiones del usuario del 2026-11-21). No es una píldora: con una sexta no cabían en móvil y sobrecargaba la fila. Mientras haya alimentos o platos provisionales, justo debajo del buscador aparece un aviso con el estilo del de Inicio, siempre en una línea (en móvil el texto baja a `text-xs` y se recorta si hace falta): `N foods to review` en ámbar y `Review ›`. Pulsarlo pone el filtro `review`, deselecciona las píldoras, oculta sus pestañas y marca el aviso con un borde ámbar; pulsar una píldora lo desmarca. La lista muestra los provisionales del usuario, los más recientes primero, con las **mismas tarjetas que el resto de Food** (`FoodCard`: `+`, favorito y pulsación larga), con la etiqueta `To review`, pero tocar una abre directamente su formulario de edición (`return_to=review`), con `Back` para salir sin cambios. Solo `Save` le quita la marca. Al guardar su formulario de edición salen de la lista. `/food?filter=review` abre la página en esa lista. Fuera de ella, un provisional lleva también la etiqueta `To review` en la lista de Food. Mientras haya alguno, el icono de Food de la barra inferior lleva un punto, que la barra pide aparte (`/menu/review_dot`) al cargar y con el evento `dbReviewChanged`, porque `render_page` no lee la base. Guardar el formulario abierto con `return_to=review` vuelve a la lista; abierto desde el chat, a la conversación (`return_to=assistant:<id>`). El aviso del formulario de un provisional ofrece **cambiarlo de tipo** si DiaBot se equivocó: `Make it a dish` en un alimento, y `Make it a food` en un plato, con el campo `Category*` de los formularios de alimento debajo del botón (`code_conventions.md` §8.12). Un error sale en el toast con su texto. Abre el formulario del nuevo, aún por revisar, con el mismo `return_to`. Debajo, `Make it a quick add` (decisión del usuario del 2026-11-22), para lo que no vale la pena guardar: abre un pop-up de confirmación (`ConfirmActionModal`, `Yes` en rojo, porque no se puede deshacer). Al aceptar, el provisional pasa a ser un añadido rápido en cada comida donde estaba y desaparece de Food (`code_conventions.md` §8.12). Sale el aviso `Now a quick add in your meals` y la página vuelve, sin recargar (`HX-Location`), a `return_to` (la lista To review, o el chat). Si no hay `return_to`, vuelve a la lista To review, nunca a las páginas del alimento, que ya no existe. Con `return_to`, `Back` vuelve también allí (la lista o la conversación), no a la página de detalle.
- Cada alimento de la lista es una tarjeta con el nombre, la marca u origen debajo y los carbohidratos por 100 g. Los propios llevan la etiqueta `Mine` y los archivados, `Archived`. Las listas van agrupadas bajo etiquetas de sección (`web_section_label`).
- **La página trae ya la primera página de la lista** (2026-11-25), en una sola petición. `/food/list` sirve lo demás: búsquedas, pestañas, filtros y páginas siguientes. Al volver con Atrás con una búsqueda guardada (§5), `food_view.js` la pide otra vez. El buscador pide al dejar de escribir 300 ms, y una búsqueda nueva cancela la anterior.
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


De arriba abajo: el nombre y sus datos, *Add to*, la cantidad (con *Preparation*, plegado, para la preparación completa —el botón se llamó *Advanced* hasta el 2026-11-24—; en una fruta, también `Ripeness`, que solo se guarda al registrarla en una comida con `Log`, no al guardarla en un tupper), el bloque de **preparación por confirmar** (abajo), `Amount from` (U2: cómo se obtiene la cantidad esta vez, que empieza en el valor por defecto del alimento; §7.1, `measurement_conventions.md` §6.11), *Macros Summary* y *Details*. Debajo, las acciones: `Edit` y `Log`; si el usuario no puede editarlo, `Make a copy` ocupa el sitio de `Edit`. Si puede editarlo, `Make a copy` va en su propia fila debajo, encima de `Publish` (decisión 2026-10-27). Copiar pide confirmación y abre la edición de la copia. Entra bloque a bloque (§10). Debajo del nombre, sus etiquetas (§9.4.1).

En un alimento o un plato, debajo de `Edit` y `Log food`, dos botones visibles, `Save to fridge` y `Save to freezer` (decisión 2026-11-07, que sustituye a ofrecerlos dentro de *Add to*, donde no se encontraban): guardan la cantidad de arriba entera en un tupper nuevo, con su preparación y pesada y sin plato (`measurement_conventions.md` §4.8.5). La página no cambia y aparece el aviso `Saved to the fridge` o `Saved to the freezer`. Una receta se guarda desde su paso previo (§9.7). Al registrar con `Log food`, si la cantidad cocinada es mayor que la del plato, la línea `Will be saved in fridge` dice lo que se guarda en un tupper de la nevera, y se guarda de verdad.

**Preparación por confirmar en la ficha** (decisión del usuario del 2026-11-24). En un alimento o un plato, a la vista y no dentro de *Preparation*, el mismo bloque que en el carrito (§7.1): las mismas opciones, la primera marcada de antemano, el tick y `Dismiss`. Es un atajo para rellenar *Preparation*, que tiene los cuatro campos con todos sus valores y es lo único que envía el formulario.

- **Tick.** No llama al servidor: copia lo elegido a `Cooking` y `Conservation` de *Preparation*, y el bloque se pliega (§10) y deja en su sitio una línea corta con lo que se va a registrar, como la de una fila del carrito (`boiled-soft · solid · fridge`: cocción, estado final y conservación, lo que tenga valor). La línea sigue a *Preparation*: si después se cambia ahí un campo, la línea cambia con él.
- **A mano.** Si los dos campos se ponen en *Preparation*, el bloque también se pliega y deja la misma línea.
- **`Dismiss`.** Quita el bloque, sin línea, y no se recuerda: la ficha no tiene fila todavía. Los campos se registran como estén y, si van vacíos, el carrito vuelve a pedirlos (decisión del usuario del 2026-11-24).
- Sin tocar nada, los campos se envían como estén (vacíos, salvo que se hayan puesto en *Preparation*) y la comida registrada muestra el bloque en el carrito. Vale igual para `Log` y para `Save to fridge` o `Save to freezer`.

#### 9.4.1 Etiquetas en la ficha (decisión del usuario, 2026-11-08)

Contrato de datos en `code_conventions.md` §11.2.8.

- En la ficha de cualquier alimento, plato o receta que el usuario ve, sea suyo o no, debajo del nombre: sus etiquetas en esa entrada, como píldoras de su color con una × para quitarlas, las de sistema primero.
- Debajo, `+ Tag` abre un `<details>` con el resto de etiquetas que puede usar (las de sistema y las suyas), cada una como píldora `+ Nombre`, y un campo `New tag` con `Add`. Escribir el nombre de una que ya existe, sin distinguir mayúsculas, la reutiliza (una de sistema, por su nombre visible), también si otra petición la acaba de crear; si no, crea una personal con un color sacado del nombre. `Add` se deshabilita mientras se envía.
- El nombre visible de una de sistema sale de `SYSTEM_TAG_LABELS` (`components/food/tags.py`), nunca de la fila (`code_conventions.md` §11.2.8).
- En una receta se ofrecen también las de sistema, pero solo como marca: el pop-up de rescate no ofrece recetas (§9.6), así que una receta `Rescue` o `Exercise` no aparece en sus pestañas (decisión del usuario, 2026-11-12).
- Cada acción repinta el bloque entero desde lo guardado (§6). Al añadir, el panel sigue abierto para poder añadir otra.

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `POST /food/tags/{entry_type}/{entry_id}` (`tag_id`, `linked=true\|false`, `open`) | `#entry_tags_{entry_type}_{entry_id}` | `outerHTML` | el bloque | id de la URL mal formado: `400`; `linked` ausente, `tag_id` mal formado o tipo desconocido: `422`; al añadir, entrada o etiqueta no disponibles: `404`. Quitar es un no-op con éxito aunque la entrada ya no exista o no sea visible. Por el canal de errores |
| `POST /food/tags/{entry_type}/{entry_id}/new` (`name`) | `#entry_tags_{entry_type}_{entry_id}` | `outerHTML` | el bloque, con el panel abierto | nombre vacío o largo: `422`; entrada no disponible: `404`. Por el canal de errores |

Las dos exigen el header `HX-Request` (`403` si falta).

### 9.5 Carrito

La página empieza con la etiqueta `CART`, el título *Planned meals* y una línea que explica qué hacer. Cada comida es una tarjeta con la estructura de §7.1.

### 9.6 Rescate

Decisión 2026-10-11. Un rescate es lo que se toma para tratar una hipoglucemia. Se registra desde un pop-up y crea directamente una comida ya consumida. Desde el 2026-11-08 el mismo pop-up sirve de añadido rápido para otros tipos de comida (unas pastillas o un papel de glucosa que no son un rescate): se elige el tipo, con `Rescue` por defecto. Desde el mismo día tiene dos pestañas, `Rescue` (por defecto) y `Exercise`, una por etiqueta de sistema (`study_conventions.md` §N): cada una ofrece sus alimentos y elige su tipo de comida abajo, que se puede cambiar antes de confirmar.

**Dónde está**

- El botón del rayo de la cabecera de Food (§9.3) y el botón `Log rescue` de Inicio (§9.2) abren el mismo pop-up (`ModalLayer`, §8, id `rescue_modal`). No hay panel desplegable.
- El contenido del pop-up se pide al servidor cada vez que se abre (`GET /food/rescue/form`). Así la fecha y la hora son las de ese momento y el formulario sale vacío. La respuesta trae ya la lista inicial de alimentos, y `static/js/rescue.js` abre el pop-up cuando llega: se pinta completo, con una sola animación de entrada (§10), en vez de abrirse vacío y crecer por partes.

**Qué alimentos se ofrecen**

- Con el buscador vacío salen los alimentos de la pestaña: los que este usuario ha etiquetado con su etiqueta de sistema (`rescue` o `exercise`) y los que ya ha usado en comidas de ese tipo, primero los usados más recientemente. Cambiar de pestaña vuelve a pedir la lista con lo que haya escrito en el buscador.
- Al escribir, los resultados **sustituyen** a los alimentos de la pestaña en el mismo sitio, y al vaciar el buscador vuelven los de la pestaña. La lista declara su propio `hx-target`: sin él heredaría el del formulario (`#rescue_form_error`) y los resultados aparecerían debajo. Enter en el buscador (la tecla Buscar del teclado del móvil) no envía el rescate: solo cierra el teclado.
- La búsqueda abarca todos los alimentos (`catalog`) y platos (`manual_intake`) que el usuario puede ver, con la misma regla de visibilidad que el resto de búsquedas, incluidos los archivados que conserva (`code_conventions.md` §11.2). Ignora mayúsculas y acentos, y `%` y `_` cuentan como caracteres. Los de la pestaña van primero. No ofrece recetas, aunque tengan la etiqueta de la pestaña: en una receta es solo una marca (§9.4.1, decisión del usuario, 2026-11-12).
- Cada opción es una fila `control` compacta (§8) con el nombre y, debajo, la marca u origen y los hidratos del alimento (por ración si la tiene, si no por 100 g). La lista tiene una altura máxima con scroll propio. Sin alimentos en la pestaña, una línea explica que basta con buscar cualquiera o etiquetar un alimento o un plato, y que los registrados aparecerán ahí.
- La etiqueta de cada pestaña se identifica por su `system_key` (`SystemTag`), nunca por el nombre (`code_conventions.md` §11.2.8), y el texto de la pestaña sale de `SYSTEM_TAG_LABELS`, el mismo que el de las píldoras. El tipo de comida de cada una sale de `SYSTEM_TAG_MEAL_TYPE` (`domain/tag.py`).

**Líneas**

- Al elegir un alimento se añade su línea (nombre, cantidad, unidad y un botón para quitarla) y el buscador se oculta. `+ Add another food` lo vuelve a mostrar para añadir otra línea. Si se quitan todas, el buscador vuelve a aparecer.
- La línea la pinta el servidor (`GET /food/rescue/line/{entry_type}/{entry_id}`): el nombre con un botón para quitarla y, debajo, la cantidad con botones − y + y la unidad. Los botones − y + solo mueven el número en el navegador (1 ración, 10 g, 1 oz, 0,25 lb) y nunca lo bajan a 0. La unidad es un `<select>` de `AmountInputUnit` sin `%`: `portion` solo aparece si el alimento tiene ración, y entonces la línea nace con `1 portion`. Sin ración, nace en `g` y con la cantidad vacía. En una fruta, la línea añade un `<select>` `Ripeness` con `Not set` elegido (decisión del usuario, 2026-11-12; `study_conventions.md` §6.3).
- Se envían `amount_value`, `amount_unit` y `ripeness` (vacío si no es una fruta o no se indica) por línea. El servidor convierte a gramos con `amount_to_grams` y lee la ración del alimento en la base, nunca de un campo oculto (decisión 2026-09-22, `code_conventions.md` §7.13).
- No hay "% comido" ni "sobrante": no se guardan en ningún sitio (§6).
- **Elegir un alimento que ya está en la lista no añade otra línea: suma a la existente**, como el carrito. Si la línea está en raciones, suma 1 ración; si está en gramos y el alimento tiene ración, suma su peso en gramos. En oz, lb o sin ración no hay una cantidad fiable que sumar, y la línea solo se resalta para que el usuario la ajuste. Al guardar, el servidor fusiona igualmente las porciones repetidas (§4.6.4).
- **Ningún campo se enfoca solo** (ni al elegir un alimento, ni al quitarlo, ni al abrir el pop-up): en el móvil abriría el teclado sin que el usuario lo pida.
- No se guarda estado del pop-up en `localStorage`.

**Diseño**

- Compacto, para que quepa en la pantalla de un móvil: las pestañas `Rescue` / `Exercise` en lugar del título, con una × para cerrar, el buscador, la lista, las líneas, el tipo de comida (un `<select>` de `MealType` con el de la pestaña elegido), la fecha y la hora en una fila sin etiqueta, y *Cancel* / *Log rescue* a todo el ancho. Con otro tipo, el botón dice *Log meal*. Sin textos de ayuda fijos.
- Nada sobresale de la tarjeta en el móvil. Un nombre de alimento largo ocupa como mucho dos líneas y después se corta con "…" (`line-clamp-2`, `break-words` para una palabra sin espacios). La fecha y la hora van en columnas `minmax(0, 1fr)` con `appearance-none` y el texto centrado, porque iOS da a esos controles nativos un ancho propio mayor que la columna (§3).

**Fecha y hora**

- Dos campos, `date` y `time`, rellenos con el momento de abrir el pop-up y editables. Se admite cualquier momento, también futuro, con el mismo criterio que las inyecciones (decisión 2026-09-06).

**Qué se guarda** (`POST /food/rescue/log`)

- Cada envío crea un evento nuevo, aunque haya un rescate reciente: `meal_type` el elegido (`rescue` por defecto; vacío o desconocido es un error de validación), `insulin_dose = FALSE` (lo que se registra aquí no lleva insulina y nunca crea una inyección automática, sea del tipo que sea), una sola tanda con offset 0 y una porción por línea. Si un alimento se repite con la misma preparación, se suman sus cantidades (`measurement_conventions.md` §4.6.4).
- El evento se crea en `planned` y se confirma al 100 % en la misma transacción, con la misma confirmación que usa el carrito (`services/intake_event.py`). Así calcula `ingested_amount` y `amount_confidence` con las mismas reglas que cualquier comida (`measurement_conventions.md` §6.9.1).
- Todo va en una transacción. Si una línea no es válida, no se guarda nada.

**Respuestas HTMX**

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /food/rescue/form?kind=` (`rescue` por defecto) | `#rescue_modal_body` | `innerHTML` | el formulario, con la lista inicial de alimentos dentro | sin sesión: `401`; `kind` desconocido: `422`. Por el canal de errores |
| `GET /food/rescue/options?q=&kind=` (al escribir en el buscador o cambiar de pestaña) | `#rescue_picker_results` | `innerHTML` | la lista de alimentos | `kind` desconocido: `422` por el canal de errores |
| `GET /food/rescue/line/{entry_type}/{entry_id}` | `#rescue_lines` | `beforeend` | una línea | `404` por el canal de errores (`error_conventions.md` §7.1) |
| `POST /food/rescue/log` | `#rescue_form_error` | `innerHTML` | cuerpo vacío y el evento `rescueRegistered` (`HX-Trigger`, con el `meal_type`). `static/js/rescue.js` cierra el pop-up y muestra el aviso de éxito `Rescue registered`, o `Meal registered` con otro tipo (`dbShowAppNotice`, `error_conventions.md` §7.1) | validación: `200` y el mensaje en `#rescue_form_error` (`code_conventions.md` §9.5). Sesión, alimento inexistente o conflicto: su status por el canal de errores |

Todas exigen el header `HX-Request` (`403` si falta).

**Marcar un alimento como rescate o ejercicio**

- Con las etiquetas de sistema `Rescue` y `Exercise` desde la ficha (§9.4.1), en cualquier alimento o plato que el usuario vea. En una receta son solo una marca. El botón provisional `Rescue` y `/food/rescue/mark/...` ya no existen (2026-11-08).

### 9.7 Recetas: paso previo, tandas e ingredientes

Decisión 2026-11-05. El modelo está en `measurement_conventions.md` §4.7 y el contrato en `code_conventions.md` §11.2.4.

**Paso previo al añadir a una comida**

- El `+` de la fila y `Add to meal` de la ficha abren el pop-up `recipe_add_modal`. Su contenido se pide al servidor (`GET /food/recipe/{id}/add/form`) con la comida y la tanda elegidas, y `static/js/recipe_add.js` lo abre cuando llega, como en el rescate (§9.6).
- Con `servings`, un campo `Servings` con `1`. Sin él, no aparece, pero el paso sigue, para ajustar la preparación.
- Una línea por ingrediente, con su cantidad por ración. Se despliega para cambiar `cooking`, `final_state` y `conservation`, ya rellenos con lo de la receta. Con varias tandas, agrupadas y con un aviso de que entran como tandas nuevas.
- `POST /add_recipe/{id}` recibe la comida, la tanda, las raciones y la preparación por ingrediente, nunca cantidades. Validación: `200` + fragmento en `#recipe_add_error`. Una comida o tanda que no existe, `404`; una comida ya confirmada o una receta sin ingredientes, `409`. Al terminar, el evento `recipeAdded` cierra el pop-up y muestra `Added to the meal`. Si ha creado la comida, va también `mealCreated` (§7.7).
- Repetirlo añade la receta otra vez: es otra ración, no un duplicado (§9.6 de `code_conventions.md`). El botón se deshabilita durante la petición.
- Debajo, `Save to fridge` y `Save to freezer` guardan esas mismas raciones, con la preparación elegida, en un tupper nuevo con el nombre de la receta (decisión 2026-11-07, `measurement_conventions.md` §4.8.5). La comida y la tanda no se usan. El pop-up se cierra y aparece el aviso `Saved to the fridge` o `Saved to the freezer`.

**Tandas en la ficha**

- Con una tanda el concepto no se ve: solo `Add ingredient` y un `+ Add plate` discreto debajo, que no aparece hasta que la receta tiene una tanda. Es distinto del carrito, donde la cabecera sale siempre (§7.2), porque aquí no hay offset común que mostrar.
- Con dos o más, cada tanda lleva una cabecera con su nombre editable (vacío, el derivado), subir, bajar y borrar, y su propio `Add ingredient`. Cada ingrediente tiene un selector para moverlo de tanda.
- Borrar una tanda con ingredientes responde `409` y pide moverlos o borrarlos.
- Toda acción repinta el bloque `#recipe_ingredients_{id}` y, fuera de banda, el resumen.

**Por ingrediente**: cantidad, preparación y `Weighed cooked`, con el mismo criterio que el carrito (§7.4). `Amount from` se ajusta en el carrito.

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
  - **Píldora `Fridge`** de la cabecera de Food: sin seleccionar, lleva un degradado de blanco a `wash-blue` y el borde en `ice`. Seleccionada, tiene el negro de las demás píldoras y conserva solo el borde `ice` (`.food_filter_fridge`).
  - Un tupper caducado no cambia de forma: se marca solo con la etiqueta `Expired` y la línea de días en `danger` (arriba).

### 9.9 Bolis de insulina (decisión del usuario, 2026-11-08)

Modelo en `measurement_conventions.md` §8.4.

- **Etiqueta de un boli**, igual en todos los selectores: marca, formato y lo que queda (`NovoRapid · Cartridge · 140 U left`, con `≈` si es aproximado). Los selectores listan solo bolis abiertos, el que caduca antes primero, y terminan en la opción `+ New pen`, que no se guarda: abre el pop-up de abrir boli y, al crearlo, el boli nuevo queda elegido en ese selector. No hay opción "sin boli".
- **Pop-up de abrir boli** (`New pen`, en la sección `Insulin` del menú, en los selectores y en ajustes). Marca (las activas del usuario, con su tipo, más `+ New brand`, que despliega sus campos: nombre, tipo, días de uso, 30 por defecto, y unidades por boli, 300 por defecto), formato y fecha en que se saca de la nevera, hoy por defecto. Marca y formato empiezan sin elegir (§6). Al guardar, la caducidad es esa fecha más los días de la marca.
- **Formulario de inyección del menú.** En vez del tipo, el selector de boli, y el tipo sale de su marca. El boli sale elegido de antemano: el de basal mientras falte la basal del día y, si no, el de rápida de siempre (`measurement_conventions.md` §8.4, decisión del usuario del 2026-11-24). La dosis (`Dose (U)`) es obligatoria si el boli es de basal y opcional si es de rápida; el " - optional" del título sigue al boli elegido, también al abrir el pop-up.
- **Errores de los formularios de inyección** (menú y edición del registro, 2026-11-08). Los comprueba el servidor, no `alert()`: boli, zona (obligatoria en los dos), fecha y hora, y dosis. Un error de formulario sale dentro del pop-up (`#menu_injection_error`, `#settings_injection_error_{id}`) y el pop-up sigue abierto; el resto, por el aviso global. Solo se cierra al guardar: `injectionLogged` repinta el menú y avisa `Injection logged`, e `injectionUpdated` repinta el registro (también al borrar).
- **Carrito.** Con `Insulin` marcado, debajo de la fila, en una línea: el botón de la zona, el selector de boli (solo de rápida) y la dosis, que se guardan solos al cambiar, como el resto del carrito. El boli viene elegido con el de por defecto; si no hay ninguno, el selector muestra `Choose pen` y confirmar avisa.
- **Ajustes, `Insulin pens`** (2026-11-08). Un menú con el mismo diseño que la página principal de ajustes y dos botones, `Pens` y `Brands`, cada uno con su página (`/settings/insulin/pens` y `/settings/insulin/brands`), que vuelve a ese menú con `Back`.
  - **Pens**: los bolis abiertos, el que caduca antes primero. Cada fila dice marca y formato, los días desde que se abrió y los que le quedan (`3 days in · 27 days left`) y las unidades que quedan. A punto de acabarse, la línea afectada va en `warning`; caducado, lleva `Expired` y la línea de días en `danger`, y el botón `Discard` se ve en la fila sin tener que abrirla. Al tocar una fila: `Edit` (formato, caducidad y capacidad) y `Discard`, que pide confirmación. Abajo, `New pen`.
  - **Brands**: las marcas activas con su tipo, sus días de uso y sus unidades por boli. Al tocar una fila: `Edit` y `Delete`, que pide confirmación (archiva si tiene bolis). El tipo no se puede cambiar si la marca tiene bolis. Abajo, `New brand`.
- **Registro de inyecciones de ajustes.** Cada fila muestra su boli. Al editar una se elige el boli entre los abiertos y el que ya tenía; una inyección anterior a los bolis ofrece además dejarla sin boli.

### 9.10 Ajustes, `Tags` (decisión del usuario, 2026-11-08)

`/settings/tags`, desde el botón `Tags` de ajustes. Contrato de datos en `code_conventions.md` §11.2.8.

- Arriba, `New tag` con `Add`, que crea una etiqueta personal y repinta la lista; `Add` se deshabilita mientras se envía. Debajo, el buscador, que ignora mayúsculas y acentos y trata `%` y `_` como caracteres.
- La lista: primero las de sistema, como píldora con la marca `System` y sin acciones; después las del usuario, con el nombre editable en la propia fila (se guarda al cambiar, no en cada salida del campo), el color (el selector Pickr, con versión fija) y `Delete`, que pide confirmación y avisa de que se quita de todos los alimentos.
- Cada cambio responde con la fila leída de nuevo por su id (§6).

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /settings/tags/list?q=` | `#settings-tags-list` | `innerHTML` | la lista | — |
| `POST /settings/tags` (`name`) | `#settings-tags-list` | `innerHTML` | la lista; el campo se vacía | `422` nombre; `409` ya existe o es el nombre visible de una de sistema |
| `POST /settings/tags/{tag_id}/update` (`name`, `color`) | `#tag_row_{tag_id}` | `outerHTML` | la fila | `422` nombre o color; `404` no es suya (también una de sistema); `409` nombre ocupado o de sistema |
| `POST /settings/tags/{tag_id}/delete` | `#tag_row_{tag_id}` | `delete` | cuerpo vacío | `404` no es suya o ya se borró |

Todas exigen el header `HX-Request` (`403` si falta) y los errores van por el canal común (`error_conventions.md` §7.1).

- **Cabecera** (2026-11-21): Tags usa la cabecera de subpágina de Ajustes, igual que la guía (§9.12): barra fija arriba, sin margen, con `Back`, el título y el buscador de etiquetas. El alta de una etiqueta queda debajo, y cada fila ocupa todo el ancho.

### 9.11 Asistente (decisión del usuario, 2026-11-12)

Contrato del servidor en `code_conventions.md` §8.12. Solo existe si el asistente está configurado.

**Dónde está.** Página `/assistant`, con dos accesos (decisión del usuario, 2026-11-12):

- **En la isla, en el centro de sus cinco elementos** (decisiones del usuario del 2026-11-21): Menu, Stats, DiaBot, Food, Settings. Así se llega desde cualquier página. Es un elemento como los demás, pero bastante más grande, que sobresale un poco por arriba y por abajo de la isla sin hacerla más alta (márgenes verticales negativos; la isla no recorta su contenido), con la cara normal de DiaBot centrada (`static/images/diabot/diabot_island.svg`, recortado a la gota) y `aria-label` `DiaBot`. Lo rodea un círculo (`--bump-d`) del tamaño del elemento en reposo: 88 px en móvil y 112 px en escritorio; elegido, el círculo y la cara se encogen con una animación hasta caber en la isla (`--bump-on`: el alto de la isla menos 10 px en móvil, algo mayor que el indicador de los demás elementos, y menos 18 px en escritorio, igual que ese indicador) mientras llega el indicador, que ocupa todo el círculo; así la isla queda como una píldora lisa y lo que se apoya en ella (el cuadro de mensajes del chat, colocado con `--island-reach`, que mide `island_indicator.js`) tiene un margen uniforme (pegado en móvil, 12 px por encima en escritorio) (decisión del usuario del 2026-11-21, opción D entre cuatro). El elemento conserva en la isla su tamaño de reposo, así que la isla no cambia de ancho (`.island_bump`, propiedades registradas con `@property` para que el tamaño se anime); el indicador apunta directamente al tamaño final, así que el deslizamiento y el cambio de tamaño ocurren a la vez, y la isla y el círculo son **un solo cristal**: una capa con el fondo de `web_glass` recortada con una máscara a la píldora más el círculo (`island_fill`), debajo la sombra de la píldora, encima el círculo **elevado** (decisión del usuario del 2026-11-21, elegida entre siete opciones: más blanco que la isla, con borde blanco y una sombra pequeña propia, como un botón apoyado en ella) y la isla transparente con su borde agujereado donde está el círculo (`input.css`). Dos cristales superpuestos nunca se ven iguales. Como DiaBot es siempre el elemento central, todo se centra solo con CSS; `island_indicator.js` solo da la altura de la isla (`--island-h`), vigilada con `ResizeObserver` porque cambia al cargar las fuentes. La isla queda a 40 px del borde inferior (`bottom-10`). En móvil los demás elementos miden `w-14` y DiaBot no lleva margen lateral, para que la isla quepa en 375 px. En reposo no tiene nada debajo, como el resto; elegido, el indicador se desliza hasta él igual que a cualquier otro elemento. Solo existe si el asistente está configurado. Ya no hay accesos en Inicio ni en la cabecera de Food: su hueco queda libre para otras acciones.

**Página** (rediseño, decisión del usuario del 2026-11-21: "la comida arriba y el chat abajo", elegida entre tres). Una barra fija arriba (`sticky`, `web_glass_strong`, con las esquinas inferiores redondeadas de la barra de Food), para tener la comida a mano aunque la conversación sea larga:

- **Primera fila**: "‹ Back" a la izquierda; en el centro, la píldora del chat, que abre la lista de chats: la comida con el mismo texto que en Food (§7.7), `New meal` o `No meal`, con `▾`; a la derecha, los hidratos de la comida (sin comida, nada) y un botón redondo pequeño con el icono del carrito que abre el carrito. El botón flotante del carrito no se muestra en esta página (`data-hide-cart`), porque taparía el compositor.
- **La comida**: debajo, una fila por alimento de la comida del chat (los mismos que en el carrito), con un punto de confianza, su nombre, sus gramos y sus hidratos, y la etiqueta `To review` si es un provisional sin revisar (`code_conventions.md` §8.12). **Plegado por espacio** (decisión del usuario del 2026-11-22, sustituye a "con más de 3"): con dos alimentos o más, en cuanto la lista ocupa más del 10 % del alto de la pantalla del chat (`MEAL_FOLD_SHARE`), `static/js/assistant.js` la pliega en una línea con un punto de confianza por alimento, `N foods · M estimated` y `Show all ▾`. Pulsarla la despliega con su propio scroll, como mucho el 45 % del alto, para que nunca tape el chat, y `Hide ▴` la vuelve a plegar. Desplegada sigue así tras cada mensaje, hasta que el usuario la pliega o cambia de chat. Sin JS se ve entera (`<details open>`). **Por tandas** (decisión del usuario del 2026-11-22): una comida con varias tandas sigue siendo un solo chat. La lista se agrupa por tanda, con su nombre visible (`measurement_conventions.md` §4.6.3), sus alimentos y sus hidratos. La última, donde añade DiaBot, sale abierta, y las anteriores plegadas en su línea. Para empezar otra tanda basta con decírselo ("ahora otra tanda"): DiaBot la crea con `add_plate`.
- **Hidratos como rango y punto de confianza** (decisión del usuario del 2026-11-22). El total de la barra es un rango, `52–60 g` (un solo número si los dos extremos redondean igual). Cada alimento aporta sus hidratos más o menos un margen que suma el de su cantidad y el de sus macros (`domain/portion_detail.py`): cantidad con báscula, de bolsillo o del envase ±5 %, habitual ±15 %, medida casera, a ojo o estimada por la IA ±30 %; macros de etiqueta u oficiales ±5 %, de tabla, de ingredientes u Open Food Facts ±15 %, estimadas ±30 %. Una cantidad sin dato cuenta ±30 %; unos macros sin dato, ±15 %, como los de tabla (decisión del usuario del 2026-11-22: `macros_source` vacío nunca significa "estimado", `measurement_conventions.md` §6.11, y la mayoría del catálogo no lo tiene, así que un alimento pesado salía siempre estimado). El extremo bajo nunca baja de 0. El punto es verde (`emerald-600`, medido) si el margen del alimento no pasa del 20 %, y ámbar (`amber-400`, estimado) si pasa; no usa `warning`, que es casi rojo. El pop-up de chats y los chats pasados en solo lectura usan el mismo cálculo. Sin alimentos, o en un chat sin comida, no aparece. Se vuelve a dibujar fuera de banda tras cada mensaje y cada `+1`.

Después, los mensajes de la conversación y, fijo abajo, el compositor: el botón de foto, un `<textarea>` que crece con el texto hasta un máximo y luego hace scroll, y el botón de enviar. Ningún campo se enfoca solo al abrir la página en el móvil (mismo motivo que §9.6).

**Una conversación por comida** (decisión del usuario, 2026-11-12; lista de chats, 2026-11-21).

- Al abrir la página se abre la conversación de la comida planificada más reciente, como en Food, o una comida nueva si no hay ninguna (decisión del usuario del 2026-11-21: ya no se recuerda la última elección en `sessionStorage`). `?conversation_id=` abre esa conversación; `?intake_event_id=` la de esa comida; `?new_meal=1` una comida nueva; `?intake_event_id=none` el último chat sin comida.
- **Lista de chats**: la píldora abre un pop-up (§8) con, de arriba abajo:
  - `Planned meals`: una fila por comida planificada, con su texto de §7.7 y sus hidratos; la del chat abierto, marcada. Abre la conversación de esa comida (la última, si tuviera varias), o la vacía con la introducción.
  - `+ New meal`: un chat vacío para una comida nueva.
  - `No meal`: los últimos 5 chats sin comida, cada uno con la primera frase del usuario y su fecha, y `+ New chat`, que empieza uno vacío; los anteriores se conservan. Cada uno lleva a la derecha un botón con una papelera, `Delete` (decisión del usuario del 2026-11-22): lo **oculta** de esta lista al momento, sin preguntar, porque no se pierde nada; sigue en los chats pasados (`code_conventions.md` §11.2.9).
  - `Past chats ›`, que abre los chats pasados.

  Cada fila carga la página con su URL, como un enlace.
- **Cuándo es la comida nueva**: no se pregunta antes (decisión del usuario del 2026-11-21). La primera línea de un chat nuevo lo recuerda: "Say when, or it is for now." Si el mensaje dice cuándo ("mañana para cenar sobre las 9"), el asistente pone la fecha y la hora a la comida; si no, es para ahora.
- El primer mensaje respondido de una comida nueva crea la comida planificada, con el tipo automático (`code_conventions.md` §7.14), aunque el asistente aún no haya añadido nada (decisión del usuario del 2026-11-21: así salir de la página no pierde el chat, por ejemplo al empezar un picoteo). La respuesta trae fuera de banda la barra con la comida ya elegida y la lista de chats, para que el siguiente mensaje siga en ella. Si el primer envío falla, no se crea nada.
- **Chats pasados** (`/assistant/history`, decisión del usuario del 2026-11-21: se pueden ver, pero no salen por defecto). Todos los chats que ya no están en la lista: los de comidas confirmadas y los chats sin comida, también los borrados de la lista (decisión del usuario del 2026-11-22), los más recientes primero, agrupados por día (el de la comida, o el del último mensaje en un chat sin comida). Cada uno con el texto de §7.7, sus hidratos y los nombres de sus alimentos, o con su primera frase y `No meal`; uno borrado de la lista lleva la etiqueta `Deleted` y sale algo atenuado. Abrir una comida confirmada (`/assistant/history/{id}`) la muestra en **solo lectura**: la barra con la comida y la conversación, sin compositor, sin botones `+1` y sin las tarjetas que solo ofrecen una acción. Una comida confirmada se cambia donde siempre, no desde el chat. Un chat sin comida se abre en la página normal y se puede seguir. Arriba, un buscador (el de las subpáginas de Ajustes) filtra mientras se escribe, con un retraso de 300 ms, por el nombre de la comida, la primera frase del chat y los nombres de sus alimentos, sin acentos ni mayúsculas (`code_conventions.md` §11.7); la URL guarda la búsqueda (`?q=`). Sin resultados dice `No chats match "…"`. `Repeat today`, arriba.
- **Dudas sobre la guía** (decisión del usuario del 2026-11-22; `code_conventions.md` §8.12). En cualquier chat se puede preguntar qué significa un valor o cómo registrar algo. La respuesta sale plegada en una línea: un `?`, la pregunta y `GUIDE`; abierta mientras es el último turno, y con `See it in the guide ›`, que abre la guía. Se guarda, pero no se reenvía al modelo.
- `No meal` es un chat solo para crear alimentos y recetas (`code_conventions.md` §8.12, **Conversación sin comida**): nada va al carrito. Viaja como `intake_event_id=none`.
- El id de la conversación viaja en un campo oculto. Vacío empieza una nueva.

**Enviar** (decisión del usuario, 2026-11-12; en segundo plano desde el 2026-11-21, `code_conventions.md` §8.12).

- Envía el botón y, en un ordenador (puntero fino con hover), también Enter; ahí Shift+Enter hace un salto de línea (decisión del usuario del 2026-11-22). En el móvil Enter siempre es un salto de línea, como en los chats del móvil. Con la lista de `/` abierta, Enter elige el alimento. El botón está activo si hay texto, una mención o alguna foto.
- **Al enviar, el mensaje pasa al chat al momento** (decisión del usuario del 2026-11-22): su burbuja aparece a la derecha, subiendo con un fundido corto (sin animación si el sistema pide reducir el movimiento), con la píldora de fotos si las lleva; el texto y las menciones salen del compositor, y la introducción de un chat vacío desaparece. Las fotos siguen en el compositor hasta que llega la respuesta.
- Mientras se sube el mensaje, aparece una burbuja `Sending` y el botón se desactiva. En cuanto el servidor lo acepta (decisión del usuario del 2026-11-21, `code_conventions.md` §8.12, **Turno en segundo plano**), la burbuja provisional pasa a ser el bloque del mensaje con una burbuja `Thinking` y la cara `thinking` de DiaBot con tres puntos que suben uno tras otro (quietos si el sistema pide reducir el movimiento, §10). Ese bloque pregunta cada 2 s si hay respuesta; se puede salir de la página y, al volver, sigue esperando o ya muestra la respuesta.
- Cuando la respuesta está, sustituye a `Thinking` el turno: el mensaje del usuario, a la derecha, con la píldora `Photo` si llevaba una foto, o `N photos` si llevaba varias; las respuestas del asistente, a la izquierda y como texto plano (solo las de un mensaje sin llamadas a herramientas: el texto que el modelo escribe junto a una llamada no es una respuesta); y las tarjetas de lo que hizo. Después se vacía el compositor (texto, menciones y fotos) y se desplaza la vista al turno nuevo.
- Si el envío falla (validación, o el asistente aún responde al anterior), el toast lo explica y el compositor se queda como estaba. Si falla la respuesta, el mensaje queda con el motivo debajo y su texto vuelve al compositor si está vacío; las fotos hay que volver a adjuntarlas.

**Usual now** (decisión del usuario del 2026-11-22). En un chat vacío de una comida, encima del compositor, una fila con la etiqueta `USUAL NOW` y hasta 5 píldoras (`web_button`) con los alimentos que más come el usuario a esta hora: una puntuación por cercanía a la hora del día (decisión del usuario del 2026-11-22, sustituye al ranking de uso filtrado por distancia media): cada comida confirmada de los últimos 60 días suma `exp(−(distancia a ahora / 90 min)²)` a cada alimento que tuvo (1 a esta misma hora, 0,64 a una hora, 0,17 a dos), y salen los de más puntuación, con al menos 0,35 (una comida a hora y media o menos), y con la mediana de lo que se comió de cada uno (`143 g`). Pulsar una no envía nada: escribe `/Nombre 150 g` al final del texto como una mención, así que se pueden juntar varias en un mensaje. Desaparece con el primer envío. Sin alimentos que cumplan, no aparece; en un chat sin comida, tampoco.

**Lo de siempre** (decisión del usuario del 2026-11-22; `code_conventions.md` §8.12). Si el usuario escribe "lo de siempre" o algo parecido, el asistente busca las comidas repetidas a esta hora y las añade, o pregunta cuál con respuestas rápidas.

**Repeat today** (decisión del usuario del 2026-11-22). En un chat pasado de una comida confirmada, junto al título, el botón en tinta `Repeat today` crea una comida planificada para ahora con lo que sirvió aquella (`code_conventions.md` §8.12) y abre su chat.

**Respuestas rápidas** (decisión del usuario del 2026-11-21; `code_conventions.md` §8.12). Cuando el asistente pregunta algo con pocas respuestas probables, debajo de su turno aparecen de 2 a 4 botones redondos (`web_button`) con las respuestas ("Homemade", "Restaurant"). Pulsar uno lo envía como mensaje del usuario, igual que si lo hubiera escrito. Solo los lleva el último turno: cualquier envío los quita.

**Preparación con un toque** (decisiones del usuario del 2026-11-21 y del 2026-11-22; `code_conventions.md` §8.12). En **todos** los alimentos que añade el asistente, por cada uno de los tres campos de preparación que el usuario no dijo (cocción, textura final y conservación), su fila en la barra de la comida lleva una línea con el nombre del campo (`COOKED`, `TEXTURE`, `KEPT`, como etiqueta de sección) y 2 o 3 píldoras con los valores más probables según el contexto, el más probable primero (`Boiled`, `Fried`, `Oven`...; `Solid`, `Mashed`...; `Fresh`, `Fridge`...). Pulsar una pone ese valor al momento, sin el asistente; la elegida queda en tinta y las demás en `control`. **Desmarcar** (decisión del usuario del 2026-11-22): pulsar otra vez la elegida vacía el campo, que queda sin dato como al vaciarlo en el carrito, para deshacer un toque equivocado. **Lo habitual primero** (decisión del usuario del 2026-11-22): el valor que más veces ha tenido ese alimento en las comidas confirmadas del usuario de los últimos 90 días va el primero de su campo, entre las opciones o añadido si DiaBot no lo ofreció, como mucho 3. Lo habitual solo ordena: el campo no se rellena sin que el usuario lo diga o lo toque. La textura final ya nace con el estado inicial del alimento (`measurement_conventions.md` §6.11), así que si ese valor está entre las píldoras sale ya elegido. La barra se vuelve a dibujar con la respuesta. (Pendiente para otro día, idea del usuario del 2026-11-22: reducir en qué alimentos hace falta preguntar los tres campos, según su relevancia y lo que se suele poner por cómo se usa el producto.)

**Avatar de DiaBot** (decisión del usuario, 2026-11-21). Como en las apps de mensajería, la cara de DiaBot (`static/images/diabot/`) va abajo a la izquierda de sus mensajes de cada turno, uno por turno. Mientras responde, la burbuja `Thinking` lleva la cara `thinking`; al llegar la respuesta, el avatar del turno nuevo pasa de `thinking` a `happy`; si falla, la burbuja se queda con la cara `confused` y el texto "Couldn't answer" hasta el siguiente envío. Las conversaciones reabiertas muestran `happy`. Las caras están apiladas y el cambio es un fundido con un pequeño rebote de escala (§10); sin movimiento, cambian sin animación.

**Botones `+1`** (decisión del usuario, 2026-11-21). Para ir añadiendo de uno en uno sin escribir ni esperar al asistente, por ejemplo en un picoteo. No hay un modo especial: están siempre que la comida tenga algo.

- Encima del compositor, una fila de botones con lo que el asistente añadió a la comida de la conversación y sigue en ella (`code_conventions.md` §8.12), lo último añadido primero: `+1 Croqueta`, con el número que lleva (`×3`). Si no caben, la fila se desplaza en horizontal. Con `No meal`, o sin nada en la comida, no aparece.
- Pulsar añade una unidad más al momento (`code_conventions.md` §8.12, **Botones `+1`**), sin llamar al asistente, y el número del botón sube. Si falla, el toast lo explica y el número no cambia.
- Mantener pulsado abre el menú encima del botón sin mover el compositor: el contenedor es `sticky` y ya sitúa el menú, así que el JS no le cambia el `position`. Ni el botón ni el menú toman el foco, para que el teclado del móvil no se cierre a mitad de la pulsación.
- Mantener pulsado (el mismo gesto que una fila de Food, §9.3.1) abre un pequeño menú con `+½`, `+2` y `−1`. `−1` no aparece cuando solo queda una unidad.
- Lo nuevo se sigue contando al asistente: en cuanto lo añade, tiene su botón.
- La fila se vuelve a pedir tras cada mensaje del asistente y tras cada pulsación.

**Fotos** (decisión del usuario, 2026-11-15: hasta 4 por mensaje, con miniaturas). El botón de la cámara adjunta fotos de un plato o de una etiqueta nutricional, por ejemplo la cara delantera y la trasera de un envase.

- Se pueden elegir varias a la vez o añadirlas de una en una, hasta 4. Las que pasan de 4 no se añaden, y un toast lo dice.
- Encima del texto aparece una miniatura de cada una, con una × para quitarla. Mientras una se prepara, su miniatura sale atenuada y el botón de enviar espera.
- Antes de enviarlas, el navegador reduce cada una a 1568 px por el lado mayor y la convierte en JPEG (`code_conventions.md` §8.12, coste).
- Si el navegador no puede, envía la original, y el servidor rechaza el mensaje si lleva más de 4 fotos, o una de más de 3,75 MB o que no sea JPEG, PNG o WebP según sus bytes. Las que acepta las vuelve a codificar sin metadatos antes de enviarlas al modelo (`code_conventions.md` §8.12).
- Se guardan desde el 2026-11-18 (`code_conventions.md` §11.2.10), pero el historial sigue mostrando la píldora `Photo` o `N photos`, sin las imágenes.

**Tarjetas.**

- `Added to the cart`: una línea por alimento, plato, receta o estimación añadidos, con sus gramos, sus hidratos y cómo se obtuvo la cantidad (U2, con las etiquetas de §9.4), y el botón `Review`, que abre el carrito.
- `Changed in the cart`: una línea por cambio en la comida, un plato o un alimento (`code_conventions.md` §8.12, **Edición de la comida**), con lo cambiado y su valor nuevo, y el botón `Review`.
- `Stored in the fridge` / `Stored in the freezer` (`code_conventions.md` §8.12, **Nevera**): una línea por táper guardado, con su nombre, su sitio y sus gramos, y el botón `Fridge`, que abre Food en la nevera. Lo sacado de un táper sale en `Added to the cart`, como `From the fridge`.
- `Remove from the cart?` (`code_conventions.md` §8.12, **Quitar del carrito**): una fila por alimento que DiaBot propone quitar, con su nombre, sus gramos y el botón `Remove` (borde y texto `danger`). Pulsarlo la quita sin pasar por el modelo y la fila pasa a tachada con `Removed`; la barra y los `+1` se vuelven a dibujar. Al reabrir el chat, una fila que ya no está en la comida sale como quitada. En un chat pasado, solo lectura, sin botón.
- `New food to review`: el nombre del alimento propuesto, de dónde sale ("Read from the label", "From the food composition table", "From Open Food Facts" o "Estimated by the assistant") y el botón `Review and save`, que abre el formulario de alta de un alimento precargado con todos los campos del borrador (`code_conventions.md` §8.12, **Alimentos nuevos**). `More details` se abre solo si el borrador rellena algo de dentro.
  - Una etiqueta añade al formulario la nota "Read by the assistant from the label. Check every value before saving."; una estimación, "Estimated by the assistant. Check every value before saving.". `Macros from` empieza en el valor de la tabla de §8.12.
  - Ciqual y OFF usan su precarga de siempre (§9.4), con lo que el asistente añada encima.
  - El borrador del navegador del formulario (§7.14) es propio de cada borrador del asistente: no recupera lo escrito en otro formulario de alta.
  - Guardar vuelve a la conversación (`/assistant?conversation_id=`) en vez de a Food, y allí el usuario le pide que lo añada.
- `New dish to review`: el nombre del plato, "Dish proposed by the assistant" y el botón `Review and save`, que abre `New dish` relleno con el borrador (`code_conventions.md` §8.12, **Platos manuales**), con una nota según su `macros_source` ("Estimated by the assistant. Check every value before saving." y equivalentes). Guardar vuelve a la conversación, como el alta de un alimento.
- `New recipe to review`: el nombre de la receta, el número de ingredientes y el botón `Review and save`, que abre `New recipe` relleno (`code_conventions.md` §8.12, **Recetas**).
  - Debajo de los campos de siempre, una sección `Ingredients` de solo lectura con la nota "Proposed by the assistant. They are added when you save; edit them afterwards in the recipe.". Lista los platos de la receta (solo si hay más de uno) y en cada uno una línea por ingrediente: nombre, gramos y su preparación (`griddle · solid · weighed cooked`). Un plato manual nuevo lleva la etiqueta `New dish` y sus hidratos estimados.
  - Guardar crea todo y abre la receta, como el alta de siempre. Si un ingrediente ya no existe, el formulario lo dice; si la receta o un plato nuevo choca con un nombre que ya tienes, se avisa como en el alta de siempre (`409`). En los dos casos no se crea nada.
- `New food added` y `New dish added` (decisión del usuario del 2026-11-21), con la etiqueta `To review`: un alimento o plato provisional creado y añadido. No se confunden con los borradores (`New food to review`), que aún no existen ni están en la comida. Un resumen de lo que ha rellenado el asistente (nombre, marca u origen, hidratos por 100 g, de dónde salen los datos y los gramos añadidos) y el botón `Review`, que abre su formulario de edición; guardar vuelve a la conversación. Una vez revisado, la tarjeta lo dice en vez de mostrar `Review`.
- Sugerencia de **Repeticiones** (`code_conventions.md` §8.12): el nombre de lo repetido, cuántas veces en 90 días y `Save as dish` (o `Save as recipe`). Al pulsarlo, el botón queda desactivado y la tarjeta enlaza a lo creado.
- Al terminar un turno con provisionales sin revisar en la comida, la respuesta del asistente lo recuerda en una línea.

Las tarjetas se leen de los resultados guardados de las herramientas, así que una conversación reabierta muestra las mismas.

**Cómo escribir** (decisión del usuario, 2026-11-13). Bajo la introducción de una conversación vacía, un `<details>` plegado, `How to write`, con la guía breve en inglés: mencionar con `/` y dar la cantidad; una frase de preparación vale para todos los alimentos que nombra; las palabras de cocción y su valor; decir "weighed cooked" o "raw" en arroces, pastas y legumbres; conservación, textura y madurez; hora y platos; y cómo pedir un alimento nuevo (foto de la etiqueta o "estímalo") o una receta (pegar el texto, y "quick add" o "manual" para los ingredientes que no tienes).

**Mencionar un alimento con `/`.**

- Escribir `/` al principio del texto o después de un espacio o de un salto de línea abre, **encima del compositor**, una lista de sugerencias, como los comandos de Claude. Lo que se escribe después de `/` filtra la lista; admite espacios, porque los nombres los tienen.
- Busca entre lo que el usuario ve en Food: alimentos (`catalog`), platos (`manual_intake`, sin añadidos rápidos) y recetas, con la misma regla de visibilidad y la misma búsqueda sin acentos ni mayúsculas (`code_conventions.md` §11.7). La búsqueda abarca el nombre, y también la marca en los alimentos y el origen en los platos.
- **Orden.** Con texto, primero por cómo encaja el nombre (igual, empieza por, lo contiene, solo se parece) y, dentro de cada grupo, favoritos, después los más comidos en los últimos 60 días, y por último por nombre. Sin texto después de `/`, solo salen los favoritos y los comidos en esos 60 días, en ese orden. Las recetas no tienen uso, porque lo consumido no las referencia (`code_conventions.md` §11.7). Se devuelven como mucho 20.
- Cada fila es una fila `control` compacta (§8): el nombre (dos líneas como mucho, como en §9.6), y debajo el tipo (`Food`, `Dish` o `Recipe`), la marca u origen y, en alimentos y platos, los hidratos (por ración si la tiene, si no por 100 g). Una receta no los muestra: salen de sus ingredientes. Una estrella marca los favoritos. La lista enseña unas 6 filas y el resto con scroll propio.
- **Teclado**: ↑ y ↓ mueven la selección, que empieza en la primera fila; Tab o Enter eligen la seleccionada; Esc cierra la lista sin elegir. Con la lista cerrada, Enter hace un salto de línea y se envía con el botón. **Toque o clic** en una fila la elige.
- Al elegir, el texto `/consulta` se sustituye por `/Nombre del alimento ` y el alimento se añade a las menciones del mensaje, que se muestran como píldoras encima del `<textarea>` con una × para quitarlas. Quitar la píldora borra también su `/Nombre` del texto; borrar el texto quita la mención.
- La lista se cierra sola si se borra el `/`, si el cursor sale de la consulta o si, tras un espacio, la consulta deja de dar resultados (se queda como texto normal, que el asistente interpreta).
- Las menciones se envían como `entry_type` + `entry_id`, nunca como nombre, y el servidor las vuelve a leer (`code_conventions.md` §8.12).

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /assistant/mentions?q=` (al escribir tras `/`, con un retraso de 150 ms; una respuesta que llega tarde se descarta) | `#assistant_mentions` | `innerHTML` | las filas, o una línea `No foods match` | sin sesión: `401`, por el canal de errores |

| `GET /assistant/thread?conversation_id=` (tras un envío fallido, para mostrar lo que ya hicieron las rondas anteriores) | `#assistant_thread_box` | `innerHTML` | la conversación, y la barra de la comida fuera de banda | comida confirmada o borrada: `404` por el canal de errores |
| `POST /assistant/history/{id}/repeat` (`Repeat today`) | — | `none` | `HX-Redirect` al chat de la comida nueva | comida que no es del usuario o no confirmada `404`: toast |
| `POST /assistant/conversations/{id}/hide` (papelera de un chat sin comida en la lista) | la fila | `outerHTML` | vacío: la fila desaparece | chat que no es del usuario `404`: toast |
| `POST /assistant/preparation/{portion_id}` (`field`, `value`, `conversation_id`; al pulsar una píldora de preparación) | `#assistant_meal_bar` | `outerHTML` | la barra con el valor elegido | no ofrecido o fila que ya no está `404`, comida confirmada `409`: toast |
| `POST /assistant/remove/{portion_id}` (`conversation_id`; al pulsar `Remove`) | la fila de la tarjeta (`closest [data-removal-row]`) | `outerHTML` | la fila quitada; la barra y los `+1` fuera de banda | no propuesta o ya quitada `404`, comida confirmada `409`: toast |
| `POST /assistant/message` (`multipart/form-data`: `message`, `mentions`, `photo` (repetido, hasta 4), `intake_event_id`, `conversation_id`) | `#assistant_thread` | `beforeend` | el mensaje con `Thinking`, que pregunta por su respuesta | validación `422`, conversación ajena `404`, otro mensaje respondiéndose `409`: status, cuerpo vacío y toast |
| `GET /assistant/turn/{id}` (cada 2 s, desde el bloque `Thinking`) | el propio bloque | `outerHTML` | `204` mientras espera; el turno, con el id de la conversación, la fila `+1` y la barra de la comida fuera de banda y, si creó la comida, la lista de chats; o el bloque de fallo | sin sesión `401` |

Las cuatro exigen el header `HX-Request` (`403` si falta). Repetir un envío es un mensaje nuevo: el asistente puede volver a añadir lo mismo, y la copia se quita en el carrito.

### 9.12 Guía de criterios (decisión del usuario, 2026-11-21)

Para que los campos de calidad del dato se rellenen siempre con el mismo criterio, la web explica qué significa cada valor que hay que elegir, en Ajustes y junto a cada selector.

**De dónde sale el texto**

- La norma son las convenciones: `study_conventions.md` §6.3 (U1, U2, madurez, fracción comida) y `measurement_conventions.md` (§4.4 lo comido, §5.2 el peso en cocido). La guía es su versión corta, en inglés (§7.12): una línea por valor, sin detalle técnico.
- Todo el texto está en un solo sitio, `domain/guide.py` (desde el 2026-11-22, para que también lo lea DiaBot, `code_conventions.md` §8.12), y de ahí salen la página de Ajustes, los pop-ups (`components/guide.py`) y las respuestas del asistente. No se escribe una definición en un componente ni se lee de los `.md`.
- Cada tema recorre su enum, así que un valor nuevo aparece solo. Si no tiene definición, la guía dice `Definition pending.`. Quien añade o cambia un valor (por ejemplo, en U2) escribe su línea de la guía en el mismo cambio.
- Un tema cuyas definiciones aún no están acordadas se marca como pendiente (`Pending`) y lista sus valores sin definición. Hoy lo están `Cooking`, `Conservation` y `Final state` (`study_conventions.md` §6.3, **Preparación de una porción**).

**En Ajustes**

- El botón `Guide` abre `/settings/guide`, con `Back` a Ajustes (§5). Rediseño del 2026-11-21 (decisión del usuario):
  - Arriba, fija y pegada al borde superior (sin margen), la cabecera de subpágina de Ajustes (`components/settings/subpage.py`, la misma que Tags, §9.10): barra de vidrio con `Back`, el título y el buscador. Debajo del buscador, una línea dice cuántos resultados hay y en cuántos apartados.
  - El índice y cada apartado van en su propio contenedor (`web_container`), como el resto de la app.
  - Después, el índice (`Contents`): cada tema numerado (`01`, `02`…) con cuántas opciones tiene. Pulsarlo baja a su apartado dentro de la página, sin cambiar la URL ni añadir entradas al historial.
  - Debajo, un apartado por tema: número, título, qué se elige y una lista de definiciones (opción y significado), separadas por líneas finas, sin tarjetas. Cada apartado acaba en `↑ Contents`, que vuelve al índice.
  - **Buscar** filtra en la página (`static/js/guide.js`), sin distinguir mayúsculas ni acentos: una opción coincide por su nombre, su definición o el título de su tema. Se ocultan los temas sin resultados, y en el índice aparecen bajo cada tema las opciones que coinciden, con enlace a cada una. Con un solo resultado el índice se oculta, y el resultado sigue bajo el título de su tema. Enter lleva al primero.

**Junto a cada selector**

- Un botón `?` pequeño junto a la etiqueta del campo abre el pop-up `guide_modal` con solo ese tema, o con el grupo de preparación (cocción, estado final, conservación y madurez). No se sale de la página.
- El pop-up está una sola vez en toda la web, fuera de `#main_content` (`render_page`, `components/ui.py`), así que un repintado de la página no lo borra. Se construye con `ModalLayer` (§8) y su contenido se pide al servidor cada vez, como el de rescate (§9.6). Al abrirse desde otro pop-up (el `Adjust` del carrito) queda encima, y al cerrarlo se vuelve al de debajo, tal como estaba.
- El botón no envía ningún campo del formulario en el que está (`hx-params="none"`) y no navega.
- En los formularios de alta y edición, el `?` que ya tenía cada campo (§9.1) abre la guía en los campos que tienen tema, en vez de su aviso de texto.
- Dónde está hoy: `Amount from` (carrito, ficha de un alimento) y `Amount usually from` (formularios); `Macros from` (formularios); la preparación (pop-up `Adjust` del carrito, `Preparation` de la ficha, ingredientes de una receta, paso previo de una receta, `Ripeness` de la línea de rescate) e `Initial state` (formularios); `Weighed cooked` (carrito, ficha, receta); `Eaten` (confirmar en el carrito). Un selector nuevo de uno de estos campos lleva su `?`.

| Acción | `hx-target` | `hx-swap` | Éxito | Error |
|---|---|---|---|---|
| `GET /settings/guide/{topic}` | `#guide_modal_body` | `innerHTML` | el tema; al llegar se abre el pop-up | sin sesión: `401`; tema desconocido: `404`. Por el canal de errores |

Exige el header `HX-Request` (`403` si falta).


### 9.13 Cartas guardadas, `Menus` (decisión del usuario, 2026-11-22)

Lo que DiaBot ha guardado de las fotos de cartas de restaurante (`code_conventions.md` §8.12, **Cartas**; tabla `menu_item`, §11.2.12). No es tan importante como Food, así que no ocupa sitio en la cabecera ni en las píldoras.

- **Entrada.** Un botón cuadrado con el icono de una carta abierta, a la derecha del buscador de Food y con su mismo alto (`web_container`, `aria-label` "Restaurant menus"). Sale siempre, aunque no haya cartas; la página explica entonces cómo se guarda una. Abre `/food/menus`.
- **En la búsqueda de Food.** En la pestaña de búsqueda (`all`), con texto, después de los resultados del usuario y antes de Ciqual y Open Food Facts, un bloque `From your menus` con como mucho `MENU_FOOD_SEARCH_ROWS` (3) platos. Usan la misma fila que el resto de resultados: nombre; sitio, sección y precio en gris; y la descripción. Si hay más, `See all in Menus ›` abre Menus con esa búsqueda. Tocar un plato abre su carta con el plato buscado. Así no se acumulan muchas filas de otra fuente.
- **`/food/menus`, una sola página filtrada por su URL**: `q` (búsqueda), `place` (una carta) y `section`, cada uno opcional.
  - **Cabecera:** `‹ Food`, `Menus`, el buscador de platos (nombre, descripción y sitio, sin acentos; reemplaza solo la lista y la URL) y una fila de controles.
  - **Fila de controles:**
    - Un botón con el sitio elegido (`All places ▾`) que abre un pop-up `Places`. Ahí están `All places` y cada sitio con cuántos platos tiene y cuándo se guardó, el elegido en negrita y con ✓. Desde 8 sitios lleva su propio buscador y la lista hace scroll, así que aguanta las cartas que se acumulen. Elegir un sitio conserva la búsqueda y quita la sección.
    - Las secciones, con el estilo de las píldoras de Food (tinta la elegida): `All` y solo las secciones que tienen algún plato, en una fila con scroll lateral.
  - **Lista:**
    - Con un sitio elegido, sus platos por sección, cada uno con su papelera, y al final `Delete this menu` en rojo. Las dos piden confirmación (`ConfirmActionModal`), porque el borrado no se puede deshacer. Borrar el último plato vuelve a la lista sin sitio.
    - Sin sitio elegido, un grupo por sitio. Sin búsqueda ni sección, cada grupo muestra `MENU_PLACE_PREVIEW` (4) platos con su sección y `All N ›` para abrir ese sitio. Con búsqueda o sección, todos los que coinciden. Aquí no se borra.
  - **Sin cartas:** una línea que explica cómo se guardan. **Sin coincidencias:** `No dishes match "…"`.
- **No se editan a mano.** Para cambiar o completar una carta se manda otra foto a DiaBot, que actualiza los platos que ya están. La página lo dice bajo los controles.

| Acción | Destino | Swap | Respuesta | Error |
|---|---|---|---|---|
| `GET /food/menus` (`q`, `place`, `section`) | página; el buscador, `#menus_list` | — / `outerHTML` | la página en ese estado; un sitio que no es del usuario o una sección desconocida se ignoran | — |
| `POST /food/menus/items/{id}/delete` | la fila | `outerHTML` | vacío: la fila desaparece; si era el último de su sitio, `HX-Location` a la lista | plato que no es del usuario `404`: toast |
| `POST /food/menus/delete` (`place`) | — | — | `HX-Location` a la lista, con aviso | sitio sin platos del usuario `404`: toast |

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
- **La excepción se extiende al bloque de preparación por confirmar** (§7.1 y §9.4; decisión del usuario del 2026-11-24, que pidió que desaparezca con una animación fluida). Al pulsar el tick, el bloque se desvanece y su altura baja a 0 en 220 ms. En el carrito, la tarjeta se repinta cuando acaban a la vez la animación y la respuesta, así que el plegado no se ve como un salto ni como el parpadeo de un repintado. Con movimiento reducido no hay animación ni espera.
- Las utilidades de movimiento de los pop-ups (desvanecer, entrar subiendo, animar la altura de la tarjeta) están una sola vez en `static/js/modal.js` (`window.dbModalMotion`) y las usan el rescate y el menú de acciones. Un pop-up nuevo que se anime las reutiliza en vez de copiarlas.
- **Respuesta al toque** (2026-11-25). Una fila pulsable (`food_entry` con `cursor-pointer`) se hunde y se atenúa al tocarla, salvo que lo tocado sea un control de dentro. El aviso `Loading...` a pantalla completa solo aparece si la respuesta tarda más de 400 ms (`page_loading.js`), y no desenfoca la página.
- Los botones (`web_button`) se hunden un poco al pulsarlos (`active:scale-95`). En móvil se quita el resaltado azul del toque.
- Los repintados parciales (una tarjeta del carrito tras cambiar un valor) **no** se animan: pasan a cada cambio y un parpadeo ahí molesta más de lo que ayuda.

## 11. App instalable

Decisión del usuario del 2026-11-25. La web se puede instalar en el móvil y se abre a pantalla completa, sin la barra del navegador.

- **Un solo sitio.** El manifest (`/manifest.webmanifest`, ruta pública porque el navegador lo pide sin cookies) y las etiquetas del `<head>` salen de `components/app_head.py`. Las dos plantillas de página (`components/ui.py` y la de acceso, `routes/auth_routes.py`) usan `APP_HEAD_HTML`; una plantilla nueva también.
- **Iconos** `static/images/ui/app_icon_{180,192,512}.png` (decisión del usuario del 2026-11-25, opción C entre cuatro): la gota del favicon sobre las manchas de color del fondo, con el 70 % del alto. `app_icon_maskable_512.png` es el mismo con la gota al 60 %, para que Android pueda recortarlo en círculo. Si cambia el dibujo se regeneran los cuatro y sube el `?v=` de `app_head.py`; el iPhone solo toma el icono nuevo al volver a añadir la app.
- **Color.** `theme_color` y `background_color` son el token `page`, escrito en hexadecimal porque un manifest no puede leer el CSS (excepción a §8).
- **Márgenes seguros.** La página ocupa la pantalla entera (`viewport-fit=cover`), así que un elemento fijo junto a un borde suma el `env(safe-area-inset-*)` de ese borde. La isla conserva sus 40 px mientras sean suficientes.
- **Instalada**, tirar hacia abajo no recarga la página.
- **Sin service worker.** Nada se guarda para usarse sin conexión: las páginas llevan datos de salud. Añadir uno exige acordar antes qué puede guardar y cómo se borra al cerrar la sesión.
