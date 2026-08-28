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
- tolerancia permitida en tests.

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

- `amount_g`;
- `plate_amount`;
- `total_amount`;
- `ingested_amount`;
- cantidades disponibles en nevera;
- peso de tuppers;
- cantidades de porciones;
- cantidades restantes.

Los nombres de campos que representen masa deben terminar preferiblemente en `_g` cuando la unidad no sea obvia.

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

### 4.4 Porción, cantidad servida y cantidad ingerida

Estos conceptos son diferentes:

- `amount_g`: cantidad del ingrediente utilizada en la preparación o asignada a la porción.
- `plate_amount`: cantidad servida o puesta en el plato.
- `total_amount`: suma de las cantidades servidas en el evento.
- `ingested_amount`: cantidad que realmente se consumió.
- cantidad sobrante: `total_amount - ingested_amount`, si la operación aplica.

No se deben utilizar como sinónimos ni sobrescribir una cantidad planificada con la cantidad ingerida.

Reglas:

```text
amount_g > 0
plate_amount >= 0 cuando exista
ingested_amount >= 0 cuando exista
ingested_amount <= total_amount cuando ambos estén definidos
```

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

En un `intake_event`, `cantidad_g` es `plate_amount`. `amount_g` solo se utiliza cuando el cálculo representa la cantidad del ingrediente utilizado o cuando el contexto no es un cálculo de ingesta.

El cálculo debe utilizar el valor almacenado sin redondear previamente.

Ejemplo:

```text
carbs_100g = 20.4 g/100 g
plate_amount = 75 g
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

El peso canónico es `portion_detail.plate_amount`.

```text
event_intake_weight = suma de plate_amount de sus porciones
```

`amount_g` representa la cantidad del ingrediente utilizada o cocinada. `plate_amount` representa la cantidad asignada al plato o comida que se va a ingerir. No deben intercambiarse en cálculos de consumo.

Para datos históricos que todavía no tengan `plate_amount`, el código puede utilizar temporalmente `amount_g` como fallback de compatibilidad. Ese fallback no cambia la definición oficial y debe eliminarse cuando los datos antiguos hayan sido completados o migrados.

`ingested_amount` representa lo que finalmente se consumió y se utiliza para cálculos específicos de consumo real. No sustituye automáticamente a `plate_amount` en las métricas de composición del plato planificado.

### 6.4 `amount_confidence`

`amount_confidence` indica qué proporción del peso servido fue pesada estrictamente.

```text
amount_confidence =
    suma de plate_amount de porciones con strictly_weighed = true
    ---------------------------------------------------------------
    suma de plate_amount de todas las porciones
```

Ejemplo:

| Porción | `plate_amount` | `strictly_weighed` |
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
    suma de plate_amount de porciones con macros_quality = true
    ------------------------------------------------------------
    suma de plate_amount de todas las porciones
```

Este indicador representa la calidad declarada del origen nutricional, no una probabilidad estadística. Un valor puede existir y seguir siendo estimado o poco fiable.

### 6.6 Incertidumbre por nutriente

Cada campo `*_uncertainty` se calcula de forma independiente para cada nutriente:

```text
nutrient_uncertainty =
    suma de plate_amount de porciones sin valor para ese nutriente
    ---------------------------------------------------------------
    suma de plate_amount de todas las porciones
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

Si un evento no tiene ninguna porción con `plate_amount` válido, sus proporciones no pueden calcularse matemáticamente.

La implementación actual conserva `0.0` por compatibilidad para las métricas del evento, pero ese valor no debe interpretarse como “incertidumbre cero” ni como “confianza cero” sin consultar también la existencia de peso válido.

La solución futura preferida es impedir confirmar un evento sin cantidades válidas o almacenar `NULL` para métricas no calculables.

### 6.9 Momento del cálculo

Las métricas se calculan a partir de las porciones actuales del evento y se almacenan como un snapshot en `intake_event` cuando la operación de confirmación lo requiere.

Si las porciones cambian antes de confirmar o si una operación posterior modifica el peso servido, las métricas deben recalcularse en la misma unidad de trabajo. No se deben mantener valores derivados antiguos después de cambiar sus datos de origen.

El cálculo de los nutrientes totales del evento utiliza igualmente `plate_amount`:

```text
nutriente_total_evento =
    suma de (nutriente_100g * plate_amount / 100)
```

El redondeo se realiza únicamente en la presentación según las reglas de este documento.

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

`basal_units` representa una cantidad de unidades, no gramos ni mililitros.

Reglas actuales:

- `basal_units` es obligatorio para insulina basal;
- `basal_units` es `NULL` para insulina rápida si no se registra una dosis equivalente;
- la dosis debe ser positiva;
- el incremento permitido debe estar definido por el formulario y el servidor;
- la dosis registrada se diferencia de una dosis calculada por el sistema;
- la fecha y hora de la inyección se almacenan separadas del momento de creación del registro.

Mientras las dosis se introduzcan manualmente y no se calculen automáticamente, se puede mantener el tipo actual con validación estricta. Si DayBetes calcula dosis o recomendaciones, la dosis y todos sus operandos clínicamente relevantes usarán `NUMERIC`/`Decimal`.

### 8.2 Indicador de insulina en eventos

El campo `insulin_dose` del evento es actualmente un **indicador booleano** de si el evento requiere o contempla insulina. No representa una cantidad de unidades.

No se debe confundir:

```text
insulin_dose = True       -> indicador
basal_units = 8.5         -> cantidad de insulina
```

Si en el futuro se necesita almacenar una dosis asociada al evento, debe crearse un campo con nombre y unidad explícitos, no reutilizar el booleano.

### 8.3 Fecha de inyección

`shot_time` representa el momento en que se administró la inyección, almacenado en UTC. La interfaz puede introducirlo en la zona horaria local del usuario.

## 9. Tiempo y fechas

### 9.1 Almacenamiento

Todos los timestamps se almacenan en UTC. La aplicación no debe depender de la zona horaria del sistema operativo o de la sesión de PostgreSQL.

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
9. actualizar tests y exportaciones;
10. verificar muestras antes y después.

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
- ¿Existen tests de conversión y límites?

Un campo no se considera listo para análisis hasta que estas preguntas tengan respuestas documentadas.
