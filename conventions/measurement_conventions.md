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

Para obtener un nutriente correspondiente a una cantidad `amount_g`:

```text
nutriente_total = nutriente_100g * amount_g / 100
```

El cálculo debe utilizar el valor almacenado sin redondear previamente.

Ejemplo:

```text
carbs_100g = 20.4 g/100 g
amount_g = 75 g
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
