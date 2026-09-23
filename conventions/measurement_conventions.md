# Convenciones de datos y unidades - DayBetes

Este documento define cómo se recogen, convierten, almacenan, calculan y muestran las cantidades y mediciones de DayBetes.

Su objetivo es que los datos recogidos durante la fase personal puedan compararse y analizarse posteriormente sin confundir unidades, precisión, valores desconocidos o datos estimados.

Este documento complementa `conventions/code_conventions.md`:

- `code_conventions.md` define cómo se construye el software.
- Este documento define qué significa cada dato y cómo se representa.

La unidad almacenada debe ser única para cada concepto, aunque la interfaz permita al usuario introducir o visualizar otra unidad.

## 1. Principios generales

- Cada campo cuantitativo tiene una unidad canónica documentada.
- La conversión a la unidad canónica ocurre antes de guardar el dato.
- Los cálculos internos utilizan las unidades canónicas, nunca unidades de presentación.
- La interfaz puede mostrar una unidad alternativa, pero no cambia la unidad almacenada.
- Toda conversión usa un helper central y una constante documentada.
- No se repiten fórmulas de conversión en componentes, rutas y JavaScript.
- El valor original introducido por el usuario no se sobreescribe cuando sea necesario conservarlo para trazabilidad.
- Todo valor debe distinguir entre medido, estimado, calculado, importado y desconocido cuando esa diferencia afecte al análisis.
- Los redondeos se realizan en un punto definido y no accidentalmente en cada capa.
- Las unidades forman parte del contrato del campo, no son únicamente una etiqueta visual.

## 2. Tipos de valor

Cada medición o cantidad puede tener estos estados:

- **Valor válido**: existe una cantidad interpretada en la unidad canónica.
- **Cero**: se conoce que la cantidad es exactamente cero.
- **Desconocido (`NULL`)**: no se conoce o no se ha registrado.
- **No aplicable**: el concepto no corresponde a ese registro.
- **Estimado**: existe un valor, pero no se ha medido directamente.
- **Calculado**: el valor ha sido derivado por DayBetes.
- **Importado**: procede de una fuente externa.
- **Borrado explícito (`CLEAR`)**: se ha solicitado eliminar un valor previamente almacenado.

No se debe utilizar `0` para representar “desconocido”, ni `NULL` para representar automáticamente “cero”.

Cuando `NULL` y “no aplicable” deban distinguirse para el análisis, se añadirá un campo de estado o de disponibilidad. No se inventarán valores numéricos especiales como `-1`, `9999` o `0.0` para representar ausencia.

## 3. Precisión y redondeo

Cada campo cuantitativo debe definir:

- precisión de entrada;
- precisión de almacenamiento;
- precisión de cálculo;
- precisión de presentación;
- regla de redondeo;
    - tolerancia permitida en comparaciones.

La interfaz puede mostrar menos decimales que los almacenados. La presentación no debe alterar el valor usado en cálculos posteriores.

Reglas generales:

- No redondear cada ingrediente antes de calcular el total salvo que el dominio lo exija.
- Calcular primero con la máxima precisión disponible y redondear el resultado final.
- No comparar valores de coma flotante mediante igualdad exacta.
- Usar una tolerancia explícita en comparaciones de `REAL`/`float`.
- Usar `NUMERIC`/`Decimal` para campos que participen directamente en dosis, snapshots clínicos o decisiones terapéuticas.
- Mantener `REAL` temporalmente para los campos nutricionales existentes que solo se utilicen en registro o análisis exploratorio.

## 4. Masa y cantidades de alimentos

### 4.1 Unidad canónica

La unidad canónica de masa para alimentos es el **gramo (`g`)**.

Se aplica a:

- `portion_detail.amount`;
- `manual_intake.amount_g`;
- `ingested_amount`;
- cantidades disponibles en nevera;
- peso de tuppers;
- cantidades de porciones;
- cantidades restantes.

Los nombres de campos que representen masa deben terminar preferiblemente en `_g` cuando la unidad no sea obvia.

`portion_detail.amount` es una excepción consciente a esa preferencia (decisión 2026-09-18): la columna sirve a los tres destinos de la tabla (`intake_event`, `recipe`, `fridge`) y su unidad no es ambigua, porque es la canónica de esta sección y está fijada en §4.4.

`total_amount` (suma de `amount` de las porciones de un evento) no es una columna almacenada: se calcula en vivo, en cualquier estado del evento, cuando haga falta (decisión 2026-09-10, ver §4.4 y §6.9).

### 4.2 Unidades de entrada permitidas

La interfaz puede admitir:

- gramos (`g`);
- porciones (`portion`);
- porcentaje (`%`) cuando se aplique sobre una cantidad total;
- libras (`lb`);
- onzas (`oz`).

Todas se convierten a gramos antes de persistir.

Conversiones:

```text
1 lb = 453.59237 g
1 oz = 28.349523125 g
```

Las constantes deben definirse en un único helper. No redondear la conversión intermedia a un número entero.

### 4.3 Porciones

Una porción no es una unidad física universal. Su equivalencia depende del alimento.

Si un alimento tiene `default_portion = 120 g`:

```text
1 portion = 120 g
2 portions = 240 g
```

La equivalencia debe obtenerse del registro del alimento, nunca de una constante global.

No almacenar “1 porción” como si fuera `1 g`. El valor persistido siempre debe ser la masa convertida.

### 4.4 Cantidad de una porción, cantidad servida y cantidad ingerida

`portion_detail` tiene **una sola columna de cantidad: `amount`** (decisión 2026-09-18, que sustituye el criterio de dos columnas vigente hasta entonces). Es la cantidad de ese ingrediente en su destino, sea un evento, una receta o un tupper de nevera, y por eso el nombre no menciona el plato.

- `amount` (`portion_detail`): cantidad servida o puesta en el plato **mientras el evento está `planned`**. En el instante de `confirm` (transición `planned -> consumed`), se sobrescribe **una única vez** por la cantidad realmente consumida de ese ingrediente (ver fórmula abajo). Desde ese momento, para un evento `consumed`, `amount` deja de significar "lo servido" y pasa a significar "lo consumido". Las porciones de un evento confirmado siguen siendo editables (§6.9.3); lo que esa edición obliga a recalcular está descrito allí.
- **cantidad cocinada**: no es una columna. Es un campo del formulario (`total_amount_g`) que solo existe en el instante de emplatar, para calcular el sobrante que se guarda en `fridge`. `portion_detail` nunca la persiste (decisión 2026-09-18).
- `total_amount`: suma de `amount` de las porciones de un evento, calculada siempre en vivo (§4.1), nunca almacenada. Antes de confirmar es la cantidad servida total; en el instante de confirmar es el denominador usado para interpretar `ingested_value` cuando se introduce en gramos.
- `ingested_amount` (`intake_event`): único campo persistido a nivel de evento con el total realmente consumido. Es un snapshot (§6.9) calculado en el propio `confirm` como `total_amount (en ese instante) * fracción`.
- `fracción`: número en `(0, 1]` que representa la proporción del plato servido que se ha consumido. Se obtiene de los campos `ingested_value`/`ingested_unit` del formulario de confirmación: si `ingested_unit = "%"`, `fracción = ingested_value / 100`; si es gramos, `fracción = ingested_value_g / total_amount`. Si el usuario no rellena `ingested_value`, `fracción = 1.0` (se asume que se ha comido todo el plato). Un valor fuera de `(0, 1]` se rechaza como `validation_error` (`422`), no se recorta silenciosamente. **`0` no es un valor admisible** (decisión 2026-09-22): si no se ha comido nada del evento, el evento se borra, no se confirma.
- cantidad sobrante por ingrediente: `amount_original - amount_final` (equivalente a `amount_original * (1 - fracción)`). Solo puede calcularse en el propio instante de `confirm`, antes de sobrescribir la fila, porque `amount_original` no se conserva después. Mientras no exista la funcionalidad de nevera (`fridge`, tabla sin implementar — `audit/deuda_pendiente.md`), este sobrante no se persiste en ningún sitio: se pierde igual que se perdía antes de esta decisión.

Excepción documentada a la regla general de §1 ("el valor original introducido por el usuario no se sobreescribe cuando sea necesario conservarlo para trazabilidad"): esta sobreescritura de `amount` en `confirm` es la única excepción admitida, limitada a esta tabla y a esta transición de estado (decisión 2026-09-10). Ningún otro campo ni tabla puede apoyarse en este precedente sin una decisión propia.

Reglas:

```text
0 < amount <= 100000        # cota de cordura superior, la misma de §6.9.2
amount finito               # NaN e Infinity se rechazan con 422 y con CHECK
0 < fracción <= 1
ingested_amount = total_amount (en el instante de confirmar) * fracción
```

La cota inferior es **`> 0`** (decisión 2026-09-22): una porción de cantidad `0` no describe
nada. Si un ingrediente o una tanda no se ha consumido, se borra —el borrado tiene ruta propia
desde esa misma decisión—, no se deja a cero. Constraint:
`ck_portion_detail_amount_range CHECK (amount > 0 AND amount <= 100000)`.

### 4.5 Offset de una porción respecto al evento (decisión 2026-09-18)

`portion_detail.offset_minutes` es la diferencia en minutos entre el `meal_time` del evento y el momento en que ese ingrediente se consume, **guardada como entero literal** y fijada al crear la porción.

- **No se recalcula nunca** cuando cambia el `meal_time` del evento. El offset es un dato propio de la porción, no una función del `meal_time`: el análisis obtiene la hora real restándolo al `meal_time` vigente en ese momento, de modo que si la hora del evento cambia, el resultado se mueve con ella.
- Admite valores negativos y positivos. Rango: `-300 <= offset_minutes <= 300`, con `CHECK`. Es una cota de cordura para que un valor corrupto no pase por plausible, no una frontera de negocio.
- El valor de cada porción **se hereda de la tanda** a la que se añade (§4.6.2), pero una vez escrito es independiente de ella: `intake_plate.offset_minutes` es una plantilla, no un dato clínico.

### 4.6 Tandas (platos) dentro de un evento (decisión 2026-09-19)

Un `intake_event` es **una sola unidad glucémica**: un tipo de comida, un `meal_time`, normalmente un bolo. Cuando esa comida se come en varios momentos —primer plato, segundo, postre media hora después— **no se parte en varios eventos**: se subdivide en **tandas** (platos) dentro del mismo evento, para que todos los offsets sigan midiéndose contra el mismo `meal_time`.

#### 4.6.1 Modelo

```text
intake_plate
  id
  intake_event_id  -> intake_event  ON DELETE CASCADE
  name             VARCHAR(255)   -- NULL = nombre derivado (4.6.3)
  offset_minutes   INTEGER        -- plantilla heredada por las filas nuevas (4.6.2)
  created_at / updated_at

portion_detail
  plate_id         -> intake_plate  ON DELETE RESTRICT
                      NOT NULL cuando intake_event_id NOT NULL
                      NULL para los destinos fridge y recipe
```

Una tanda pertenece a un evento y solo existe dentro de él. Un evento sin alimentos no tiene ninguna tanda: la primera se crea implícitamente al añadir el primer alimento.

La tabla **no tiene columna de posición**. El orden de las tandas dentro de un evento es `ORDER BY offset_minutes NULLS LAST, id`: la de offset menor primero, y a igualdad de offset la creada antes. El orden es por tanto **cronológico real y derivado del dato**, no una etiqueta manual que pueda contradecirlo; reordenar las tandas se hace cambiando el offset, no arrastrándolas.

#### 4.6.2 Qué offset es el válido

`portion_detail.offset_minutes` (§4.5) sigue siendo **el único valor autoritativo**: es el que describe cuándo se comió ese alimento concreto y el que usa el análisis. Conserva la semántica de la decisión del 2026-09-18 — entero literal, fijado al insertar, nunca recalculado, rango `-300..300`.

`intake_plate.offset_minutes` **no es un dato clínico**, es una plantilla:

- Al insertar una porción en una tanda, la porción **hereda** el offset de la tanda. Ese es el mecanismo que elimina la fricción original: se fija el offset una vez por tanda y los ingredientes entran ya con el valor correcto, en vez de corregirlos uno a uno.
- Después de heredarlo, **fila y tanda son independientes**. Editar el offset de una porción concreta no toca la tanda (caso legítimo: un ingrediente del plato comido antes o después que el resto), y editar el offset de la tanda **no** reescribe sus filas.
- La propagación a las filas existentes es una acción **explícita** del usuario (`Apply all`, `frontend_conventions.md` §7): fija el offset de la tanda y lo escribe en todas sus porciones.
- Si se borrase `intake_plate.offset_minutes`, no se perdería ningún dato del estudio, solo la comodidad. Esa es la prueba de que no es un dato de la comida.

La tanda creada implícitamente con el primer alimento nace con el offset autocalculado de ese alimento (diferencia entre `meal_time` y el instante de añadirlo, §4.5).

#### 4.6.3 Nombre de la tanda

`name` nulo significa **nombre derivado**, calculado en el render a partir de los ingredientes de la tanda por orden de inserción:

| Ingredientes en la tanda | Nombre mostrado |
|---|---|
| 0 | `Empty plate` |
| 1 | la primera palabra de su nombre (`Arroz`) |
| 2 o más | la primera palabra de los dos primeros, separadas por coma (`Arroz, Pechuga`) |

Se toma la **primera palabra** de cada nombre, no el nombre completo: `Arroz basmati Hacendado` aporta `Arroz`. El objetivo es un título corto y reconocible al releer el histórico, que es también la razón de preferir esto a un ordinal puro (`First`, `Second`): describe qué se comió, no en qué posición estaba.

Por el mismo motivo, la tanda vacía **no se llama `First`** (corrige la primera redacción de esta sección, 2026-09-19): una tanda sin ingredientes puede ser la segunda o la tercera del evento, así que un ordinal sería falso. `Empty plate` describe lo único que se sabe de ella.

El único literal del nombre derivado —el de la tanda vacía— va **en inglés**, como el resto de la interfaz (`frontend_conventions.md` §7.12). Los otros dos casos no son literales: salen del nombre del alimento, en el idioma en que se guardó.

El nombre derivado **no se guarda** y se recalcula solo: cambia al añadir, borrar o mover ingredientes. En cuanto el usuario escribe un nombre, `name` deja de ser nulo y el nombre queda congelado; borrarlo devuelve la tanda al nombre derivado.

#### 4.6.4 Unicidad de un ingrediente dentro de una tanda

La clave única de la decisión del 2026-09-18 pasa de `(intake_event_id, origen, origen_id, cooking, conservation, final_state)` a:

```text
UNIQUE NULLS NOT DISTINCT (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state)
WHERE plate_id IS NOT NULL
```

`plate_id` sustituye a `intake_event_id` porque la tanda ya determina el evento. Sin este cambio, el mismo pan en el primer plato y en el segundo se fusionaría en una sola fila. El resto de la regla se mantiene: añadir un alimento que ya está **en esa tanda** con los tres atributos de preparación iguales suma las cantidades en la fila existente; si alguno difiere, se crea una fila aparte.

**`is_cooked_weight` forma parte de la clave** (2026-09-23; modifica la regla de fusión de la decisión 2026-09-19). El índice queda así:

```text
UNIQUE NULLS NOT DISTINCT (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight)
WHERE plate_id IS NOT NULL
```

`amount` guarda lo que el usuario pesó (§5.2), y 100 g pesados en crudo y 100 g pesados en cocido son cantidades de alimento distintas: sumarlas en una fila con un único valor de la casilla convertiría mal una de las dos. Por eso la misma comida pesada en crudo y en cocido son dos filas aparte, y solo se suman cuando la casilla coincide.

**Es un índice único parcial, no un constraint de tabla, y el `WHERE` no es opcional.** `plate_id` es nulo en las porciones con destino `recipe` y `fridge`, y con `NULLS NOT DISTINCT` esos nulos se consideran iguales entre sí: sin el filtro, el mismo alimento con la misma preparación en **dos recetas distintas** chocaría como si fuera un duplicado. La unicidad es dentro de la tanda y solo aplica a las porciones que tienen tanda.

**La fusión es real en la base, no solo visual** (decisión 2026-09-19). Antes de esta regla, añadir dos veces el mismo alimento insertaba dos filas y `group_portions` las sumaba solo al pintar; la fusión física ocurría únicamente si el usuario editaba la cantidad desde el carrito. A partir de aquí, la inserción fusiona en la propia tabla, para que el análisis no tenga que deduplicar.

**Qué ocurre con los campos que no están en la clave al fusionar** (decisión 2026-09-19, cierra el punto que el 2026-09-18 dejaba abierto):

- `amount` **se suma**: es el sentido mismo de la fusión.
- `strictly_weighed` y `macros_quality` **conservan el valor de la fila existente**. Gana lo que ya estaba: la fila lleva ahí desde la primera adición y su calidad de dato ya está afirmada; una adición posterior no sabe más sobre ella. `is_cooked_weight` ya no entra en esta regla: desde el 2026-09-23 es parte de la clave, así que dos filas que se fusionan lo tienen igual.
- `offset_minutes` no necesita regla: dentro de una misma tanda el offset heredado ya coincide.

La misma regla se aplicó retroactivamente al histórico en la migración (§4.6.6).

**La fusión también ocurre al editar la preparación** (decisión 2026-09-20). `cooking`,
`conservation` y `final_state` forman parte de la clave, así que cambiarlos o vaciarlos puede
hacer que la fila coincida con otra hermana de la misma tanda. En ese caso **se suma `amount` en
la fila existente y se elimina la editada**, en la misma transacción: mismo criterio que al añadir
y que al mover entre tandas, y nunca un error de integridad devuelto como `500`. Lo mismo vale para
`is_cooked_weight` (2026-09-23): marcar o desmarcar la casilla en el carrito puede igualar la fila
con otra de la misma tanda, y entonces se fusionan con esta misma regla.

#### 4.6.5 Ciclo de vida

- **Borrar el evento** borra sus tandas (`ON DELETE CASCADE`) y, por la cascada ya existente de `portion_detail.intake_event_id`, sus porciones.
- **Borrar una tanda que tiene porciones está bloqueado** (`ON DELETE RESTRICT`). La interfaz obliga a mover o borrar sus ingredientes antes. Es deliberado: arrastrar las filas a otra tanda automáticamente haría que un click se llevara por delante la mitad de la comida sin que se note.
- **Mover un ingrediente de tanda** es un `UPDATE` de `plate_id`. No modifica su `offset_minutes`: el offset heredado en su día sigue siendo lo que se comió, y si debe cambiar, se cambia explícitamente.
- **Importar una receta a un evento** crea una **tanda nueva** con los ingredientes de la receta dentro.

#### 4.6.6 Migración de los datos existentes

Cada evento existente pasa a tener **una sola tanda**, con `name` nulo (para que el nombre derivado se calcule solo desde sus ingredientes) y `offset_minutes` igual al **menor** de los offsets de sus porciones. Todas sus filas de `portion_detail` reciben ese `plate_id`. No afirma nada nuevo sobre el histórico: agrupa en una tanda lo que hoy ya es un único bloque de ingredientes.

La columna `portion_detail.split_group_id` se elimina en la misma migración (`DROP COLUMN`, hallazgo 16 de `audit/audit_portion_detail.md`): era DDL aplicado a mano, sin ningún valor guardado y sin relación con este diseño.

**Consolidación de los duplicados históricos.** La clave única de §4.6.4 no puede crearse sobre datos que ya la violan (§12.7 de `code_conventions.md`). Verificado el 2026-09-19 sobre la base real: 11 grupos, 24 filas, todos dentro de un mismo evento y clones exactos entre sí —misma cantidad, mismo offset, mismos tres booleanos, `plate_amount` nulo en todas—, producto de añadir el mismo alimento dos o tres veces sin editar después la cantidad. Se consolidan con la misma regla de fusión de §4.6.4: una fila por grupo, con la suma de las cantidades y el resto de campos de la **fila más antigua**. El total de cada comida no cambia, de modo que `ingested_amount`, los macros y las confianzas de los eventos ya confirmados siguen siendo válidos sin recalcularlos.

`plate_amount` se trata aparte porque en el histórico es nulo y la lectura viva usa `COALESCE(plate_amount, amount_g)`: si todas las filas del grupo lo tienen nulo, la fila consolidada lo conserva nulo; si alguna tiene valor, se guarda la suma de `COALESCE(plate_amount, amount_g)`. En los dos casos la cantidad que el código calcula hoy es idéntica antes y después.

## 5. Información nutricional

### 5.1 Unidad canónica por 100 gramos

Los nutrientes del catálogo y de las comidas manuales se almacenan por **100 g de alimento**.

| Campo | Unidad canónica | Tipo de magnitud |
|---|---|---|
| `calories_100g` | kcal/100 g | energía |
| `carbs_100g` | g/100 g | masa |
| `sugars_100g` | g/100 g | masa |
| `fats_100g` | g/100 g | masa |
| `saturated_100g` | g/100 g | masa |
| `proteins_100g` | g/100 g | masa |
| `fiber_100g` | g/100 g | masa |
| `caffeine` | mg/100 g | masa |
| `alcohol` | g/100 g | masa |

Los campos `caffeine` y `alcohol` deben confirmarse con la fuente de datos antes de importar valores. No se debe asumir que un proveedor externo usa la misma unidad solo porque el nombre del campo coincida.

### 5.2 Cálculo para una cantidad concreta

Para obtener un nutriente correspondiente a una cantidad de alimento:

```text
nutriente_total = nutriente_100g * cantidad_g / 100
```

En un `intake_event`, `cantidad_g` es `portion_detail.amount` (§4.4), que es la única columna de cantidad de la tabla.

**Peso pesado en cocido** (decisión 2026-09-18): si la porción tiene `is_cooked_weight = TRUE`, la cantidad se convierte a peso en crudo **solo dentro de este cálculo**, aplicando el `cooking_factor` del alimento de `catalog`; `amount` sigue guardando lo que el usuario pesó y nunca se sobrescribe con el resultado de la conversión. La conversión se aplica **solo a ingredientes de `catalog`** (en `manual_intake` este campo no se usa ni se muestra) y se aplica siempre: `cooking_factor` tiene `DEFAULT 1.0`, con el que la operación es neutra. Los macros de `catalog` están expresados en crudo, salvo en productos precocinados que ya traen sus valores cocinados.

El cálculo debe utilizar el valor almacenado sin redondear previamente.

Ejemplo:

```text
carbs_100g = 20.4 g/100 g
amount = 75 g
total = 20.4 * 75 / 100 = 15.3 g
```

### 5.3 Límites

Los valores nutricionales deben validarse contra rangos físicos razonables:

- nutrientes de masa: normalmente `>= 0`;
- nutrientes expresados por 100 g: no deben superar límites definidos por campo;
- grasas saturadas: no deben superar grasas totales;
- azúcares: no deben superar hidratos si el contrato del dato lo exige;
- calorías: no deben ser negativas;
- cafeína y alcohol: no deben ser negativos.

Los límites deben documentarse junto con el campo y no repetirse de forma diferente en cada endpoint.

## 6. Confianza e incertidumbre

### 6.1 Valores entre cero y uno

Los campos de confianza e incertidumbre usan una escala normalizada entre `0` y `1`:

```text
0.0 = ausencia total de confianza / máxima incertidumbre
1.0 = confianza total / ausencia de incertidumbre
```

Esto aplica a:

- `amount_confidence`;
- `quality_confidence`;
- `carbs_uncertainty`;
- `sugars_uncertainty`;
- `fats_uncertainty`;
- `saturated_uncertainty`;
- `proteins_uncertainty`;
- `fiber_uncertainty`.

La interfaz puede mostrar estos valores como porcentaje:

```text
0.75 -> 75 %
```

El porcentaje es solo una unidad de presentación. El valor almacenado sigue siendo un decimal entre `0` y `1`.

### 6.2 Significado

La confianza expresa fiabilidad del dato. La incertidumbre expresa falta de fiabilidad. No se deben intercambiar sin documentar la transformación:

```text
uncertainty = 1 - confidence
```

Si una fórmula utiliza una de las dos magnitudes, debe indicarlo explícitamente.

### 6.3 Peso utilizado para los cálculos del evento

Las métricas de confianza e incertidumbre de un `intake_event` se ponderan por el peso que se ha servido o se ha previsto ingerir, no por la cantidad total utilizada para preparar el ingrediente.

El peso canónico es `portion_detail.amount`.

```text
event_intake_weight = suma de amount de sus porciones
```

El fallback de compatibilidad que permitía usar `amount_g` cuando `plate_amount` era nulo **ya no existe**: la decisión 2026-09-18 unificó las dos columnas en `amount` con el backfill `COALESCE(plate_amount, amount_g)`, de modo que no quedan filas sin cantidad y no hay nada que suplir.

`ingested_amount` representa lo que finalmente se consumió y se utiliza para cálculos específicos de consumo real. No sustituye automáticamente a `amount` en las métricas de composición del plato planificado.

### 6.4 `amount_confidence`

`amount_confidence` indica qué proporción del peso servido fue pesada estrictamente.

```text
amount_confidence =
    suma de amount de porciones con strictly_weighed = true
    ---------------------------------------------------------------
    suma de amount de todas las porciones
```

Ejemplo:

| Porción | `amount` | `strictly_weighed` |
|---|---:|---|
| Arroz | 100 g | `true` |
| Salsa | 50 g | `false` |

```text
amount_confidence = 100 / 150 = 0.6667
```

El valor no indica si la información nutricional es correcta. Solo indica la confianza en la cantidad servida.

### 6.5 `quality_confidence`

`quality_confidence` indica qué proporción del peso servido tiene información nutricional marcada como fiable mediante `macros_quality = true`.

```text
quality_confidence =
    suma de amount de porciones con macros_quality = true
    ------------------------------------------------------------
    suma de amount de todas las porciones
```

Este indicador representa la calidad declarada del origen nutricional, no una probabilidad estadística. Un valor puede existir y seguir siendo estimado o poco fiable.

### 6.6 Incertidumbre por nutriente

Cada campo `*_uncertainty` se calcula de forma independiente para cada nutriente:

```text
nutrient_uncertainty =
    suma de amount de porciones sin valor para ese nutriente
    ---------------------------------------------------------------
    suma de amount de todas las porciones
```

Ejemplo:

| Porción | Peso servido | Hidratos |
|---|---:|---|
| Arroz | 100 g | conocido |
| Plato manual | 50 g | `NULL` |
| Aceite | 10 g | `NULL` |

```text
total = 160 g
unknown_carbs = 60 g
carbs_uncertainty = 60 / 160 = 0.375
```

El resultado significa que el `37.5 %` del peso servido no tiene un valor de hidratos registrado. No significa que el total de hidratos tenga exactamente un `37.5 %` de error.

Un nutriente con valor `0` se considera conocido. Solo se considera desconocido cuando el valor es `NULL` o no existe en la fuente aplicable.

### 6.7 Diferencia entre confianza, calidad e incertidumbre

Las métricas tienen significados distintos:

| Campo | Qué mide |
|---|---|
| `amount_confidence` | proporción pesada estrictamente |
| `quality_confidence` | proporción con macros marcados como fiables |
| `carbs_uncertainty` | proporción sin hidratos registrados |
| `sugars_uncertainty` | proporción sin azúcares registrados |
| `fats_uncertainty` | proporción sin grasas registradas |
| `saturated_uncertainty` | proporción sin grasas saturadas registradas |
| `proteins_uncertainty` | proporción sin proteínas registradas |
| `fiber_uncertainty` | proporción sin fibra registrada |

No se debe asumir automáticamente que:

```text
quality_confidence = 1 - nutrient_uncertainty
```

Una porción puede tener un valor nutricional estimado: en ese caso puede reducir `quality_confidence` sin aumentar `*_uncertainty`, porque el valor existe. Del mismo modo, un nutriente puede estar ausente únicamente en una parte de la comida.

Estas métricas no son todavía intervalos estadísticos, desviaciones estándar ni márgenes de error clínicos. Son indicadores de completitud y calidad del registro para ayudar al análisis posterior.

### 6.8 Eventos sin peso calculable

Si un evento no tiene ninguna porción con `amount` válido, sus proporciones no pueden calcularse matemáticamente.

De las dos alternativas que esta sección dejaba abiertas —impedir la
confirmación o almacenar `NULL`— se eligió la primera: **un evento sin
porciones no puede confirmarse**. `POST /cart/event/{id}/confirm` responde
`409` (transición de estado no permitida, `error_conventions.md` §3.6) y no
escribe nada, así que a partir de ahora ningún evento `consumed` nace sin peso
calculable. Decisión 2026-09-10 (hallazgo 34 de
`audit/audit_intake_event.md`).

La comprobación es una regla dependiente del estado de la base, así que ocurre
dentro de la misma transacción que confirma el evento, no antes de abrirla:
leerla fuera dejaba una ventana en la que otra petición podía añadir una
porción que se escalaría sin haber contado en `total_amount` (hallazgo 46).

Un `0.0` en las métricas de un evento **histórico** sigue significando "no
calculable", no "confianza cero" ni "incertidumbre cero": son las filas
anteriores a esta decisión (40 eventos `consumed` con `amount_confidence = 0`),
que se conservan como daño consumado y no se reinterpretan. Cualquier lectura
que compare confianzas debe consultar también si el evento tiene peso válido
antes de tratar un `0.0` como una medida.

### 6.9 Momento del cálculo

Las métricas se calculan a partir de las porciones actuales del evento y se almacenan como un snapshot en `intake_event` cuando la operación de confirmación lo requiere.

Si las porciones cambian antes de confirmar o si una operación posterior modifica el peso servido, las métricas deben recalcularse en la misma unidad de trabajo. No se deben mantener valores derivados antiguos después de cambiar sus datos de origen.

El cálculo de los nutrientes totales del evento utiliza igualmente `amount`:

```text
nutriente_total_evento =
    suma de (nutriente_100g * amount / 100)
```

El redondeo se realiza únicamente en la presentación según las reglas de este documento.

Mientras el evento está `planned`, nada de esto se persiste: la interfaz del carrito lee `portion_detail` en cada petición y recalcula en memoria (`total_amount`, macros, `amount_confidence`, `quality_confidence`, `*_uncertainty`). No existe ninguna escritura en `intake_event` por cada alta, baja o edición de un ingrediente del carrito.

### 6.9.1 Flujo de `confirm` (decisión 2026-09-10)

El único punto donde se persiste algo es la transición `planned -> consumed`, dentro de una sola transacción:

1. Se leen las porciones actuales del evento (`portion_detail`, todavía sin tocar).
2. `total_amount = SUM(amount)` de esas porciones, calculado en vivo (§4.4).
3. `amount_confidence`, `quality_confidence` y `*_uncertainty` (§6.3-§6.6) se calculan sobre esas porciones **antes** de escalarlas. Al ser proporciones (peso que cumple una condición / peso total), una escala uniforme de todas las porciones por el mismo factor no cambia el resultado, así que da igual calcularlas antes o después del paso 5.
4. Se obtiene la `fracción` (`(0, 1]`) a partir de `ingested_value`/`ingested_unit`, según la fórmula de §4.4. Fuera de rango es `422`.
5. `UPDATE portion_detail SET amount = amount * fracción WHERE intake_event_id = ...`: una sola sentencia SQL para todas las porciones del evento, no un recálculo recursivo en Python.
6. `intake_event.ingested_amount = total_amount (paso 2) * fracción`, junto con el resto de campos del snapshot (paso 3) y la transición de `state`.

No hay ninguna otra columna de cantidad que tocar: desde la decisión 2026-09-18 `portion_detail` solo tiene `amount`. El mecanismo de guardar en la nevera la diferencia entre lo cocinado y lo servido sigue ocurriendo antes, en el momento de emplatar, y no lee ni escribe ninguna columna de esta tabla: la cantidad cocinada solo existe como campo del formulario (§4.4).

Pendiente, fuera de alcance de esta decisión (ver `audit/deuda_pendiente.md`): cuando exista la tabla `fridge` como funcionalidad real, el sobrante por ingrediente (`amount_original - amount_final`, calculable solo en el paso 5, antes de sobrescribir) se escribirá en la misma transacción del `confirm`, condicionado a una confirmación explícita del usuario (popup, solo si `fracción < 1`, con un número de días de conservación configurable, por defecto 7).

### 6.9.2 Límite de masa de `intake_event.ingested_amount` (decisión 2026-09-10)

`ingested_amount` es la única masa que `intake_event` sigue persistiendo (§6.9.1; `total_amount` ya no es columna, se calcula en vivo). Como toda cantidad en gramos, debe validarse antes de guardarse:

- **No finitos**: `NaN` e `Infinity` se rechazan con `422` en el boundary (`math.isfinite`), nunca se guardan. Un valor no finito no es "sin dato" (eso es `NULL`); es una entrada corrupta.
- **Límite inferior**: `>= 0`. El `CHECK` no cambia, porque hay eventos históricos con `ingested_amount = 0` y §12.7 los protege, pero `0` pasa a ser un valor **histórico, no producible**: desde la decisión 2026-09-22 la fracción de ingesta está en `(0, 1]` y ningún confirm nuevo puede escribir un `0`. Sigue sin confundirse con "sin dato" (`NULL`).
- **Límite superior**: `100000` (100 kg). No es una cota clínica ni nutricional, es una cota de cordura: ninguna comida humana real la alcanza; su único propósito es que un valor corrupto o manipulado no se guarde como si fuera un dato plausible.

Constraint: `ck_intake_event_ingested_amount CHECK (ingested_amount IS NULL OR (ingested_amount >= 0 AND ingested_amount <= 100000))`, con el mismo nombre canónico (§11.6 de `code_conventions.md`) que el resto de columnas de la tabla.

Esta misma cota aplica al `total_amount` calculado en vivo (§6.9.1 paso 2) y a la `fracción` derivada de él, aunque no exista columna que la persista: un `total_amount` fuera de rango no debe usarse para calcular `ingested_amount` ni para escalar `portion_detail.amount`.

### 6.9.3 Edición de las porciones de un evento ya `consumed` (decisión 2026-09-10)

Las porciones de un evento confirmado **son editables**. Un evento `consumed`
ya era editable en todos sus campos (decisión 2026-09-08) y lo mismo vale para
su `portion_detail`: una comida se corrige después de haberla registrado
(faltaba un ingrediente, el peso no era el que se anotó, la calidad de los
macros era otra). La interfaz que exponga esas ediciones sobre un evento
consumido está pendiente; la regla se fija ahora porque hay rutas que ya las
aceptan.

Consecuencia obligatoria: el snapshot de `intake_event` deja de corresponder a
sus porciones en cuanto estas cambian, así que **toda escritura sobre las
porciones de un evento `consumed` recalcula y reescribe los campos derivados,
en la misma transacción que la escritura**:

- `amount_confidence`, `quality_confidence` y los seis `*_uncertainty`
  (§6.3-§6.6), siempre;
- `ingested_amount` (§6.9.1 paso 6), además, si la escritura cambia algún
  `amount`.

No se admite dejar el snapshot antiguo ni recalcularlo "más tarde": es la misma
regla de §6.9 ("no se deben mantener valores derivados antiguos después de
cambiar sus datos de origen"), aplicada al estado en el que sí hay valores
persistidos.

Mientras el evento está `planned` no hay snapshot que reescribir: las métricas
se recalculan en memoria en cada petición (§6.9).

**Qué está abierto hoy y qué no** (2026-09-22): las rutas del carrito de cantidad, offset, alta y
baja de ingrediente, y las de tandas, exigen `state = planned` y responden `409` sobre un evento
confirmado. Eso es una **limitación de interfaz, no la regla**: la regla es que las porciones de un
evento `consumed` son editables. El día que se construya la interfaz del histórico, cada ruta que
se abra a `consumed` deberá recalcular el snapshot en la misma transacción —métricas siempre, e
`ingested_amount` si toca `amount`—, exactamente como ya hacen las tres rutas de flags. Queda
anotado en `audit/deuda_pendiente.md` decidir entonces qué operaciones se abren.

## 7. Factor de cocinado

`cooking_factor` es una magnitud sin unidad. Representa una relación entre masa cruda y masa cocinada según la fórmula definida por el dominio.

La fórmula debe fijarse antes de utilizarlo en cálculos. La convención recomendada es:

```text
cooking_factor = masa_cocinada / masa_cruda
```

Con esa convención:

```text
masa_cocinada = masa_cruda * cooking_factor
masa_cruda = masa_cocinada / cooking_factor
```

Reglas:

- `cooking_factor` debe ser mayor que cero.
- No puede interpretarse como porcentaje.
- No puede cambiar de significado entre catálogo, porción y receta.
- La unidad de las masas relacionadas sigue siendo gramos.
- Si una fuente externa usa otra definición, debe transformarse antes de guardar.

## 8. Insulina

### 8.1 Dosis

La dosis de insulina se expresa en **unidades de insulina (`U`)**.

La columna que almacena la dosis en `insulin_injections` se llama `units` (se llamaba `basal_units` hasta la decisión del 2026-09-06 registrada en `decisions.md`). Representa una cantidad de unidades de insulina, no gramos ni mililitros, y su nombre es deliberadamente neutro respecto al tipo: la misma columna sirve para basal y para rápida.

Reglas actuales:

- `units` es obligatorio y positivo para insulina **basal**;
- `units` es opcional para insulina **rápida**: hoy siempre se guarda `NULL`, porque el formulario de rápida no captura la dosis, pero un valor positivo es válido en el modelo y podrá capturarse sin migración adicional (caso de uso: usar una pluma que no registra la dosis por sí sola);
- `NULL` significa "dosis no registrada", nunca cero (§2);
- la dosis debe ser positiva;
- el incremento permitido debe estar definido por el formulario y el servidor, y reforzarse además en PostgreSQL con un `CHECK` coherente con esa validación (`code_conventions.md` §11.6);
- la dosis registrada se diferencia de una dosis calculada por el sistema;
- la fecha y hora de la inyección (`shot_time`) se almacenan separadas del momento de creación del registro (`created_at`).

Mientras las dosis se introduzcan manualmente y no se calculen automáticamente, se puede mantener el tipo actual con validación estricta. Si DayBetes calcula dosis o recomendaciones, la dosis y todos sus operandos clínicamente relevantes usarán `NUMERIC`/`Decimal`.

### 8.2 Indicador de insulina en eventos

El campo `insulin_dose` del evento es actualmente un **indicador booleano** de si el evento requiere o contempla insulina. No representa una cantidad de unidades.

No se debe confundir:

```text
insulin_dose = True       -> indicador
units = 8.5               -> cantidad de insulina
```

Si en el futuro se necesita almacenar una dosis asociada al evento, debe crearse un campo con nombre y unidad explícitos, no reutilizar el booleano.

Relación entre `insulin_dose` e `insulin_injections` (decisiones del 2026-09-06):

- Confirmar un `intake_event` con `insulin_dose = TRUE` registra **siempre** una fila en `insulin_injections` asociada a ese evento. Confirmar sin registrar la inyección no es un resultado válido.
- Si el usuario no ha seleccionado zona, la fila se guarda con `injection_zone = NULL`, que significa "zona no registrada" y no "no hubo inyección". Por eso `injection_zone` es nullable. Una zona presente pero fuera del enum es un error de validación explícito, nunca un `NULL` silencioso.
- Un `intake_event` puede tener **varias** inyecciones asociadas (comida larga partida en dos, corrección post-comida). No existe unicidad por evento: la confirmación crea una única inyección automática, y su no duplicación se apoya en que la transición `planned -> consumed` es condicional.
- `intake_event_id` es opcional en la inyección: una inyección sin evento es un registro manual válido, y borrar el evento no elimina la inyección (`ON DELETE SET NULL`).

### 8.3 Fecha de inyección

`shot_time` representa el momento en que se administró la inyección, almacenado en UTC. La interfaz puede introducirlo en la zona horaria local del usuario.

`shot_time` no se sustituye por `created_at` ni al revés: son campos distintos según §9.3. Una inyección puede registrarse horas o días después de haberse administrado.

## 9. Tiempo y fechas

### 9.1 Almacenamiento

Todos los instantes se almacenan como `TIMESTAMPTZ` y representan UTC. La aplicación no debe depender de la zona horaria del sistema operativo o de la sesión de PostgreSQL.

Los eventos relevantes para análisis histórico conservan además la zona IANA aplicable en el momento del evento mediante un campo `timezone_at_event`, por ejemplo `Europe/Madrid`. `TIMESTAMPTZ` conserva el instante universal, pero no el nombre de la zona original.

Las comparaciones de intervalos, retrasos y orden temporal se realizan sobre el instante UTC. Los análisis de hora local convierten cada instante usando su `timezone_at_event`, no la zona actual del usuario ni una zona fija de presentación.

El offset numérico no sustituye a la zona IANA. Puede conservarse adicionalmente cuando sea necesario reproducir exactamente la representación original, pero la zona IANA es el dato canónico para resolver cambios históricos y horario de verano.

### 9.2 Conversión

- Formularios: reciben fecha/hora local del usuario.
- Boundary HTTP: convierte la entrada local a UTC.
- Base de datos: almacena UTC.
- Componentes: convierten UTC a zona local para mostrar.
- Exportaciones: declaran explícitamente la zona horaria utilizada.

### 9.3 Significado de los timestamps

| Campo | Significado |
|---|---|
| `created_at` | momento en que se creó el registro |
| `updated_at` | última modificación del registro |
| `deleted_at` | momento de archivado lógico |
| `meal_time` | hora planificada o asociada al evento |
| `shot_time` | hora de administración de insulina |
| `expires_at` | momento en que deja de ser válida una sesión |

No utilizar `created_at` como sustituto de `meal_time`, ni `meal_time` como sustituto de la hora real de consumo. Si se necesita el momento real, se añadirá un campo independiente.

## 10. Porcentajes, ratios y escalas

- Los porcentajes introducidos por el usuario se reciben en escala `0-100`.
- Los porcentajes almacenados para cálculos de confianza se representan en escala `0-1`.
- Un campo debe indicar claramente qué escala utiliza.
- No guardar `75` en un campo que espera `0.75`.
- No mostrar `0.75 %` cuando el valor significa `75 %`.
- Los ratios sin unidad deben documentar numerador y denominador.

Ejemplo:

```text
amount_confidence = 0.75
presentación = 75 %
```

## 11. Unidades de interfaz

La interfaz puede ofrecer unidades alternativas, pero cada selector debe indicar:

- código interno;
- etiqueta visible;
- factor de conversión a la unidad canónica;
- unidad canónica de destino;
- precisión de entrada;
- precisión de presentación.

Ejemplo:

```text
Código: oz
Etiqueta: oz
Unidad canónica: g
Factor: 28.349523125
```

El código interno de una unidad cerrada debe formar parte del enum central de unidades. Las unidades no se introducen como texto libre.

Ese enum central es `AmountInputUnit` (`DayBetes_food/domain/constants.py`). Contiene `g`, `%`,
`portion`, `lb` y `oz` (decisión 2026-09-22): `lb` y `oz` llevan en el propio enum su factor
exacto a gramos (`453.59237`, `28.349523125`), y son la **única** fuente de ese número — los
`data_factor` del HTML se generan desde ahí, nunca se escriben a mano en una plantilla.
`portion` no tiene factor constante: su factor es el `unit_g` del alimento y se resuelve en
tiempo de ejecución contra la fila de origen, no contra un campo oculto del formulario (§7.13
de `code_conventions.md`).

**La conversión a la unidad canónica ocurre en el servidor.** Un boundary que acepte una unidad
alternativa recibe valor + unidad (`amount_value`/`amount_unit`, `ingested_value`/
`ingested_unit`), convierte la unidad con el enum, calcula los gramos y valida el resultado ya
convertido. El JavaScript puede repintar el número al cambiar de unidad, pero no decide lo que se
persiste.

El boundary que recibe una unidad la convierte con ese enum y rechaza con `422` cualquier valor que no pertenezca al subconjunto que acepta —nunca la interpreta como la unidad canónica por defecto, porque eso guarda una cantidad falsa en vez de rechazar la entrada (decisión 2026-09-10, hallazgo 47 de `audit/audit_intake_event.md`).

## 12. Fuentes y calidad del dato

Cada dato relevante debería poder clasificarse por fuente:

```text
measured    = medido directamente
label       = procedente de etiqueta
estimated   = estimado por el usuario
calculated  = calculado por DayBetes
imported    = importado de una fuente externa
unknown     = origen desconocido
```

La fuente no sustituye al valor. Un dato puede ser `estimated` y tener igualmente un valor numérico válido.

Cuando una fuente externa proporcione una unidad distinta, se conserva la fuente original en metadatos si es necesario y se guarda el valor convertido en la unidad canónica.

### 12.1 Contrato de importación

Cuando un valor proceda de Open Food Facts, LibreView, Apple Health u otra fuente externa, se debe conservar, cuando el modelo lo permita:

```text
source = imported
source_name = nombre del proveedor
source_field = campo original
source_unit = unidad original
canonical_unit = unidad DayBetes
conversion_version = versión de la conversión
measured_at = momento de medición
imported_at = momento de importación
```

Reglas:

- La unidad original se identifica antes de convertir.
- Si la unidad no puede identificarse con seguridad, el dato no se persiste como válido.
- La conversión se realiza una sola vez en el adapter de integración.
- El resto del sistema trabaja únicamente con la unidad canónica.
- `source_unit` no sustituye a `canonical_unit`.
- El valor convertido no se presenta como si hubiera sido medido directamente por DayBetes.
- Si el proveedor cambia el significado o la unidad de un campo, se incrementa `conversion_version`.
- `measured_at` y `imported_at` son momentos distintos y no deben intercambiarse.
- La procedencia debe conservarse aunque el dato se transforme o se utilice en un cálculo derivado.

`source`, `measured_at`, `imported_at` y `request_id` pertenecen a la trazabilidad de mediciones, datos clínicos importados o transformaciones relevantes. No son campos obligatorios de las cuentas de usuario ni deben añadirse a `users` por defecto.

## 13. Datos originales y derivados

Cuando un dato derivado sea importante para análisis futuro, se deben distinguir:

- entrada original del usuario;
- valor normalizado;
- valor convertido;
- valor calculado;
- fórmula y versión utilizada.

No se deben mezclar datos introducidos por el usuario con datos calculados como si tuvieran la misma fiabilidad.

Ejemplo:

```text
Entrada: 1.5 porciones
Equivalencia: 150 g
Hidratos calculados: 32.4 g
Fuente: estimated
```

Si el sistema modifica una fórmula de cálculo, debe poder distinguir los resultados generados con la fórmula antigua de los nuevos cuando eso afecte a la reproducibilidad del análisis.

## 14. Datos futuros de glucosa y actividad

Cuando se incorporen datos de glucosa, deberán definirse antes de integrar una fuente externa:

- unidad canónica de glucosa;
- unidad original de cada proveedor;
- timestamp de medición;
- zona horaria;
- tipo de medición;
- fuente;
- precisión declarada;
- valores faltantes;
- lecturas duplicadas;
- lecturas fuera de rango;
- diferencia entre lectura puntual y sensor continuo.

Cuando se incorporen datos de actividad física, deberán definirse por separado:

- duración en minutos;
- distancia en metros o kilómetros;
- pasos como número entero;
- energía como kcal;
- intensidad mediante una enumeración cerrada o una escala documentada;
- timestamp de inicio y final;
- fuente del dispositivo.

No introducir datos de glucosa o actividad en el modelo actual hasta definir sus unidades y procedencia. La integración no debe depender de asumir que todos los proveedores usan la misma unidad.

## 15. Cambios de unidad y migraciones

Cambiar la unidad canónica de un campo es una migración de datos, no un simple cambio de etiqueta.

Antes de cambiarla se debe:

1. documentar la unidad actual y la nueva;
2. definir la fórmula de conversión;
3. identificar todas las tablas y campos afectados;
4. convertir los datos existentes;
5. actualizar constraints y validaciones;
6. actualizar dataclasses y mappers;
7. actualizar componentes y formularios;
8. revisar cálculos derivados;
9. verificar muestras antes y después.

Nunca cambiar únicamente el texto de una etiqueta si el valor almacenado sigue estando en la unidad anterior.

## 16. Checklist de auditoría de unidades

Para cada campo cuantitativo se debe comprobar:

- ¿Cuál es su unidad canónica?
- ¿Está reflejada en el nombre o en la documentación?
- ¿Qué unidades acepta la interfaz?
- ¿Dónde se realiza la conversión?
- ¿Se almacena ya convertido?
- ¿Qué precisión de entrada y almacenamiento tiene?
- ¿Dónde se redondea?
- ¿Qué significa `NULL`?
- ¿Cómo se representa cero?
- ¿El valor es medido, estimado, calculado o importado?
- ¿Tiene rangos y constraints?
- ¿Se utiliza en cálculos clínicos o solo descriptivos?
- ¿Se distingue de los valores derivados?
- ¿Hay fórmulas duplicadas en Python, SQL o JavaScript?

Un campo no se considera listo para análisis hasta que estas preguntas tengan respuestas documentadas.
