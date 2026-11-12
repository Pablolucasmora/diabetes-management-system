# Convenciones de Desarrollo - DayBetes

Este documento define la forma obligatoria de construir código nuevo y refactorizar código existente en DayBetes. Su objetivo es mantener una arquitectura coherente, evitar errores de seguridad y concurrencia, y hacer que funciones equivalentes tengan contratos equivalentes.

Durante una auditoría de tabla, módulo o Pull Request, este documento es el criterio de decisión. Si una decisión concreta de producto o modelo no está cubierta aquí, debe documentarse antes de implementar el código y añadirse a este documento si puede repetirse.

Las convenciones se aplican inmediatamente al código nuevo. El código existente se adapta progresivamente por tabla o módulo, sin mezclar en una misma corrección cambios funcionales no relacionados.

Durante la fase de desarrollo personal (TFG, un único desarrollador, un único usuario) no se exige una suite de tests automatizados. La verificación manual del comportamiento afectado es suficiente antes de dar por cerrada una tabla o módulo. Esta decisión se revisará cuando el proyecto salga de esta fase; no debe señalarse como convención faltante en auditorías mientras siga vigente.

## 0. Idioma (obligatorio)

La regla general es: **lo que se ejecuta, en inglés; lo que se lee como documentación, en español.**

| Qué | Idioma |
|---|---|
| Código: identificadores, nombres de funciones y variables, docstrings, **comentarios**, comentarios dentro de SQL, mensajes internos de excepción y de log | Inglés |
| Archivos de infraestructura y configuración: scripts de shell, workflows de GitHub Actions, Compose, Dockerfiles, unidades de systemd, plantillas de entorno (`.env.example` y similares), incluidos sus comentarios y mensajes | Inglés |
| Mensajes de commit, nombres de ramas, títulos y descripciones de Pull Requests | Inglés |
| `README.md`, `conventions/` (incluido `decisions.md`) y la memoria del TFG | Español |
| Texto que ve el usuario (interfaz y mensajes públicos de error) | Inglés (`frontend_conventions.md` §7.12, `error_conventions.md` §1). La internacionalización sigue pendiente |

- Un comentario en español en código nuevo es un defecto, no un detalle de estilo.
- El código existente se tradujo entero en octubre de 2026. Desde entonces no hay excepciones por código heredado: cualquier comentario en español que aparezca se corrige.
- Una traducción nunca se mezcla con cambios funcionales (§12.1). Una PR de traducción se verifica comprobando que el código, sin comentarios ni docstrings, no cambia.

## 1. Capas y responsabilidades

El proyecto se divide estrictamente en cuatro responsabilidades. Una capa inferior no debe conocer detalles de una capa superior.

### 1.1 Rutas y endpoints

Las funciones de `routes/`:

- reciben la petición HTTP;
- aplican las reglas de acceso del endpoint;
- extraen y validan los datos de entrada;
- convierten la entrada HTTP en dataclasses de comandos o payloads;
- abren y cierran la conexión de la unidad de trabajo;
- coordinan una o varias operaciones de servicio/CRUD;
- traducen resultados y excepciones a respuestas HTTP, HTML o JSON.

Las rutas no deben contener SQL ni duplicar reglas de persistencia. Una ruta puede decidir qué código HTTP corresponde, pero no debe decidir cómo se construye una query.

Una ruta puede llamar directamente a un CRUD cuando la operación es una única lectura o escritura sin reglas de negocio adicionales. Se introduce un servicio cuando hay coordinación de varias operaciones, una transacción compuesta, una regla de negocio no trivial o una operación que deba reutilizarse desde más de un endpoint.

Cada unidad de trabajo tiene un único coordinador raíz. Si la ruta delega la operación en un servicio, la ruta le entrega la coordinación de la unidad de trabajo y el servicio se convierte en su propietario; no se crean coordinadores paralelos para la misma operación.

### 1.2 Servicios

Las funciones de `services/` contienen casos de uso reutilizables que combinan varias operaciones o reglas de negocio.

Un servicio:

- recibe datos ya parseados y validados;
- puede coordinar varias queries;
- es dueño de la transacción si coordina una operación compuesta fuera de una ruta;
- no devuelve `HTMLResponse`, `JSONResponse` ni fragmentos HTMX;
- no debe depender de headers, cookies o detalles de la petición HTTP.

Un endpoint puede llamar directamente a `database/queries/` cuando la operación es una única lectura o escritura sin reglas de negocio adicionales. Se introduce un servicio cuando hay coordinación de varias operaciones, una transacción compuesta, una regla de negocio no trivial o una operación que deba reutilizarse desde más de un endpoint.

Si un servicio recibe una conexión, la usa como parte de la unidad de trabajo existente. No abre otra conexión salvo que su contrato documente explícitamente que es el coordinador raíz. Un servicio nunca abre una conexión adicional para consultar datos que podría obtener mediante la conexión recibida.

### 1.3 Queries y CRUD

Las funciones de `database/queries/` ejecutan SQL sobre una entidad u operación de persistencia concreta.

Un CRUD:

- recibe una conexión existente;
- recibe dataclasses o argumentos tipados, nunca datos HTTP sin parsear;
- construye y ejecuta SQL parametrizado;
- aplica filtros de propietario y visibilidad cuando forman parte de su contrato;
- respeta el contrato de commit definido en la sección 2;
- devuelve datos de dominio o resultados simples;
- no construye respuestas HTTP;
- no devuelve HTML, JSON ni interpreta headers HTMX.

#### 1.3.1 Organización de archivos en `database/queries/`

`database/queries/` no es un único archivo: un módulo por tabla física, nombrado como la tabla (`users.py`, `catalog.py`, `manual_intake.py`, `recipe.py`, `recipe_plate.py`, `tags.py`, `linked_tags.py`, `user_favorites.py`, `food_brands.py`, `intake_event.py`, `insulin_injections.py`, `insulin_brand.py`, `insulin_pen.py`, `portion_detail.py`, `meal_type_schedule.py`, `auth_sessions.py`, `auth_rate_limits.py`, ...).

- **`crud.py`** contiene únicamente helpers genéricos compartidos por varios módulos de tabla: ejecución de queries (`_execute_query`, `_execute_query_many`), el constructor seguro de `UPDATE` dinámico (`_build_update_query` y su whitelist), búsqueda difusa (`_build_fuzzy_search`), la búsqueda por palabras de las tablas de referencia (`_search_reference_foods`) y la regla de visibilidad de `catalog` y `manual_intake` (`_food_visibility_sql`). No contiene CRUD de ninguna tabla. Un helper usado por más de un módulo de tabla vive en `crud.py`, aunque físicamente resida hoy dentro del bloque de una tabla concreta; no se decide por dónde está escrito hoy sino por quién lo usa.
- Una función va en el archivo de la tabla sobre la que ejecuta su SQL. Si su `FROM`/`UPDATE`/`INSERT` principal toca la tabla puente de una relación N:M (`linked_tags`, `user_favorites`), va en el archivo de esa tabla puente, no en el de las tablas que relaciona.
- Una lectura que agrega o combina varias tablas sin tabla dueña clara (autocompletado que unifica `catalog`+`manual_intake`, rankings de uso que cruzan `portion_detail`+`intake_event`, etc.) va en **`entries.py`**, reservado para lecturas cross-entity. No se fuerza en el archivo de la primera tabla que aparece en el `FROM` porque eso es arbitrario.
- **`__init__.py`** re-exporta toda la API pública de todos los módulos de tabla y de `entries.py` (no los helpers privados de `crud.py`). El resto de la aplicación (`routes/`, `services/`, `components/`) importa siempre `from DayBetes_food.database.queries import <nombre>`, nunca del módulo de tabla concreto — así ningún punto de import fuera de `database/queries/` depende de en qué archivo vive cada query.
- Añadir una tabla nueva implica: crear su módulo, añadir sus funciones públicas al re-export de `__init__.py`, y mover a `crud.py` cualquier helper que termine siendo compartido con otra tabla.

#### 1.3.2 Columnas cualificadas en SQL

Toda referencia a una columna en una query SQL indica la tabla de la que proviene, mediante su alias o el nombre de la tabla (`entity.created_by`, `fb.label`, `c.is_published`). La regla se aplica también a las queries de una sola tabla y a los fragmentos SQL construidos por separado (cláusulas de visibilidad, filtros dinámicos, helpers de `crud.py`) que después se concatenan en una query mayor.

Motivo: una columna sin cualificar solo funciona mientras ninguna otra tabla del `FROM` tenga una columna con el mismo nombre. Añadir un `JOIN` o una columna nueva a otra tabla (por ejemplo, `created_by` en `food_brands`) convierte en `AmbiguousColumn` una query que antes funcionaba, y el fallo aparece en ejecución, no al escribir el cambio.

Excepciones, solo donde PostgreSQL no admite cualificador: la lista de columnas de un `INSERT`, las columnas destino de `SET` en un `UPDATE` y la lista de columnas de `ON CONFLICT (...)`. En un `UPDATE`, las expresiones del lado derecho del `SET`, el `WHERE` y el `RETURNING` sí se cualifican.

### 1.4 Componentes y frontend

Las funciones de `components/` reciben datos ya consultados y renderizan HTML o configuran HTMX.

Los componentes deben ser puros respecto a la base de datos:

- no importan `get_connection`;
- no abren conexiones;
- no ejecutan queries;
- no modifican datos;
- no deciden permisos de negocio;
- no convierten errores de base de datos en mensajes propios.

El componente `render_page()` y cualquier helper equivalente tampoco debe abrir conexiones implícitamente. La ruta o el servicio coordinador debe poseer la conexión y pasar al componente todos los datos necesarios.

La prohibición incluye consultas indirectas: un componente no puede llamar a una función que internamente consulte la base de datos. Los componentes reciben modelos, dataclasses o datos de presentación ya preparados.

## 2. Ciclo de vida de conexiones y transacciones

### 2.1 Dueño de la conexión

Una unidad de trabajo es el conjunto de lecturas y escrituras que deben observar una misma realidad de datos y compartir un mismo resultado transaccional. Una petición HTTP puede contener más de una unidad de trabajo independiente, pero cada unidad de trabajo utiliza una única conexión.

El endpoint o servicio coordinador raíz es el único dueño de la conexión de su unidad de trabajo y es responsable de cerrarla. Si una petición necesita realizar operaciones independientes, cada una debe tener un boundary explícito; no se reutiliza una conexión abierta accidentalmente por otra capa.

Reglas:

- Abrir la conexión en el boundary de la unidad de trabajo.
- Pasar la misma conexión a los servicios, queries y componentes que la necesiten para leer datos.
- No abrir varias conexiones para completar una misma operación lógica.
- No abrir conexiones dentro de componentes, mappers o helpers de presentación.
- No mantener conexiones en variables globales ni en `ContextVar`.
- Un componente no puede ocultar una lectura de base de datos durante el renderizado.
- El middleware, la ruta, el servicio y el renderizado no deben abrir conexiones duplicadas para la misma unidad de trabajo.

### 2.2 Operaciones simples

Toda función CRUD de escritura acepta `commit: bool = True`.

- `commit=True`: el CRUD es propietario de una operación simple y debe confirmar su operación cuando termina correctamente. Si falla, revierte su propia operación y propaga la excepción, o la traduce a un error de aplicación tipado conservando la causa (§2.5). Nunca la convierte en un valor de retorno.
- `commit=False`: el CRUD participa en una transacción propiedad del llamador y no confirma ni revierte la transacción bajo ningún concepto.
- Las funciones de solo lectura siempre llaman a los helpers de query con `commit=False`.
- El valor de `commit` se propaga hasta el helper que ejecuta el cursor.

`commit=False` expresa ownership, no ausencia de transacción. Una lectura puede ejecutarse dentro de una transacción implícita de Psycopg o dentro de la transacción compuesta del llamador; la función simplemente no decide cuándo finaliza.

Se mantiene este parámetro explícito aunque Psycopg 3 permita anidar `connection.transaction()` mediante savepoints. Un savepoint anidado no equivale a confirmar una operación y puede ocultar quién es el propietario real de la transacción. La convención `commit=True/False` hace visible el ownership, garantiza que una operación compuesta sea todo-o-nada y evita que un CRUD introduzca límites transaccionales implícitos.

No se utilizará `with connection.transaction()` dentro de cada CRUD como sustituto de esta convención. Si en el futuro se necesita aislamiento parcial dentro de una operación compuesta, se añadirá un helper de savepoint explícito y documentado; nunca se obtendrá accidentalmente por anidamiento.

### 2.3 Operaciones compuestas

El endpoint o servicio que coordina varias escrituras posee la transacción:

```python
try:
    with connection.transaction():
        first_write(connection, ..., commit=False)
        second_write(connection, ..., commit=False)
except (ValidationError, NotFoundError, ConflictError) as error:
    return error_response(error)
```

El coordinador solo captura los errores de aplicación que sabe traducir a una respuesta. Una excepción SQL o de infraestructura no se captura: al salir del bloque, `connection.transaction()` ya ha revertido la operación y la excepción sigue hasta el boundary global (`error_conventions.md` §8.3 y §11).

Todas las escrituras de la operación compuesta deben confirmar o revertir juntas. Cada resultado esperado debe comprobarse inmediatamente. Si una operación devuelve `False` o `None` cuando el caso de uso requiere éxito, se lanza una excepción para provocar rollback.

### 2.4 Commit y rollback

- Un CRUD nunca hace `commit()` incondicional.
- Un CRUD nunca hace `rollback()` cuando `commit=False`.
- Un helper puede hacer `commit()` o `rollback()` únicamente cuando `commit=True` y es propietario de la operación simple.
- Un endpoint o servicio coordinador no debe llamar a `commit()` o `rollback()` manualmente si usa `connection.transaction()`.
- No se permiten `commit()` o `rollback()` huérfanos fuera de un punto explícito de ownership transaccional.
- Los cursores directos siguen exactamente estas mismas reglas.
- `db_init.py` es bootstrap de esquema y mantiene su propia transacción de arranque; queda fuera de las transacciones CRUD de la aplicación.

No se considera válido llamar a un CRUD con `commit=True` desde una operación compuesta para “dejar confirmado” uno de sus pasos. Si se necesita esa semántica, debe diseñarse como una unidad de trabajo diferente o mediante un savepoint explícito documentado. Los savepoints no sustituyen el ownership de la transacción externa ni realizan un commit real.

### 2.5 Errores dentro de una transacción propia

Un fallo SQL o de infraestructura **siempre se propaga como excepción**, en los dos modos. Lo único que cambia entre ellos es quién revierte:

- En modo propietario (`commit=True`), el helper o el CRUD hace `rollback()` de su propia operación y **relanza** la excepción. Antes puede traducirla a un error de aplicación tipado cuando su contrato lo define (por ejemplo, `UniqueViolation` → `ConflictError`, §6.2), conservando la causa con `raise ... from exc`.
- En modo caller-owned (`commit=False`), propaga la excepción sin hacer `rollback()`. Revierte quien posee la transacción (§2.3, §2.4).

Ningún helper ni CRUD convierte un fallo en un valor de retorno. `None`, `False` y `[]` solo significan lo que define el contrato de la función: "no hay fila", "la operación no es aplicable" o "no hay resultados" (§3.3, §3.4). Nunca significan "ha fallado". Tampoco se registra la excepción al relanzarla. El log se escribe una sola vez, en el boundary que la convierte en respuesta (`error_conventions.md` §10.3).

El rollback de los helpers genéricos (`_execute_query`, `_execute_query_many`) se deriva únicamente de `commit`. No existe un parámetro por call site que lo cambie, para que nadie pueda configurarlo mal. Un argumento así ya causó el defecto que corrigió la decisión 2026-09-22. Un default "siempre rollback" convertía todas las lecturas, que llaman con `commit=False`, en infractoras de §2.4. Además, dentro de un `connection.transaction()` producía `ProgrammingError: Explicit rollback() forbidden within a Transaction context`, que enmascaraba el error real. Una función que necesite un tratamiento propio (traducir una violación de unicidad, por ejemplo) captura la excepción que le llega del helper. No reimplementa el helper.

Los errores de aplicación se clasifican así:

- `ValidationError`: entrada o combinación de valores inválida.
- `NotFoundError`: el recurso no existe o no es visible para el contexto autorizado.
- `ConflictError`: unicidad, versión obsoleta o conflicto de estado.
- Excepción SQL/infraestructura: fallo técnico que debe propagarse hasta el boundary correspondiente.

El coordinador no debe convertir indiscriminadamente todas estas categorías en `ValueError`.

**Para saber más sobre las convenciones de errores leer `error_conventions.md`**

## 3. Tipado de datos, firmas y nomenclatura

### 3.1 Dataclasses

Se abandona el uso de diccionarios planos como contrato entre capas.

- Toda conversión de una fila SQL a un objeto de dominio debe usar una dataclass de lectura.
- Todo payload que viaje de una ruta a un servicio o CRUD debe usar una dataclass de comando/update.
- Una dataclass de request representa datos HTTP ya parseados y validados, pero no debe cruzar directamente a la capa de persistencia.
- Una dataclass de comando representa la intención del caso de uso y no conoce headers, cookies ni nombres de campos específicos de un formulario.
- Una dataclass de lectura/dominio representa datos que salen de persistencia y puede utilizarse para renderizar o serializar una respuesta.
- Una dataclass de update representa únicamente los campos modificables de una entidad.
- Las dataclasses centralizan conversión de `REAL`, `Decimal`, `NULL`, fechas y booleanos.
- Los campos opcionales deben declararse como opcionales; no representar opcionalidad mediante claves ausentes ambiguas.
- Los datos HTTP se convierten a dataclass después de validar la entrada y antes de llamar al servicio/CRUD.
- Las respuestas JSON pueden serializar dataclasses mediante un mapper explícito; no se devuelve directamente una fila de psycopg.

La separación mínima recomendada es:

```text
HTTP input -> Request dataclass -> Command/Update dataclass -> CRUD
SQL row -> mapper -> Read/Domain dataclass -> component o respuesta JSON
```

No es obligatorio crear una dataclass distinta cuando dos capas tienen exactamente el mismo contrato, pero esa equivalencia debe ser deliberada y no consecuencia de pasar un diccionario o un objeto HTTP sin transformar.

Ejemplo:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RecipeUpdate:
    name: str | None = None
    meal_type: str | None = None
    notes: str | None = None
```

### 3.2 Acceso a filas SQL

- Usar `row["column"]` para columnas obligatorias del contrato SQL.
- Usar `row.get("column")` exclusivamente para columnas opcionales o nullable.
- Si una columna obligatoria falta, debe producirse un error de contrato, no un valor por defecto silencioso.
- Las conversiones repetidas de filas se centralizan en mappers.
- No repetir por todo el proyecto expresiones como `float(row.get("amount_g") or 0.0)` sin decidir si `NULL` significa cero o ausencia.

### 3.3 Funciones CRUD

Usar los siguientes verbos:

- `create_<entity>`: crea una fila y devuelve siempre su ID en los CRUD base. Un servicio puede recuperar y devolver la dataclass completa si el caso de uso lo necesita.
- `get_<entity>`: obtiene una entidad individual y devuelve su dataclass o `None` si no es visible/no existe según el contrato de lectura.
- `list_<entities>`: devuelve siempre `list`; una lista vacía significa “sin resultados”.
- `update_<entity>`: modifica una entidad existente.
- `delete_<entity>`: elimina físicamente cuando la entidad no es archivable.
- `archive_<entity>`: aplica soft-delete.
- `restore_<entity>`: elimina el soft-delete.

No introducir `add_`, `fetch_`, `find_`, `remove_` o `save_` para operaciones equivalentes nuevas.

### 3.4 Contrato de escrituras y “no encontrado”

- `create_*` devuelve el identificador u objeto creado.
- En todos los verbos, y sea cual sea `commit`, un fallo SQL o de infraestructura lanza excepción (§2.5). Nunca se representa con `None`, `False` o `[]`.
- `update_*`, `delete_*`, `archive_*` y `restore_*` devuelven `True` cuando modifican la fila.
- Devuelven `False` únicamente cuando la fila visible y autorizada existe, pero la operación no es aplicable por una regla de negocio idempotente, por ejemplo archivar una fila ya archivada.
- Si el identificador no existe, la operación lanza `NotFoundError` cuando el contrato necesita distinguir ese caso.
- Si la fila existe pero no pertenece al usuario y no debe revelarse, la query mutadora debe producir el mismo resultado externo que un recurso inexistente: `NotFoundError` o un resultado equivalente que el endpoint traduzca a `404`.
- No usar `False` indistintamente para “ID inexistente”, “sin permiso”, “ya archivado” y “fallo SQL”.
- Dentro de una operación compuesta, un `False` inesperado se convierte en excepción para provocar rollback.

Un update parcial debe representar de forma inequívoca tres estados: campo ausente (no modificar), campo presente con `None` (guardar `NULL` cuando el campo lo permita) y sentinel `CLEAR` (borrado explícito cuando el contrato lo diferencie). No se puede recuperar esta distinción leyendo una clave opcional de un `dict` sin un contrato adicional.

### 3.5 Parámetros

- Usar `user_id` en todo el código Python: nombres de parámetros, variables locales, claves de payloads, parámetros SQL, campos de dataclasses y nombres expuestos por los mappers, aunque la columna física heredada se llame `users_id`.
- El literal `users_id` solo puede aparecer en SQL, `schema.py`, migraciones/bootstrap y documentación que describa el esquema físico. Cuando una fila SQL se expone fuera de la capa de persistencia, debe mapearse a `user_id` o seleccionarse mediante un alias `users_id AS user_id`.
- No renombrar automáticamente `created_by`: representa el actor/creador y no es necesariamente equivalente al propietario actual `user_id`.
- Usar nombres explícitos: `catalog_id`, `manual_intake_id`, `recipe_id`, `intake_event_id`.
- No usar un parámetro genérico `id` cuando el concepto pueda confundirse.
- Mantener el orden: `connection`, contexto de usuario, identificador de entidad, payload, opciones como `commit`, `limit` y `offset`.
- Los updates de entidad reciben un payload dataclass. Las operaciones especializadas pueden tener argumentos explícitos si ejecutan una acción distinta, no si son otro update equivalente.
- No usar `**kwargs` para campos de tablas; los campos aceptados deben estar tipados y validados.
- Las funciones que reciben una conexión deben usar el tipo común de conexión del proyecto cuando exista; no crear wrappers incompatibles por módulo.

### 3.6 Paquete `domain/` y ubicación de los mappers

`DayBetes_food/domain/` es el único lugar donde viven los enums de dominio (§4.1) y las dataclasses de lectura/comando/update (§3.1). `domain/` no importa psycopg, rutas ni componentes: es código puro, sin dependencias de infraestructura ni de presentación.

- `domain/constants.py`: enums de dominio (§4.2).
- Un módulo por entidad con sus dataclasses, por ejemplo `domain/insulin.py` para `insulin_injections`.
- Un módulo de reglas compartidas por varias entidades, cuando la regla la usan dos o más: `domain/nutrition.py` contiene los límites de nutrientes, el parser numérico y el de smart macros que comparten `catalog` y `manual_intake` (decisión 2026-09-25). Una entidad no importa reglas del módulo de otra entidad.

Los **mappers de fila SQL a dataclass viven en la capa de persistencia** (`DayBetes_food/database/mappers.py`), nunca en `domain/`: conocen nombres físicos de columna (`users_id` → `user_id`, §3.5) que el dominio no debe conocer. `auth/models.py` es anterior a esta convención y mantiene sus mappers junto a las dataclasses porque es un módulo cerrado y específico de autenticación; no es precedente para código nuevo.

Las etiquetas visibles y las imágenes asociadas a un enum (por ejemplo las rutas de imagen de `InjectionZone`) son un mapper de presentación y siguen en `components/`, nunca en `domain/`.

```text
domain/constants.py   -> enums de dominio
domain/<entidad>.py    -> dataclasses de esa entidad
database/mappers.py   -> fila SQL -> dataclass (conoce nombres físicos)
components/<algo>.py  -> dataclass/enum -> etiqueta o imagen (presentación)
```

## 4. Constantes de dominio

### 4.1 Fuente única de verdad

Un valor se modela como enumeración cuando pertenece a un conjunto cerrado y conocido de opciones. Ejemplos: tipos de comida, zonas de inyección, tipos de insulina, estados de eventos, Nutriscore y modos internos de navegación. También son conjuntos cerrados la categoría de un alimento (`catalog.category`), los estados físicos del alimento (`catalog.initial_state` y `portion_detail.final_state`, que comparten un único enum), los métodos de cocción (`portion_detail.cooking`) los métodos de conservación (`portion_detail.conservation`), la madurez de una fruta (`portion_detail.ripeness`, `Ripeness`, `study_conventions.md` §6.3) y el índice glucémico declarado de un plato manual (`manual_intake.glycemic_index`, `measurement_conventions.md` §5.5): que se prevea añadirles valores no los convierte en abiertos, porque solo se amplían de forma deliberada cambiando el enum en el código, con la revisión conjunta de §4.4. El criterio que separa un conjunto cerrado de uno abierto está en §4.5.

Los enums de dominio se declaran en un módulo central, `DayBetes_food/domain/constants.py` (§3.6). Ese módulo no debe importar rutas, componentes ni la base de datos. Las dataclasses que usan estos enums viven en el módulo de su entidad dentro de `domain/`, por ejemplo `InsulinType` e `InjectionZone` se declaran en `domain/constants.py` y se consumen desde `domain/insulin.py`.

Cada concepto tiene un único enum. No se crean listas paralelas del mismo concepto en `routes/`, `components/`, `crud.py` y `schema.py`.

### 4.2 Implementación obligatoria

Los enums persistibles deben ser compatibles con texto para poder validarse y serializarse de forma predecible:

```python
from enum import Enum, unique


@unique
class MealType(str, Enum):
    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon_snack"
    DINNER = "dinner"
    SNACK = "snack"
    RESCUE = "rescue"
```

Reglas de implementación:

- El nombre de la clase usa PascalCase y describe el concepto singular: `MealType`, `InsulinType`, `EventState`.
- Los miembros usan MAYÚSCULAS con guion bajo: `AFTERNOON_SNACK`.
- Los valores (`.value`) son los códigos estables que se almacenan o transmiten: minúsculas, ASCII y `snake_case` cuando corresponda.
- Los valores persistidos no se renombran por motivos cosméticos. Cambiar un valor requiere migración de datos.
- Si un conjunto que ya tiene datos guardados pasa a ser enum y sus códigos no siguen el formato anterior (por ejemplo, `mashed/creamy`, `boiled-al-dente` o `freshly-made`), el enum conserva los códigos existentes tal cual: prevalece la regla de no renombrar. Los valores que se añadan después sí siguen el formato.
- `@unique` es obligatorio para impedir aliases accidentales.
- Las etiquetas visibles al usuario no forman parte del valor persistido. Se mantienen en un mapper o diccionario de presentación separado.
- Los enums no contienen lógica de rutas, SQL, HTML ni traducciones dependientes de un componente.

### 4.3 Uso entre capas

- Los endpoints convierten el texto recibido a enum en el boundary de entrada:

```python
try:
    meal_type = MealType(raw_meal_type)
except ValueError as exc:
    raise ValidationError("Invalid meal type") from exc
```

- Un valor no perteneciente al enum produce un error de validación (`422`), no un fallback silencioso.
- Los servicios reciben enums ya validados, no strings arbitrarios.
- Las dataclasses de dominio usan el tipo enum, no `str`, para campos cerrados.
- Al construir parámetros SQL se usa siempre `enum_value.value`.
- Al leer SQL, el mapper convierte el código persistido de nuevo al enum. Un valor desconocido debe producir un error de integridad/configuración, no ignorarse.
- Los componentes generan sus opciones recorriendo el enum y usan un mapper independiente para las etiquetas.
- Los endpoints y componentes no escriben literales sueltos como `"rapid"`, `"basal"`, `"planned"` o `"consumed"`.

### 4.4 Refuerzo en la base de datos

La base de datos debe reflejar los valores cerrados mediante un `CHECK` explícito o una restricción equivalente:

```sql
CHECK (state IN ('planned', 'consumed'))
```

La lista del `CHECK` debe coincidir exactamente con los valores `.value` del enum. PostgreSQL no se considera la fuente de verdad del concepto: el enum central define el contrato de aplicación y el constraint SQL lo refuerza.

Añadir, eliminar o cambiar un valor requiere revisar conjuntamente:

1. El enum central.
2. El schema y la migración.
3. Los mappers y dataclasses.
4. Las validaciones y servicios.
5. Los formularios y etiquetas visibles.
6. Los datos existentes afectados.
7. La validación de aceptación y persistencia.

### 4.5 Enumeraciones abiertas

Un valor que el usuario, un administrador o una fuente externa pueda ampliar no se modela como `Enum` de Python ni como `CHECK` cerrado.

"Ampliar" significa añadir un valor como cambio de datos, sin tocar el código: desde la interfaz (por ejemplo, un selector con "Add"), desde una herramienta de administración o al importar de una fuente externa. Un conjunto al que solo se añaden valores editando el código es cerrado (§4.1), aunque se espere que crezca.

Debe almacenarse en una tabla de catálogo con, como mínimo:

- identificador;
- código estable;
- etiqueta visible;
- indicador `is_active`;
- timestamps cuando proceda.

Los valores iniciales pueden cargarse mediante bootstrap o migración, pero añadir uno nuevo debe ser un cambio de datos, no un cambio obligatorio de código.

En esta categoría entran actualmente dos conceptos:

| Concepto | Columnas | Estado |
|---|---|---|
| Marcas de comida | `catalog.brand_id` → `food_brands` | Catálogo implementado (`code`, `label`, `is_active`) |
| Subtipos de comida | `catalog.subtype`, `manual_intake.subtype` | Texto libre; catálogo pendiente |

El origen de un plato manual (`manual_intake.origin`) salió de esta tabla el 2026-10-09: no es una enumeración abierta, sino **texto libre normalizado** con autocompletado (§11.2.3). Un catálogo global expondría a todos los usuarios lugares y personas que solo tienen sentido para uno ("abuela Geno").

Un concepto entra o sale de esta tabla solo por decisión explícita, y se actualiza aquí en el mismo cambio. Las listas Python existentes de los conceptos pendientes solo pueden actuar como datos iniciales mientras se completa el catálogo.

### 4.6 Enumeraciones técnicas

Las whitelists internas también son conjuntos cerrados, aunque el usuario no los introduzca. Ejemplos: tablas permitidas para updates, campos actualizables, tipos de entidad y expresiones SQL raw.

- Deben centralizarse igual que los enums de dominio.
- Se validan antes de construir SQL o seleccionar una estrategia.
- No se exponen como opciones editables al usuario.
- Añadir un valor requiere revisar seguridad y queries.

### 4.7 Constantes de configuración

Límites, tamaños de página, ventanas temporales y nombres de cookies se definen una sola vez en configuración. No repetir números mágicos en endpoints o componentes.

## 5. Seguridad, autenticación, autorización y ownership

### 5.1 Autenticación

El middleware global valida la sesión y establece el usuario de la petición. Cada endpoint debe pertenecer claramente a una de estas categorías:

- público;
- requiere usuario autenticado;
- requiere usuario autenticado y ownership del recurso;
- requiere un permiso o rol adicional, si se introduce ese modelo.

No duplicar validaciones de sesión de forma distinta en cada ruta. Un endpoint puede comprobar explícitamente la ausencia de usuario cuando necesita una respuesta distinta, pero debe respetar el mismo contrato de códigos.

### 5.2 CSRF y rate limiting

- Toda petición que no use un método de lectura (`GET`, `HEAD`, `OPTIONS`) requiere el token CSRF definido por el middleware. La lista es de métodos seguros, no de inseguros, para que un método no previsto quede protegido por defecto. Una escritura nunca se hace por un método de lectura (§9.2).
- El token debe coincidir con la cookie (*double submit*) y con el guardado en la sesión, comparados en tiempo constante.
- Ninguna ruta queda sin token. Los formularios que se envían antes de haber sesión (`/auth/login/submit` y `/auth/register/submit`, en `SESSIONLESS_FORM_PAGES`) solo comprueban que coincida con la cookie, y si falla se vuelve a su página con un token válido.
- Añadir un formulario a esa lista requiere justificarlo y documentarlo. No se desactiva CSRF dentro de una ruta individual.
- El rate limiting es obligatorio para login, registro, recuperación de credenciales y cualquier endpoint externo costoso o susceptible de abuso.
- La clave de rate limiting debe combinar el identificador de operación con una identidad suficientemente estable, normalmente IP normalizada e identificador normalizado cuando exista. Cómo se obtiene y normaliza la IP se define en `infra_conventions.md` §9.
- Los límites, ventanas y bloqueos se configuran mediante variables de entorno validadas al arrancar.
- Un bloqueo por rate limit devuelve `429` cuando el cliente necesita distinguirlo; no se devuelve `500` ni un `200` ambiguo.
- Los mensajes de autenticación no deben revelar si existe un usuario concreto.

### 5.3 Ownership dentro de SQL

Las queries de lectura privada y todas las queries mutadoras que operen sobre datos de usuario deben recibir `user_id` e incluirlo en la cláusula SQL correspondiente.

Ejemplo conceptual:

```sql
UPDATE intake_event
SET name = %(name)s
WHERE id = %(event_id)s
  AND users_id = %(user_id)s
RETURNING id;
```

Está prohibido hacer un `SELECT` por ID, obtener el registro y comprobar posteriormente en Python si pertenece al usuario cuando la restricción pueda expresarse en SQL.

### 5.4 Recursos ajenos

- Un recurso ajeno que no deba revelar su existencia se trata como inexistente hacia el cliente.
- El endpoint devuelve `404`, no `403`, para ese caso.
- La capa interna puede registrar o clasificar el motivo sin exponerlo en la respuesta.
- La función no debe devolver datos privados antes de comprobar ownership.

## 6. Concurrencia e idempotencia

Esta sección define cómo debe comportarse el sistema cuando dos peticiones acceden o modifican los mismos datos al mismo tiempo, o cuando una petición se repite por reintento del navegador, HTMX, una red inestable o un cliente externo.

No todas las entidades necesitan el mismo nivel de protección. En cada operación se identifica primero el tipo de colisión posible y después se aplica la estrategia mínima que garantice la integridad requerida. La existencia inicial de un único usuario no elimina los reintentos, los dobles envíos ni las peticiones simultáneas desde varias pestañas.

### 6.1 Unicidad

La base de datos es la autoridad definitiva sobre unicidad.

- No usar el patrón “comprobar si existe en Python y después insertar” como garantía de unicidad.
- Las comprobaciones previas solo pueden mejorar el mensaje de usuario; nunca sustituyen una constraint.
- Todo conflicto de constraint se traduce a `ConflictError` y posteriormente a HTTP `409`.
- La condición de unicidad debe incluir todos los campos que formen parte del concepto de duplicado.
- Las comparaciones que ignoren mayúsculas, espacios o valores vacíos deben usar un índice de expresión coherente con la normalización aplicada por Python.
- En entidades con soft-delete, los índices únicos deben ser parciales y contener `WHERE deleted_at IS NULL`.
- La unicidad debe contemplar también el contexto del propietario cuando el recurso sea privado por usuario.
- Toda constraint de unicidad debe tener un nombre estable y documentar qué regla de negocio protege.

### 6.2 Tratamiento de conflictos de unicidad

Una violación de unicidad no se convierte en un error genérico:

- El CRUD o servicio identifica el conflicto como `ConflictError`.
- El endpoint lo traduce a HTTP `409`.
- El mensaje no revela datos privados de otro usuario.
- No se ejecuta una inserción alternativa automática sin documentar su semántica.
- Dentro de una operación compuesta, el conflicto provoca rollback de toda la operación.

Cuando una operación puede terminar correctamente creando una fila o encontrando una fila equivalente ya existente, el resultado no se representa con un `bool` ambiguo:

```python
from enum import Enum


class CreationResult(str, Enum):
    CREATED = "created"
    ALREADY_EXISTED = "already_existed"
```

El CRUD devuelve `CreationResult` o una dataclass que lo contenga. El servicio decide si `ALREADY_EXISTED` es éxito idempotente, `409` o una actualización, según el contrato de la operación.

### 6.3 `ON CONFLICT`

Las operaciones repetibles o susceptibles de peticiones duplicadas usan SQL nativo:

- `ON CONFLICT DO NOTHING` cuando repetir debe ser un no-op.
- `ON CONFLICT DO UPDATE` cuando repetir debe actualizar el mismo recurso.
- La operación debe documentar si devuelve el estado anterior o posterior.
- `DO UPDATE` solo modifica los campos incluidos en el comando y no destruye valores que la petición no pretendía cambiar.
- Las operaciones repetibles deben producir el mismo estado final ante el mismo comando.

Las operaciones toggle deben evitarse para acciones que puedan reintentarse. Preferir `set_favorite(value)` frente a `toggle_favorite()` cuando el cliente pueda repetir la petición.

### 6.4 Idempotencia y reintentos

Una operación es idempotente cuando ejecutarla varias veces produce el mismo estado final que ejecutarla una sola vez.

Cada operación repetible debe definir uno de estos comportamientos:

- repetición como no-op correcto;
- actualización del mismo recurso al mismo estado;
- conflicto `409`;
- error por estado incompatible.

Deshabilitar botones en el frontend evita algunos dobles envíos, pero nunca sustituye la protección del servidor.

Las idempotency keys se reservan para operaciones expuestas a clientes externos, webhooks o reintentos distribuidos que no puedan resolverse con constraints, estados condicionales y `ON CONFLICT`. Si se implementan, se asocian al usuario y operación, se almacenan durante el periodo de reintento y una reutilización con parámetros distintos produce conflicto.

### 6.5 Operaciones compuestas

Las operaciones que modifican varias tablas usan una única transacción. Si necesitan garantizar exclusión o evitar lecturas obsoletas, deben documentar el nivel de aislamiento o el bloqueo utilizado.

Reglas:

- El coordinador abre `connection.transaction()`.
- Todos los CRUD internos reciben `commit=False`.
- Los resultados inesperados se convierten inmediatamente en excepciones.
- Un fallo revierte todas las escrituras de la operación.
- No se confirma una tabla y se continúa con otra fuera de la transacción.
- La operación documenta qué ocurre si una parte ya estaba aplicada.

### 6.6 Lectura seguida de escritura

El patrón “leer estado, comprobar en Python y escribir” puede permitir que dos peticiones tomen la misma decisión. Cuando sea posible, la condición debe formar parte del `UPDATE`:

```sql
UPDATE intake_event
SET state = %(new_state)s,
    updated_at = NOW()
WHERE id = %(event_id)s
  AND users_id = %(user_id)s
  AND state = 'planned'
RETURNING id;
```

En una entidad sin versionado, si este `UPDATE` devuelve cero filas se sabe que la operación no se aplicó, pero no se puede distinguir si el estado incompatible era anterior o resultado de una carrera concurrente. En ese caso se devuelve el conflicto de negocio definido por la operación, normalmente `409`, sin afirmar que se haya detectado una carrera concreta.

### 6.7 Actualizaciones concurrentes del mismo recurso

`ON CONFLICT` resuelve colisiones de creación, pero no evita que dos clientes sobrescriban silenciosamente el mismo recurso.

- Las entidades con transiciones críticas o snapshots clínicos deben usar control de concurrencia optimista.
- Se preferirá una columna `version INTEGER NOT NULL DEFAULT 1` que se incremente en cada update.
- En una entidad versionada, primero se obtiene la fila visible y autorizada junto con su versión.
- El estado de negocio se valida sobre esa fila ya leída.
- El update debe incluir la versión esperada en el `WHERE` y devolver la nueva versión:

```sql
UPDATE resource
SET state = %(state)s,
    version = version + 1
WHERE id = %(resource_id)s
  AND users_id = %(user_id)s
  AND version = %(expected_version)s
RETURNING id, version;
```

**Qué cuenta como "crítico"**: en una aplicación monousuario donde las escrituras concurrentes sobre una misma fila solo pueden llegar del propio usuario (pestañas o dispositivos duplicados, nunca otro actor), `version` no es obligatorio por defecto. Se añade cuando la transición es irreversible o tiene efecto en otra tabla que no pueda deshacerse con un simple `UPDATE` (p. ej. la creación automática de una fila en otra entidad al confirmar). No usar `version` no exime de filtrar por estado esperado en el `WHERE` cuando la transición lo requiera (ver `confirm_intake_event` como ejemplo ya conforme). Este criterio se revisará si la aplicación pasa a admitir edición concurrente de la misma fila por varios usuarios (ver `intake_event`, `conventions/decisions.md`, 2026-09-08).

- Si no se actualiza ninguna fila por una versión obsoleta, se lanza `ConflictError` y el endpoint devuelve `409`.
- Si el update no devuelve fila, una comprobación protegida por ownership distingue `NotFoundError` de `ConflictError`; nunca se consulta el recurso sin filtros de visibilidad.
- Cualquier escritura que cambie la versión entre la lectura y el update se considera conflicto, independientemente de cuándo ocurriera.
- La versión se incrementa en cada actualización relevante. Si se modifican hijos de un agregado crítico, el coordinador decide si también incrementa la versión de la raíz.
- Para datos no críticos puede aceptarse “última escritura gana”, pero debe quedar documentado por entidad; no es el comportamiento implícito por defecto.
- No usar `updated_at` como versión si su precisión o zona horaria no garantizan detectar dos escrituras cercanas. Si se usa temporalmente, debe documentarse como deuda de migración.

### 6.8 Locks y aislamiento

Se puede utilizar `SELECT ... FOR UPDATE` cuando una operación necesite leer una fila, calcular un nuevo estado y mantenerla protegida durante ese cálculo.

- Debe ejecutarse dentro de una transacción explícita.
- Debe utilizar la misma conexión durante toda la operación.
- Debe aplicar ownership y visibilidad.
- Debe mantener el lock el menor tiempo posible.
- Las operaciones que bloqueen varias filas deben adquirirlas siempre en el mismo orden.
- No se usan locks por reflejo cuando un update condicional o el control optimista es suficiente.
- El nivel de aislamiento se modifica solo para una operación justificada, no globalmente.

### 6.9 Agregados y tablas relacionadas

Una tabla sin propietario directo, como `portion_detail`, hereda ownership y consistencia de su aggregate root:

- la query valida el ownership del destino mediante `JOIN` o `EXISTS`;
- el origen se valida aparte según sea público, propio o no visible;
- la modificación del hijo y cualquier actualización de la raíz comparten transacción;
- una modificación del hijo no puede modificar indirectamente el agregado de otro usuario;
- si la raíz usa `version`, se documenta si las modificaciones de hijos incrementan esa versión.

### 6.10 Última escritura gana

“Última escritura gana” solo se permite para datos donde perder una modificación concurrente sea aceptable, como preferencias visuales o filtros de interfaz.

No se acepta por defecto para estados clínicos, dosis, cantidades consumidas, snapshots, eventos confirmados ni históricos. Cada excepción debe documentarse por campo u operación.

### 6.11 Nivel de aplicación

Durante la primera fase, con un único usuario, no es obligatorio añadir `version` a todas las tablas ni crear una infraestructura global de idempotency keys. Sí son obligatorios desde el principio:

- constraints de unicidad;
- `ON CONFLICT` cuando corresponda;
- transacciones para operaciones compuestas;
- estados condicionales en transiciones sensibles;
- protección frente a dobles envíos y reintentos básicos.
- constraints de integridad para valores imposibles;
- unicidad compatible con soft-delete;
- ownership preparado en el modelo y las queries;
- timestamps y unidades coherentes;
- migraciones idempotentes y verificables.

La auditoría clínica completa, los snapshots inmutables, el versionado optimista general, los locks explícitos y las idempotency keys globales se incorporan cuando la operación sea crítica o cuando se habilite concurrencia real entre clientes. Esta es la política de fases común para concurrencia y persistencia; no se duplica en la sección 11.

## 7. Validación y normalización de entrada

La validación garantiza que los datos que llegan al dominio tienen una estructura, tipo y significado válidos antes de ejecutar una operación de persistencia. El servidor es siempre la autoridad final. HTML y JavaScript solo mejoran la experiencia de usuario.

### 7.1 Pipeline obligatorio

Toda entrada debe seguir este orden:

```text
Petición HTTP -> extracción -> normalización -> parseo -> validación individual
-> validación cruzada del payload -> dataclass Request/Command -> servicio o CRUD
```

No se ejecutan queries ni se modifican datos durante la validación sintáctica o del payload. Las reglas que dependan del estado actual de la base de datos pertenecen al servicio o caso de uso y se ejecutan después de construir el comando limpio.

- Validar en helpers reutilizables, no mediante lógica ad-hoc por endpoint.
- Normalizar espacios antes de comprobar campos obligatorios.
- Las cadenas opcionales vacías se convierten uniformemente en `None`.
- Los números se parsean con un helper común que valida formato, finitud, rango y signo.
- Los booleanos solo aceptan valores explícitos. Un valor desconocido produce `422`.
- Las opciones cerradas se validan contra enums/constants centrales.
- Los identificadores se validan antes de ejecutar SQL.
- La misma regla de negocio debe existir en servidor y, cuando sea útil, reflejarse en el formulario.

### 7.2 Normalización frente a validación

La normalización transforma representaciones equivalentes en una forma común, como `"  Tortilla  "` a `"Tortilla"` o `"12,5"` a un número. La validación decide si esa representación es admisible.

No se debe convertir silenciosamente una entrada inválida en un valor válido: `"abc"` no se convierte en `0`, `"maybe"` no se convierte en `False` y una opción desconocida no se convierte en `None`.

### 7.3 Cadenas

- Aplicar `strip()` antes de comprobar obligatoriedad.
- Normalizar espacios internos solo cuando el dominio lo permita.
- Definir una longitud máxima por campo.
- Rechazar cadenas vacías en campos obligatorios.
- Convertir cadenas vacías a `None` en campos opcionales, salvo contrato contrario.
- No truncar silenciosamente.
- Usar la misma normalización en Python y en los índices SQL de duplicados.

La longitud máxima de un campo persistido es la de su columna. El boundary
que recibe el texto debe comprobarla **antes** de llamar a persistencia y
**rechazar** el exceso como `validation_error` (`422`), nunca truncarlo ni
dejar que lo rechace PostgreSQL (`value too long for type character
varying(N)` sale como `500`, un error de cliente convertido en fallo de
servidor). El límite se declara una sola vez como constante en el módulo de
dominio de la tabla (por ejemplo `INTAKE_EVENT_NAME_MAX_LENGTH` en
`domain/intake_event.py`), y todas las rutas y formularios que escriben esa
columna usan esa misma constante — incluido el `maxlength` del `Input`, que
es ayuda de UX y no sustituye la comprobación en servidor. Decisión
2026-09-09.

Una columna `TEXT` no tiene límite físico, pero eso **no la exime** de la
regla anterior: el límite es entonces una decisión de dominio y se declara
igual, como constante en el módulo de dominio de la tabla (por ejemplo
`INTAKE_EVENT_NOTES_MAX_LENGTH`), se comprueba en el boundary y se rechaza el
exceso con `422` sin truncar. El comentario de la columna en `schema.py`
indica que el límite es de dominio y dónde vive la constante. Una columna de
texto libre sin límite declarado es un hallazgo de auditoría, no un caso
permitido. Decisión 2026-09-10.

### 7.4 Campos obligatorios, opcionales y parciales

Se distinguen tres estados:

- campo ausente: no modificar el valor existente;
- campo presente vacío: normalizar según el tipo, normalmente `None`;
- sentinel `CLEAR`: borrar explícitamente un valor nullable.

Para JSON se distinguen así:

- `{}`: campo ausente;
- `{"field": ""}`: campo presente vacío;
- `{"field": null}`: campo presente con `None`;
- `{"field": "__clear__"}`: token de transporte convertido al sentinel interno `CLEAR`.

Los formularios HTML no tienen un valor nativo `null`:

- control ausente: campo ausente;
- control presente vacío: cadena vacía;
- la cadena `"null"` no representa `None`;
- `<campo>__clear=1` solicita limpieza explícita y se convierte a `CLEAR`.

Si se envían simultáneamente un valor y `<campo>__clear=1`, el request es inválido y devuelve `422`. El token JSON y el campo auxiliar HTML se interpretan únicamente en el parser central; los endpoints no crean variantes locales.

### 7.5 Números

Todos los números pasan por un parser común que valida formato, separador decimal, signo, finitud, rango, precisión y escala cuando proceda. No se aceptan `NaN`, `Infinity`, `-Infinity`, contenido parcial ni valores fuera del rango de negocio.

Para campos clínicos, dosis, snapshots o cálculos terapéuticos se usa `Decimal` en Python y `NUMERIC` en PostgreSQL. Los campos existentes `REAL` se convierten en el boundary mediante un helper, sin mezclar arbitrariamente `float` y `Decimal`.

El redondeo se decide por contrato y se realiza en un único punto: almacenamiento, cálculo, presentación o exportación. No se redondean individualmente los sumandos si el resultado debe coincidir con el redondeo de la suma.

### 7.6 Booleanos

Los booleanos solo aceptan el conjunto definido por el transporte. No se permite `value = raw_value == "true"`, porque cualquier valor desconocido se convertiría en `False`.

El parser central define los valores aceptados, por ejemplo `{"true"}` y `{"false"}`. Si los formularios necesitan `on`, `1` u `off`, se declaran una sola vez en ese parser. Cualquier otro valor produce `422`. La ausencia de un checkbox tiene un significado definido por el contrato y no se interpreta automáticamente como `False` en updates parciales.

### 7.7 Enums y opciones cerradas

Los valores cerrados se convierten mediante los enums centrales. Un valor desconocido produce `422`, no un fallback. Los componentes generan sus opciones recorriendo el enum y los servicios reciben el valor ya validado. Las opciones abiertas se validan contra sus tablas de catálogo.

Esto incluye los valores cerrados que llegan en la URL. El tipo de alimento de las rutas de Food (`catalog`, `manual_intake`, `recipe`) es `FoodEntryType` (`domain/constants.py`, decisión 2026-10-27). Cada ruta lo convierte al empezar y responde `422` a un tipo desconocido, en vez de `404` o de seguir sin rama. Las acciones en línea lo devuelven con `app_error_response` y las páginas completas lo lanzan, como el resto de sus errores.

### 7.8 Identificadores, fechas y horas

- Los identificadores de URL, formularios y HTMX se validan antes de ejecutar SQL, y solo se admiten dígitos ASCII: nunca `int()` sobre el texto, que acepta otros dígitos Unicode (`٨`, `８`) y guiones bajos (`1_7`).
- Un id de la ruta (`/food/item/{entry_type}/{entry_id}`) se declara con el tipo común `PathId` (`domain/constants.py`) en la firma de la ruta (`entry_id: PathId`), nunca `int`. Mal formado, lanza `MalformedRequestError` y el handler global responde `400` (`error_conventions.md` §3.1), con `X-Request-ID` y el formato de error común; con `int`, FastHTML respondía un `404` genérico. Es la regla de todas las rutas (2026-11-12, hallazgo 30 de `audit/audits/audit_tags.md`).
- Un id de un formulario, de `hx-vals` o de la query string se lee con `parse_optional_id` (`domain/constants.py`): vacío es `None` y mal formado, `422`.
- Un ID válido sin recurso visible produce `404`.
- No convertir IDs inválidos en `0` o `None`.
- Las fechas y horas usan un formato único y se convierten en el boundary HTTP.
- La entrada local se convierte a UTC mediante helpers comunes.
- No se mezclan conversiones manuales con conversiones de helpers comunes.

### 7.9 Validación cruzada del payload

Comprueba relaciones entre campos del propio request y no necesita consultar la base de datos. Ejemplos: dosis basal obligatoria para `basal`, dosis basal nula para `rapid`, `offset_minutes` solo para eventos, cantidad ingerida no superior a la total, grasas saturadas no superiores a grasas y `CLEAR` solo para campos nullable.

### 7.10 Reglas de negocio dependientes de la base de datos

Las reglas que necesitan conocer el estado actual de la base de datos no pertenecen al parser de entrada. Comprobar que una receta tiene ingredientes, que un evento sigue planificado, que una fila no está archivada, que la versión coincide o que existe ownership pertenece al servicio o caso de uso.

El flujo es:

```text
HTTP -> payload validado -> Command -> servicio consulta estado
-> regla de negocio -> CRUD/transacción
```

No se introduce SQL dentro de un validador sintáctico. La seguridad y el estado deben comprobarse también en las queries mutadoras.

### 7.11 Request, Command y Update

- `Request`: datos HTTP ya parseados y validados.
- `Command`: intención de un caso de uso, sin headers, cookies ni nombres de formulario.
- `Update`: únicamente campos modificables de una entidad.
- Un CRUD no recibe una dataclass específica de HTTP.
- Un update parcial declara el significado de campo ausente, `None` y `CLEAR`.
- No se pasa un diccionario HTTP directamente al CRUD o a `_build_update_query()`.

### 7.12 Ownership

La validación de formato no sustituye la autorización. El usuario de seguridad procede del contexto autenticado, nunca del payload. El flujo es validar ID, obtener usuario, comprobar visibilidad y ownership en SQL, y aplicar la misma condición en la escritura.

### 7.13 Frontend

Los atributos `required`, `min`, `max`, `step`, `pattern` y la validación JavaScript son ayudas de UX. Desactivar JavaScript o enviar una petición manual no debe permitir datos inválidos.

### 7.14 Defaults mostrados en la interfaz

Todo valor que la interfaz muestre como ya elegido (una opción preseleccionada de un `<select>`, un checkbox marcado, un campo numérico ya relleno) tiene que corresponder a un valor **ya persistido** en la base de datos en el momento en que se renderiza. Ningún campo se "adivina" solo visualmente: un `<select>` de un enum sin ningún `<option selected>` explícito lo resuelve el navegador marcando la primera opción de la lista, que el usuario lee como una elección real aunque la base siga en `NULL`; si el guardado es autosave-on-change (§9.5, decisión "refresco local del carrito"), ese valor nunca llega a escribirse porque el usuario no dispara ningún `change`.

Si un campo tiene un valor por defecto razonable, ese default se calcula y se escribe en el mismo momento en que se decide (alta de la entidad, alta de la fila relacionada), no se deja implícito para que lo infiera la interfaz. Cuando de verdad no hay un default fiable, el control debe mostrar un estado "sin elegir" explícito (una opción placeholder sin valor, marcada `selected` cuando el campo es `None`) en vez de aterrizar en la primera opción del enum por accidente del render.

Corolario para defaults "inteligentes" (inferidos de contexto — hora del día, origen del alimento, receta...): la lógica de inferencia vive donde se crea la fila, no en el componente de presentación; el componente sigue leyendo el campo ya resuelto como cualquier otro dato persistido. Un default inteligente que se calcule solo en el momento de renderizar reproduce el mismo defecto que un `<select>` sin `selected`. Ver domain/meal_type_schedule.py y audit/deuda_pendiente.md (sección `intake_event`, H13) para el primer caso real (decisión 2026-09-11).

Esta sección cubre los **defaults**. La regla más general —que todo estado visible, tenga default o no, coincida exactamente con lo que se guardaría— está en `conventions/frontend_conventions.md` sección 6 (decisión 2026-09-18), e incluye el caso de los campos de tres estados (`NULL` / `True` / `False`), que no pueden representarse con un checkbox de dos posiciones.

### 7.15 Texto libre con varios valores

Un campo de texto libre que contiene varios valores (hoy, las smart macros de `catalog` y `manual_intake`) se parsea con una **gramática cerrada**, y todo lo que queda fuera de ella se rechaza con `validation_error` (`422`). No se adivina qué quiso decir el usuario: un valor mal asignado es peor que un error visible (§7.2).

- **Smart macros**: una secuencia de pares `<número> [unidad] <nombre>`, con el número siempre delante (`120kcal 30 hc 12,5 g azucar`). Los pares se separan con espacios, `,`, `;` o `+`, y no hace falta separador. La unidad (`g`, `gr`, `gramos`, `ml`) es opcional y solo se descarta si detrás hay un nombre.
- El nombre se compara **exactamente** (tras minúsculas y sin tildes) con la lista de sinónimos de cada macro, que vive una sola vez en cada lenguaje (`domain/nutrition.py` y `static/js/smart_macros.js`). No se aceptan prefijos parciales.
- Se rechazan: un nombre delante de su número, un número sin nombre, un nombre desconocido, un macro repetido y cualquier otro carácter.
- El servidor es la autoridad. El JavaScript aplica la misma gramática y los mismos mensajes solo como vista previa. Los dos se comprueban contra el mismo juego de casos versionado (`static/data/smart_macros_cases.json`) con `scripts/check_smart_macros.py` y `dbSmartMacrosSelfCheck()`. Cambiar la gramática obliga a cambiar los dos parsers y los casos en el mismo commit.

## 8. Configuración, logging y servicios externos

Esta sección define cómo se configura la aplicación, cómo se registran los eventos operativos y cómo se integran fuentes externas.

Las convenciones de errores pertenecen a `conventions/error_conventions.md`. Las unidades, conversiones y precisión pertenecen a `conventions/measurement_conventions.md`. La concurrencia y los reintentos de operaciones mutadoras siguen la sección 6.

### 8.1 Configuración

Toda la configuración se carga y valida al iniciar la aplicación, en `DayBetes_food/config.py` o en el módulo central que lo sustituya. Las rutas, servicios y queries consumen valores ya parseados y no llaman directamente a `os.getenv()`.

La aplicación distingue como mínimo `development`, `test` y `production`. Un entorno desconocido produce error de configuración y no se activan defaults de desarrollo en producción.

Las variables obligatorias, como `DATABASE_URL` y secretos de autenticación:

- deben existir y no estar vacías;
- deben tener formato válido;
- impiden arrancar si faltan o son inválidas;
- no se sustituyen por valores de ejemplo;
- no se muestran en logs ni respuestas;
- producen un error de arranque con severidad `CRITICAL`.

Las variables opcionales solo pueden tener defaults documentados y seguros. Una variable presente pero inválida no se reemplaza silenciosamente por el default.

Los parsers centralizados deben validar estrictamente booleanos, enteros, decimales, URLs y enums. Los límites de sesiones, rate limiting, timeouts y paginación se definen una sola vez en configuración.

La configuración de desarrollo, test y producción no se mezcla. La inicialización automática del esquema no debe activarse accidentalmente en producción. Ver además sección 12.6 sobre la identidad de conexión separada para el bootstrap.

### 8.2 Secretos y cookies

Los secretos incluyen contraseñas, peppers, tokens, cookies, claves API, claves privadas y URLs con credenciales.

- No se guardan en el repositorio.
- No se incluyen en `repr()` de dataclasses, excepciones o respuestas.
- No se escriben en logs, ni siquiera parcialmente si pudieran reconstruirse.
- `.env` se reserva para desarrollo local y permanece fuera del control de versiones.
- Producción utiliza el mecanismo de secretos del entorno de despliegue.

La configuración de sesión centraliza nombre de cookie, `Secure`, `HttpOnly`, `SameSite`, `Path`, duración, refresco y revocación. Las cookies no contienen datos médicos ni datos de usuario en texto plano.

### 8.3 Logging

El proyecto utiliza el módulo estándar `logging`. Está prohibido usar `print()` para errores, warnings, arranque, migraciones, llamadas externas o eventos de seguridad.

Cada módulo obtiene un logger con `logging.getLogger(__name__)`. La configuración de handlers, formato y niveles se realiza en un único punto.

Niveles:

- `DEBUG`: diagnóstico de bajo nivel sin datos sensibles.
- `INFO`: eventos operativos relevantes y métricas de bajo volumen.
- `WARNING`: anomalías recuperables, rate limiting y degradaciones.
- `ERROR`: fallos que impiden completar una operación.
- `CRITICAL`: fallos que impiden arrancar o continuar de forma segura.

Las validaciones rechazadas, recursos inexistentes y conflictos esperables no se registran individualmente en `INFO` si pueden generar ruido. En tráfico elevado se usan `DEBUG` o métricas agregadas.

Un log puede incluir `request_id`, código interno, operación, módulo, entidad, ID técnico, usuario cuando sea seguro, status y duración. Nunca incluye contraseñas, tokens, cookies, hashes, peppers, claves API, payloads completos ni datos médicos detallados.

Una excepción se registra con traceback una sola vez en el boundary que la convierte en respuesta, según `error_conventions.md`. Las capas inferiores añaden contexto y propagan, pero no duplican el log.

### 8.4 Correlación de peticiones

Toda petición tiene un `request_id` generado por el servidor si no existe.

- El mismo ID aparece en logs, respuestas de error y llamadas externas relacionadas.
- Las respuestas incluyen `X-Request-ID`.
- Las respuestas JSON lo incluyen según `error_conventions.md`.
- No se utiliza como mecanismo de autenticación.
- No contiene tokens, datos médicos ni identificadores sensibles.
- Un valor proporcionado por el cliente se valida y solo sirve para trazabilidad.

### 8.5 Servicios externos

Toda integración externa se implementa mediante un adapter o cliente dedicado. Una ruta no construye directamente llamadas HTTP a proveedores.

El adapter define:

- URL y método;
- autenticación y headers;
- timeout;
- formato de entrada;
- formato esperado de salida;
- validación;
- errores;
- reintentos;
- cache;
- conversión a dataclasses internas.

Toda llamada externa debe:

- tener timeout explícito y configurable;
- validar el status HTTP antes de interpretar el cuerpo;
- comprobar el `Content-Type` cuando proceda;
- validar la estructura JSON recibida;
- capturar errores de red, timeout y parseo;
- convertirse a dataclass interna antes de entrar en el dominio;
- convertir unidades según `measurement_conventions.md`;
- marcar la fuente como `imported`;
- registrar el fallo internamente sin datos sensibles;
- devolver al usuario un mensaje genérico y estable según `error_conventions.md`.

Una respuesta `200` no garantiza que el contenido sea válido, completo o esté expresado en la unidad esperada.

### 8.6 Timeouts y errores externos

Cuando la librería lo permita, se distinguen timeout de conexión, timeout de lectura y timeout total. Nunca se espera indefinidamente.

Un timeout o error de red se convierte en `ExternalServiceError`. No se convierte en una lista vacía, un valor cero ni una respuesta de éxito.

El usuario no recibe el nombre técnico del proveedor, traceback, URL interna ni detalle de la excepción.

### 8.7 Reintentos

Los reintentos se definen por integración y operación. Solo se permiten si el fallo es transitorio, existe un límite, se aplica backoff y la operación es segura de repetir.

No se reintenta automáticamente ante errores de validación, `400`, `401`, `403`, `409` ni operaciones mutadoras no idempotentes.

Los reintentos de operaciones mutadoras siguen las reglas de idempotencia de la sección 6 y pueden requerir idempotency keys. No se implementan reintentos genéricos en un cliente compartido sin conocer la semántica de la operación.

### 8.8 Rate limiting externo

Si un proveedor externo limita las peticiones, el adapter debe detectar la respuesta, respetar `Retry-After` cuando exista, aplicar backoff y evitar reintentos inmediatos.

El fallo se registra con el proveedor y la operación, sin datos sensibles, y se devuelve un error genérico. La política concreta se documenta en el adapter.

### 8.9 Degradación controlada

Si un servicio externo no está disponible:

- no se bloquea indefinidamente la petición;
- no se guarda un registro incompleto como si fuera correcto;
- no se sustituyen datos por ceros;
- no se confunde una respuesta vacía con un fallo;
- se puede utilizar cache solo si está documentada y marcada;
- se informa al usuario con un mensaje genérico;
- la aplicación continúa funcionando si la integración no es esencial.

Un fallback no puede cambiar silenciosamente el significado de los datos.

### 8.10 Cache externo

Si se utiliza cache:

- la clave incluye todos los parámetros relevantes;
- tiene expiración;
- no mezcla datos privados;
- diferencia respuesta vacía de error;
- conserva fuente y timestamp;
- se invalida cuando proceda;
- no sustituye a la base de datos principal;
- no altera la semántica transaccional.

Los datos cacheados se validan de nuevo antes de persistirse.

### 8.11 Checklist de auditoría

Para cada configuración o integración se comprueba:

- ¿Está centralizada?
- ¿Tiene tipo, rango y default definido?
- ¿Falla rápido si es obligatoria?
- ¿Separa entornos?
- ¿Puede activar desarrollo en producción?
- ¿Contiene secretos en logs o respuestas?
- ¿Usa `logging`?
- ¿Tiene `request_id`?
- ¿Registra excepciones una sola vez?
- ¿Existe un adapter para el proveedor?
- ¿Tiene timeout?
- ¿Valida status, Content-Type y estructura?
- ¿Convierte unidades según `measurement_conventions.md`?
- ¿Marca la fuente?
- ¿Los reintentos son seguros?
- ¿La operación es idempotente?
- ¿Existe degradación controlada?

### 8.12 Asistente de registro con IA

Acordado con el usuario el 2026-11-12. Un chat en el que el usuario cuenta lo que ha comido y el asistente lo deja en el carrito para que lo revise y lo confirme. La privacidad está en `study_conventions.md` §7.1, y U1 y U2 en su §6.3.

**Principio: propone y el usuario confirma.** Es la excepción acordada a "no se adivina" (decisión 2026-09-25 y §7.15): el asistente interpreta texto libre, pero nada de lo que hace queda como dato confirmado sin un paso del usuario.

- Solo escribe en comidas `planned`: porciones en el carrito y añadidos rápidos estimados con su porción. El usuario las revisa, las cambia o las borra, y confirma la comida como siempre.
- Un alimento nuevo nunca se crea desde el asistente. Este prepara un borrador y abre el formulario de alta relleno; el usuario lo guarda, y el formulario vuelve al chat.
- No existe ninguna herramienta que borre, archive, edite un alimento, plato o receta existente, confirme una comida, toque una comida consumida, registre una inyección o cambie ajustes. La garantía es que esas herramientas no existen, no una instrucción del prompt.

**Capas**

- Adaptador: `integrations/anthropic_client.py`, con el SDK oficial `anthropic` (versión fija, §10 de `infra_conventions.md`). Cumple §8.5–§8.9: timeout de configuración, errores del proveedor convertidos en `ExternalServiceError` y mensaje genérico al usuario.
- Servicio: `services/assistant.py` lleva el bucle de herramientas y `services/assistant_tools.py` las define. Cada herramienta llama a las mismas queries y servicios que las rutas equivalentes, con la misma validación (§7) y la propiedad en SQL (§5.3). Una entrada no válida se devuelve al modelo como `tool_result` con `is_error`, nunca como `500`.
- Rutas: `routes/assistant_routes.py`. Componentes: `components/assistant/`. JS: `static/js/assistant.js`.

**Configuración** (§8.1)

- `ANTHROPIC_API_KEY`: secreto opcional. Vacío = asistente desactivado: sus rutas no se registran (`404`) y no aparece ningún acceso en la interfaz.
- `ASSISTANT_MODEL`: por defecto `claude-opus-5-5`. Se cambia sin tocar código.
- `ASSISTANT_EFFORT`: por defecto `low`.
- `ASSISTANT_TIMEOUT_SECONDS` y `ASSISTANT_MAX_TOOL_ROUNDS` (rondas de herramientas por mensaje). Al llegar al límite se corta, se guarda lo hecho y se avisa al usuario.

**Datos**

- Los macros de un alimento de la base nunca los calcula ni los copia el modelo: el servidor los lee del alimento, como en cualquier porción. El modelo solo elige el alimento, la cantidad y su `amount_method`.
- Cuando no encuentra el alimento, por este orden de preferencia: lo fijado con `/`, los alimentos y platos del usuario (favoritos y usados primero), sus recetas, Ciqual y OFF. Solo al final estima un añadido rápido.
- Un añadido rápido estimado lleva `macros_source = ai_estimate` y la porción `amount_method = ai_estimate`. Los hidratos y el peso son obligatorios; un macro que no estima queda vacío, nunca a cero (§8.9).
- Las porciones de alimentos de la base llevan el `amount_method` de las reglas de U2, aunque el alimento tenga otro por defecto.
- Las menciones (`/`) viajan como pares `entry_type` + `entry_id`. El servidor las vuelve a leer con la regla de visibilidad (§11.4); una que el usuario ya no ve se descarta y se avisa.

**Coste**

- Al modelo nunca se le envía el catálogo. Busca con herramientas que devuelven como mucho 5 resultados compactos: id, tipo, nombre, marca u origen, hidratos por 100 g y ración.
- El `system` y las herramientas son fijos y van cacheados. La fecha, la hora y las comidas planificadas van en el mensaje del usuario, nunca en el `system`, para no romper la caché.
- Una conversación por comida. No se arrastra el historial de otras.
- Las imágenes se reducen en el navegador antes de enviarlas.
- Se registra el uso (tokens de entrada, de caché y de salida, rondas y duración) por mensaje, sin su contenido (§8.3).

**Conversaciones guardadas.** Cada conversación se guarda con sus mensajes, las llamadas a herramientas y lo que acabó en el carrito (`study_conventions.md` §7.1). Contrato de las tablas en §11.2.9.

**Implementación** (decisiones del usuario del 2026-11-12: dos tablas, envío síncrono, selector de comida y alimentos de Ciqual u OFF mediante el formulario precargado).

- **Llamada al modelo** (`integrations/anthropic_client.py`). Usa `client.beta.messages.create` sin streaming, porque las respuestas son cortas, con `max_tokens` 4096. Lleva tres opciones:
  - pensamiento adaptativo (el valor por defecto del modelo) con `block_binding.prefix_mismatch_behavior = "drop_block"`;
  - caché de toda la petición (`cache_control` de nivel superior);
  - respaldo del servidor ante una negativa (`fallbacks: "default"`).

  `drop_block` hace falta porque la foto guardada es un marcador de texto. Eso cambia el historial al que estaban ligados los bloques de pensamiento anteriores, y sin esta opción la API rechazaría la llamada con un `400`. Los reintentos son los del SDK: dos, con backoff, `Retry-After`, y solo ante 408, 409, 429, 5xx y errores de red. Enviar un mensaje no escribe nada en el proveedor, así que repetirlo es seguro (§8.7).
- **Herramientas** (`services/assistant_tools.py`), en una lista fija y en un orden fijo, porque forman parte del prefijo cacheado:
  - `search_my_foods`: lo que ve en Food, con la consulta de las menciones `/` y como mucho 5 filas;
  - `search_reference_foods`: Ciqual u OFF;
  - `add_food`: un alimento o plato, en gramos o en raciones, con su `amount_method`;
  - `add_recipe`;
  - `add_estimate`: un añadido rápido con `ai_estimate` en U1 y U2;
  - `show_meal`;
  - `draft_new_food`: `ciqual`, `open_food_facts` o `label`.

  Un resultado de Ciqual o de OFF no se añade directamente: se ofrece su formulario de alta precargado, como el de una etiqueta. Las herramientas son `strict`, salvo `add_estimate` y `draft_new_food`. La API admite como mucho 16 parámetros anulables entre todas las herramientas `strict`, y esas dos tienen muchos números opcionales. Sus handlers validan todos los valores igualmente (§7).
- **Turno** (`services/assistant.py`). Cada ronda de herramientas es una transacción: guarda a la vez lo que hacen las herramientas y los mensajes que lo explican, así que la conversación siempre se puede reenviar. Cada herramienta corre en su propio savepoint, y si falla no deja nada. Si una llamada posterior a la primera falla, se conserva lo hecho y se avisa. Al llegar a `ASSISTANT_MAX_TOOL_ROUNDS`, las llamadas pendientes se contestan como no ejecutadas, para que el historial siga siendo válido.
- **Contexto.** Cada mensaje del usuario empieza con un bloque `<daybetes_context>` que escribe el servidor y que la página no muestra. Lleva la hora local, la comida (nombre, hora y lo que ya tiene) y las entradas fijadas con `/`, ya releídas. El `system` está en inglés, es fijo y pide responder en el idioma en que escribe el usuario.
- **Registro** (§8.3). Una línea `INFO` por mensaje del usuario, con la conversación, el modelo, las rondas, los tokens de cada clase, la duración y el resultado. Un fallo del proveedor se registra una vez en la ruta, con el motivo interno del adaptador (`assistant_timeout`, `assistant_status_400`...).
- **Errores.** Las acciones del asistente usan el canal de errores de las acciones en línea: status semántico, cuerpo vacío y toast (`error_conventions.md` §7.1). HTMX no reemplaza nada, y el texto y la foto se quedan en el compositor para volver a enviarlos. Si la comida de la conversación se confirmó o se borró, la respuesta es `404` o `409`, con "That meal was confirmed or deleted. Choose another meal.". Un fallo del proveedor es `502`, con "The assistant is not available right now. Try again in a moment.".

## 9. Endpoints, HTTP y HTMX

### 9.1 Contrato del endpoint

Cada endpoint debe tener una responsabilidad principal y un contrato explícito de:

- método HTTP;
- ruta y parámetros;
- categoría de acceso;
- datos de entrada y transporte;
- servicio o CRUD utilizado;
- unidad de trabajo y ownership de conexión;
- formato de respuesta;
- comportamiento de éxito;
- comportamiento ante repetición.

La decisión entre llamar directamente a CRUD o delegar en un servicio sigue la sección 1.2. Las reglas de excepciones, códigos de error, mensajes y estructuras de error pertenecen exclusivamente a `conventions/error_conventions.md`. Las reglas de validación pertenecen a la sección 7; ownership a la sección 5; transacciones a la sección 2; e idempotencia a la sección 6.

### 9.2 Métodos y rutas

- `GET` solo realiza lecturas.
- `POST` se utiliza para creaciones y acciones de negocio mutadoras.
- `PUT` representa sustitución completa únicamente si el endpoint lo documenta.
- `PATCH` representa actualización parcial únicamente si el endpoint lo documenta.
- `DELETE` se utiliza para borrado físico o eliminación de relaciones según el contrato.
- El soft-delete se expone mediante una acción `archive_<entity>` o una ruta equivalente explícita.

No se utiliza `GET` para modificar datos. **Una ruta solo acepta el método que declara**, y `HEAD` si es un `GET`: otro método responde `405` (decisión 2026-11-06). El método es el nombre de su función (`def post`), y todas las rutas se registran con `single_method_rt` (`routes/http_methods.py`), porque FastHTML, por sí solo, acepta `GET` y `POST` en una función anidada. El arranque falla si una ruta se registra de otra forma y acepta varios métodos. Las rutas usan nombres de recursos claros, parámetros específicos como `event_id` o `recipe_id` y no reciben `user_id` como fuente de autorización.

Una misma entidad usa un único segmento de recurso en todas sus rutas: el plato manual es `manual_intake` tanto al crear como al editar o archivar, y no `manual` en unas y `manual_intake` en otras. Al renombrar una ruta, la antigua se elimina en el mismo cambio y se actualizan todas sus referencias. No se mantienen alias de compatibilidad: una página abierta antes del despliegue recibe un `404` y basta con recargarla (hallazgo 20 de `audit_manual_intake.md`).

### 9.3 Canales y formato de respuesta

Un endpoint debe declarar si devuelve HTML completo, fragmento HTML o JSON. No se mezclan formatos arbitrariamente.

| Situación | HTML tradicional | HTMX | JSON |
|---|---|---|---|
| Navegación correcta | HTML completo | fragmento o `HX-Redirect` | no aplica |
| Creación correcta | `303` o HTML según contrato | fragmento, evento o `HX-Redirect` | `201` o `200` |
| Validación visual | página/formulario según contrato | `200` + fragmento mínimo de error | `422` estructurado |
| Error no visual | según `error_conventions.md` | según `error_conventions.md` | según `error_conventions.md` |

Todos los errores y sus formatos se definen en `conventions/error_conventions.md`. Esta tabla solo define el canal de transporte.

### 9.4 Códigos de éxito y redirecciones

- `200` indica una respuesta correcta con contenido o fragmento.
- `201` indica creación correcta en una API HTTP convencional.
- `204` indica éxito sin cuerpo cuando el cliente no necesita fragmento, evento ni mensaje.
- `303` se utiliza después de un `POST` tradicional cuando la operación termina en navegación.
- Una petición HTMX que termina en navegación utiliza `HX-Redirect`.

Los códigos de error no se redefinen aquí; se aplican desde `error_conventions.md`.

### 9.5 HTMX

Cada acción HTMX debe definir:

- si exige el header `HX-Request`;
- `hx-target` esperado;
- `hx-swap` esperado;
- fragmento devuelto en éxito;
- fragmento mínimo de validación si falla la entrada;
- eventos `HX-Trigger`, si existen;
- navegación posterior, si existe.

Las acciones equivalentes deben usar el mismo patrón.

#### Validación HTMX

Los errores de validación que deban mostrarse dentro de un formulario utilizan deliberadamente:

- status HTTP `200`;
- un fragmento HTML mínimo;
- un target visible y estable;
- el componente común de error;
- ningún redirect ni evento de éxito.

Esta excepción existe para que HTMX inserte el mensaje directamente en el formulario. No se extiende automáticamente a autenticación, autorización, recurso inexistente, conflicto, rate limiting o infraestructura, que conservan sus status semánticos según `error_conventions.md`.

El fragmento mínimo no debe reconstruir la página completa ni ejecutar consultas adicionales innecesarias.

#### Targets y swaps

- `innerHTML`: reemplaza el contenido de un contenedor.
- `outerHTML`: reemplaza el propio componente.
- `none`: no intercambia cuerpo; solo se usa si el contrato depende de headers/eventos o de un refresco posterior.
- `beforeend`: añade contenido y solo se usa cuando la operación es una adición.

El target debe tener un ID estable y una responsabilidad visual única. No se cambia el target entre acciones equivalentes sin actualizar el contrato.

El refresco posterior solo ocurre cuando `event.detail.successful` es verdadero. En los errores de validación HTMX con status `200`, el frontend debe distinguir el fragmento de error mediante el target o contrato específico y no tratarlo como una operación de éxito global.

#### Eventos HTMX

- `HX-Trigger` se reserva para eventos documentados.
- Los nombres de eventos son estables y describen el hecho ocurrido, no una implementación interna.
- Un evento de éxito no se emite en una respuesta de validación fallida.
- No mezclar `HX-Redirect`, `HX-Location` y fragmentos intercambiados para el mismo flujo sin una decisión documentada.

#### Contrato HTMX del carrito

El carrito usa **refresco local**: cada acción devuelve el fragmento mínimo
que ha cambiado, no la página entera (decisión 2026-09-10). Como consecuencia
el `hx-target` deja de ser uniforme, así que la relación acción → target → swap
→ fragmento se declara aquí y no solo en el código. Toda acción HTMX del
carrito exige el header `HX-Request` (`403` si falta) y lleva `hx-target`
**explícito**: sin él, htmx toma como target el propio elemento que dispara la
petición y el swap `outerHTML` lo destruye.

| Acción (`POST /cart/event/{id}/…`) | `hx-target` | `hx-swap` | Fragmento de éxito |
|---|---|---|---|
| `meal_hour` (hora y fecha) | `#cart_events_list` | `outerHTML` | `cart_events_list(...)` — es la única acción que reordena la lista (`meal_time`) |
| `name`, `notes`, `meal_type`, `eating_out`, `insulin_dose`, `injection_zone` | `#cart_card_event_{id}` | `outerHTML` | `CartCard(event, portions, plates)` |
| `insulin_pen` (`insulin_pen_id`, un boli abierto de rápida) e `insulin_units` (vacío es sin dosis), junto a la zona (`measurement_conventions.md` §8.4) | `#cart_card_event_{id}` | `outerHTML` | `CartCard(...)`. Solo con `insulin_dose = TRUE` y la comida `planned` (`409` en otro caso). La opción `+ New pen` no envía nada: abre el pop-up de abrir boli |
| `POST /cart/portion/{portion_id}/amount` (payload `amount_value` + `amount_unit`), `…/offset`, `…/move`, `…/delete` | `#cart_card_event_{id}` | `outerHTML` | `CartCard(event, portions, plates)` |
| `POST /cart/portion/{portion_id}/amount_method` (`value`: un código de `AmountMethod` o vacío = "no indicado"; sustituye a `…/strictly_weighed` el 2026-11-12, U2 de `study_conventions.md` §6.3. `…/macros_quality` se retiró el 2026-10-09: es un dato del alimento, `measurement_conventions.md` §6.11) | `#macros_summary_event_{id}` | `outerHTML` | `Div(MacrosSummary(...), id="macros_summary_event_{id}")`; el `<select>` nativo ya muestra su valor, así que no hay swap OOB. Un código desconocido es `422` |
| `POST /cart/portion/{portion_id}/is_cooked_weight` | `#macros_summary_event_{id}` | `outerHTML` | `Div(MacrosSummary(...), id="macros_summary_event_{id}")` |
| `POST /cart/portion/{portion_id}/fridge` (guardar parte en la nevera, `frontend_conventions.md` §7.15) | `#cart_card_event_{id}` | `outerHTML` | `CartCard(event, portions, plates)` y el evento `fridgeStored` |
| `POST /cart/event/{id}/plate`, `POST /cart/plate/{plate_id}/name`, `…/offset`, `…/apply_offset`, `…/delete` | `#cart_card_event_{id}` | `outerHTML` | `CartCard(event, portions, plates)` |
| `delete`, `confirm` | `#cart_card_event_{id}` | `outerHTML` | cuerpo vacío (la tarjeta desaparece) y, si no queda ningún evento planificado, swap OOB de `#cart_body` con el carrito vacío. `confirm` añade el evento `mealConfirmed` con el id de la comida |
| `confirm` con una tanda no comida entera y sin `leftovers_reviewed` | `#cart_leftovers_body` (`HX-Retarget`) | `innerHTML` (`HX-Reswap`) | el pop-up de sobras (`frontend_conventions.md` §7.14), sin escribir nada; el mismo patrón que la confirmación de quitar un favorito. Un error de validación del plan de sobras es `200` con `ModalFormError` reenviado a `#cart_leftovers_message` |
| `POST /cart/event/{event_id}/recipe` y `POST /cart/plate/{plate_id}/recipe` (guardar la comida o la tanda como receta, `frontend_conventions.md` §7.13) | `#cart_card_event_{id}`, declarado pero sin swap | `none` | cuerpo vacío y el evento `recipeSaved` (`HX-Trigger`); `static/js/cart_units.js` muestra el aviso de éxito `Recipe saved`. La tarjeta no cambia |
| `archive`, `restore` | página completa del carrito | `outerHTML` | `cart_main(...)`; no están enlazadas desde ninguna tarjeta todavía |

Los dos flags de tres estados se repintan **fuera de banda** junto al resumen: el control lleva
en `hx-vals` el estado siguiente, calculado en el servidor, así que si no se repinta desde la fila
recién guardada sigue enviando el mismo valor y muestra un estado que la fila ya no tiene
(`frontend_conventions.md` §6). El checkbox de `is_cooked_weight` no lo necesita: el navegador ya
pinta su propio estado.

El borrado de un ingrediente tiene **ruta propia** (`…/delete`) y no se expresa como cantidad `0`
(decisión 2026-09-22): `…/amount` responde `422` a `<= 0`. Un mismo endpoint no puede tener dos
comportamientos irreversiblemente distintos según el payload (§9.1, §9.2).

Fragmento de error: ninguno. Las acciones del carrito son ediciones en línea,
no un formulario de guardado, así que **no** aplican la excepción de `200` +
fragmento de esta misma sección: conservan el status semántico de su categoría
y el aviso viaja por el canal de error visible definido en
`error_conventions.md` §7. Eventos `HX-Trigger`: `appError`; en el éxito de
guardar una tanda o una comida como receta, `recipeSaved`; y al confirmar, `mealConfirmed`,
que cierra el pop-up de sobras (`static/js/fridge.js`).

Añadir un botón nuevo al carrito obliga a elegir una de las filas de esta
tabla o a añadir una nueva; no se deja el `hx-target` implícito.

#### Contrato HTMX de la nevera

La pestaña `Fridge` de Food (`frontend_conventions.md` §9.8, `routes/fridge_routes.py`) sigue el
modelo del carrito: cada acción exige `HX-Request` (`403` si falta), lleva `hx-target` explícito y
devuelve la lista entera de tuppers, que es pequeña. Los errores que no son de formulario viajan
por el canal de error visible (`error_conventions.md` §7.1).

| Acción | `hx-target` | `hx-swap` | Fragmento de éxito |
|---|---|---|---|
| `GET /food/fridge/{id}/actions`, `…/actions/edit`, `…/actions/discard` (vistas del pop-up de acciones) | `#food_actions_modal_body` | `innerHTML` | la vista; `static/js/food_actions.js` abre el pop-up al llegar la primera |
| `POST /food/fridge/{id}/location` (`location`) | `#food-list` | `innerHTML` | la lista. Repetirla es un no-op (§6.3) |
| `POST /food/fridge/{id}/discard` | `#food-list` | `innerHTML` | la lista y el evento `fridgeChanged`, que cierra el pop-up |
| `POST /food/fridge/{id}/edit` (`name`, `expires_at`, `content_weight`) | `#fridge_edit_message` | `innerHTML` | cuerpo vacío, la lista fuera de banda (`#food-list`) y `fridgeChanged`. Un error de validación es `200` con `ModalFormError` en ese mismo destino (excepción de formulario de esta sección) |
| `GET /food/fridge/{id}/actions/take` (vista de sacar) | `#food_actions_modal_body` | `innerHTML` | la vista |
| `POST /food/fridge/{id}/take` (`amount_value`, `amount_unit`, y `intake_event_id` y `plate_id` de la cabecera) | `#fridge_take_message`; `none` desde `Eat` | `innerHTML` | cuerpo vacío, la lista fuera de banda y `fridgeChanged` y `fridgeTaken`. Un error de validación es `200` con `ModalFormError` |
| `GET /food/actions/{entry_type}/{id}/fridge` (guardar desde la fila) | `#food_actions_modal_body` | `innerHTML` | la vista |
| `POST /food/fridge/store_recipe/{recipe_id}` (paso previo de una receta, `frontend_conventions.md` §9.7) | `#recipe_add_error` | `innerHTML` | cuerpo vacío y `fridgeStored`, que cierra también ese pop-up. Validación: `200` + fragmento |
| `POST /food/fridge/store/{entry_type}/{id}` (desde la ficha, `frontend_conventions.md` §9.4, o desde la fila) | el mensaje de la ficha o `#food_actions_store_message` | `innerHTML` | cuerpo vacío y `fridgeStored` con el sitio. El error de validación es `200`: `ModalFormError` dentro del pop-up, que la ruta reconoce por `HX-Target`, y el mensaje de la ficha fuera |

Eventos `HX-Trigger`: `fridgeChanged` (cierra el pop-up), `fridgeTaken` y `fridgeStored` (avisos de éxito, porque la página no muestra la comida ni el tupper nuevo), en `static/js/fridge.js`, y, en los errores, `appError`. Sacar a una comida nueva añade `mealCreated` (`frontend_conventions.md` §7.7).

#### Contrato HTMX de los bolis y las marcas

Páginas `Pens` y `Brands` de ajustes y pop-up de abrir boli (`frontend_conventions.md` §9.9, `routes/insulin_routes.py`). Cada acción exige `HX-Request` (`403` si falta). Un error de validación de un formulario es `200` con `ModalFormError` en el mensaje del pop-up (excepción de formulario de esta sección); el resto de errores viajan por el canal de error visible (`error_conventions.md` §7.1).

| Acción | `hx-target` | `hx-swap` | Fragmento de éxito |
|---|---|---|---|
| `POST /insulin/pens` (abrir un boli: `insulin_brand_id` o los campos de una marca nueva, `format`, `opened_date`) | `#insulin_pen_modal_error` | `innerHTML` | cuerpo vacío y `penCreated` con `{id, label, insulin_type}`: `static/js/insulin_pens.js` cierra el pop-up, añade el boli a los selectores de boli de la página y lo elige en el que abrió el pop-up |
| `POST /insulin/pens/{id}/update` (`format`, `expires_date`, `capacity_units`) | `#insulin_pen_edit_error_{id}` | `innerHTML` | cuerpo vacío e `insulinChanged`, que cierra el pop-up y repinta la lista |
| `POST /insulin/pens/{id}/discard` | ninguno | `none` | cuerpo vacío e `insulinChanged` |
| `POST /insulin/brands` y `POST /insulin/brands/{id}/update` (`name`, `insulin_type`, `in_use_days`, `pen_units`) | `#insulin_brand_form_error` / `#insulin_brand_edit_error_{id}` | `innerHTML` | cuerpo vacío e `insulinChanged` |
| `POST /insulin/brands/{id}/delete` | ninguno | `none` | cuerpo vacío e `insulinChanged` |
| `GET /settings/insulin/pens/list` y `GET /settings/insulin/brands/list` | `#insulin_pens_body` / `#insulin_brands_body` | `innerHTML` | la lista de bolis o de marcas, con sus pop-ups. `static/js/insulin_pens.js` repinta la de la página abierta |

| `POST /menu/injection_log` (`insulin_pen_id`, `units`, `zone`, `shot_hour`, `shot_date`) | `#menu_injection_error` | `innerHTML` | cuerpo vacío e `injectionLogged`, que cierra el pop-up, avisa y repinta el menú |
| `POST /settings/injections/{id}/update` (los mismos campos) | `#settings_injection_error_{id}` | `innerHTML` | cuerpo vacío e `injectionUpdated` con el pop-up, que lo cierra y repinta el registro |
| `POST /settings/injections/{id}/delete` | ninguno | `none` | cuerpo vacío e `injectionUpdated` |

Eventos `HX-Trigger`: `penCreated`, `insulinChanged`, `injectionLogged` e `injectionUpdated`, en `static/js/insulin_pens.js`, y, en los errores, `appError`.


La entrada se extrae y valida según la sección 7 antes de crear el `Request` o `Command`. El usuario autenticado procede del contexto de sesión.

Los botones que disparan escrituras deben deshabilitarse o mostrar estado de carga. Esta protección mejora la UX, pero no sustituye las reglas de idempotencia de la sección 6.

Cada endpoint mutador debe documentar qué ocurre si se repite la petición: no-op, mismo resultado, conflicto `409` o error por estado incompatible.

### 9.7 Paginación

Los endpoints paginados utilizan una única convención:

- `limit`: máximo de elementos;
- `offset`: desplazamiento;
- `page`: solo cuando el endpoint utiliza páginas explícitas;
- cursor: solo cuando el endpoint documenta paginación por cursor.

Los valores se validan, se limitan y no pueden ser negativos. Los resultados tienen orden estable. No se mezclan `page`, `offset` y cursor en el mismo endpoint sin un contrato explícito.

### 9.8 Observabilidad HTTP

Los endpoints utilizan la correlación definida en la sección 8.4 y aplican el formato de respuesta de errores de `error_conventions.md`.

### 9.9 Nombres de los parámetros de una ruta

Decisión 2026-10-09. FastHTML resuelve cada parámetro de una ruta buscándolo, en este orden, en los parámetros de la ruta, las cookies, **las cabeceras HTTP** (con `_` convertido en `-`), la query y, por último, el cuerpo del formulario. Un campo de formulario que se llame como una cabecera toma el valor de la cabecera y no lo que escribió el usuario, sin ningún error: el campo `origin` guardó `http://0.0.0.0:8000` porque todo `POST` del navegador lleva la cabecera `Origin`.

- Un parámetro de ruta que venga del formulario o de la query no puede llamarse como una cabecera que envíe el navegador o HTMX: `origin`, `referer`, `host`, `cookie`, `accept`, `user_agent`, `content_type`, `content_length`, `connection`, `cache_control`, `priority`, `hx_request`, `hx_current_url`, `hx_target`, `hx_trigger`, `hx_trigger_name`, `hx_prompt`, `hx_boosted`, `x_csrf_token` y cualquier otra cabecera estándar.
- Tampoco puede llamarse como una cookie de la aplicación ni como un nombre especial de FastHTML (`request`, `session`, `htmx`, `data`, `body`, `app`, `state`, `auth`, `scope`).
- Si el concepto se llama así en el dominio, el campo lleva un prefijo (`source_origin` para `manual_intake.origin`) y la ruta lo traduce al nombre de dominio al construir la Request (§7.11).
- Las pruebas contra la aplicación envían las cabeceras de un navegador real (`Origin`, `Referer`, `HX-Current-URL`, `HX-Target`, `HX-Trigger`): sin ellas este fallo no aparece.

## 10. Tipos de datos, fechas y números

Esta sección define la representación técnica de fechas y números dentro del código. El significado de cada campo, su unidad canónica, precisión de negocio y reglas de redondeo pertenecen exclusivamente a `conventions/measurement_conventions.md`.

### 10.1 Mapa de tipos

La conversión entre PostgreSQL, Python y los contratos externos sigue este mapa:

| PostgreSQL | Python | JSON/HTML |
|---|---|---|
| `INTEGER`, `BIGINT` | `int` | número |
| `REAL`, `DOUBLE PRECISION` heredado | `float` | número aproximado |
| `NUMERIC` | `Decimal` | string decimal exacto |
| `BOOLEAN` | `bool` | booleano |
| `TIMESTAMP` UTC heredado | `datetime` mediante mapper | ISO 8601 en boundary |
| `TIMESTAMPTZ` | `datetime` aware | ISO 8601 en boundary |
| `NULL` | `None` | `null` cuando el contrato lo permita |

No se mezclan `float` y `Decimal` en una misma operación. Cuando una migración obligue a convertir un valor heredado `float` a `Decimal`, se utiliza una conversión controlada y documentada, no `Decimal(float_value)` directamente.

### 10.2 Autoridad de unidades y precisión

- `measurement_conventions.md` decide la unidad, precisión, escala, redondeo y significado de cada campo.
- Esta sección decide únicamente cómo se representa y se transporta ese valor técnicamente.
- Un cambio de unidad o precisión requiere seguir la migración documentada en `measurement_conventions.md` y en la sección 10.5.
- No cambiar el tipo de una columna solo para corregir una etiqueta visual.
- No añadir una conversión local en una ruta si ya existe un mapper o helper central.

### 10.3 Números y cálculos

- Los campos existentes `REAL` pueden seguir usando `float` durante la fase de recopilación y análisis exploratorio.
- Los campos nuevos que participen en dosis, snapshots clínicos o decisiones terapéuticas usan `NUMERIC` con escala explícita y `Decimal` en Python.
- Los cálculos clínicos no convierten `Decimal` a `float` para ahorrar trabajo.
- Los campos `REAL` que pasen a tener uso clínico se migran prioritariamente siguiendo la sección 10.5.
- `None` se conserva como ausencia de dato; no se convierte automáticamente a cero.
- Los cálculos usan la unidad canónica, nunca una unidad de presentación.
- El redondeo se realiza en el punto definido por `measurement_conventions.md`.
- Las comparaciones de `float` utilizan tolerancia explícita; no se usa igualdad directa.

### 10.4 Fechas y zonas horarias

Las fechas y horas se almacenan en UTC según `measurement_conventions.md`. La implementación se realiza en boundaries y helpers comunes:

- La entrada del usuario se interpreta en la zona horaria de la aplicación.
- El dominio nuevo utiliza `datetime` aware en UTC.
- Las columnas heredadas `TIMESTAMP` sin zona reciben un UTC naive únicamente en el mapper de persistencia.
- La conversión aware UTC a naive UTC ocurre solo al escribir en una columna heredada sin zona.
- La conversión naive UTC a aware UTC ocurre solo al leer una columna heredada.
- La presentación convierte UTC a la zona local del usuario.
- No usar `datetime.utcnow()` ni `datetime.now()` sin zona en código nuevo.
- No depender de la zona horaria del sistema operativo o de la sesión PostgreSQL.
- Usar helpers centrales como `utc_now()`, `local_to_utc()` y `utc_to_local()`.

Los formatos JSON de fecha y hora utilizan ISO 8601 con offset explícito. Los timestamps UTC se serializan con `Z` o `+00:00`; no se envían fechas ambiguas sin zona.

### 10.5 Migraciones de tipos

Cambiar `REAL` a `NUMERIC`, o `TIMESTAMP` a `TIMESTAMPTZ`, es una migración de datos y no un cambio aislado de schema.

Antes de ejecutarla se debe:

1. Identificar columnas, tablas, queries, mappers y dataclasses afectadas.
2. Definir precisión, escala, zona y redondeo.
3. Detectar y limpiar valores inválidos.
4. Definir la expresión `USING` de conversión.
5. Convertir datos existentes sin perder `NULL`.
6. Actualizar constraints y defaults.
7. Actualizar Python, serialización y cálculos.
8. Revisar índices y funciones SQL.
9. Verificar muestras antes y después.

No se mezcla una migración de tipo con una corrección funcional salvo que la corrección dependa directamente de la precisión o de la zona horaria.

### 10.6 Serialización de `Decimal`

`Decimal` no se serializa automáticamente con `json.dumps()`. Para conservar la precisión exacta, los valores `Decimal` se serializan como strings decimales en JSON:

```json
{
  "basal_units": "8.50"
}
```

Reglas:

- El formato decimal debe ser estable y no usar notación científica salvo que el contrato lo defina.
- La escala visible debe seguir la precisión documentada del campo.
- El cliente no debe interpretar automáticamente un valor clínico string como `float` sin conocer el contrato.
- HTML puede formatear el valor para presentación, pero no modifica el valor de dominio.
- Un endpoint puede devolver un número JSON únicamente si el contrato declara que la precisión exacta no es relevante.
- No convertir globalmente todos los `Decimal` a `float` en un encoder genérico.
- Las respuestas y requests JSON deben probar valores normales, `NULL`, escalas y números grandes.

El mapper es responsable de convertir entre `Decimal` y el formato del transporte. Las rutas no deben implementar conversiones independientes.

## 11. Base de datos, soft-delete y auditoría

La base de datos es la última barrera de integridad del sistema. Las validaciones de Python mejoran los mensajes y la experiencia, pero no sustituyen constraints, índices, claves foráneas ni transacciones.

La semántica de unidades, precisión y valores pertenece a `measurement_conventions.md`. Los errores producidos por constraints siguen `error_conventions.md`. Las estrategias de concurrencia e idempotencia siguen la sección 6.

### 11.1 Definición de propiedad y ciclo de vida

Cada tabla debe documentar explícitamente:

- su propietario, si lo tiene;
- la columna física que identifica al propietario;
- si esa columna representa propietario actual, creador o actor;
- si es pública, privada o mixta;
- si es archivable, no archivable, histórica o dependiente;
- quién puede crear, leer, modificar, archivar, restaurar y borrar;
- qué ocurre cuando se elimina el usuario propietario.

`created_by` significa creador/actor y no se interpreta automáticamente como propietario actual. Solo puede utilizarse como filtro de ownership en una tabla cuando el contrato de esa tabla documente explícitamente que creador y propietario son la misma persona. Si se permiten transferencias o recursos compartidos, debe existir una columna de propietario separada.

Los nombres físicos heredados pueden variar entre tablas, pero la capa Python debe usar `user_id` según la sección 3.5 y los mappers deben declarar la correspondencia física.

### 11.2 Entidades archivables y no archivables

Cada entidad se clasifica antes de implementar sus operaciones:

- **Archivable**: conserva la fila y utiliza `deleted_at`.
- **Non-archivable**: permite borrado físico porque no necesita preservar el registro.
- **Historical**: conserva el registro y puede requerir auditoría o prohibir el borrado normal.
- **Dependent**: su ciclo de vida depende de un aggregate root.

La clasificación no se deduce del verbo de una función. Debe documentarse por tabla y reflejarse en CRUD, endpoints, FKs e índices.

Excepcionalmente, una tabla puede tener clasificación híbrida condicionada por una columna de estado, cuando esa columna distingue de forma inequívoca un valor sin vida propia (ej. un borrador) de un valor con valor histórico o clínico. Esto debe documentarse explícitamente por tabla, incluyendo qué valores de la columna caen en cada clasificación; no se asume implícitamente. Ejemplo: `intake_event.state = 'planned'` es no archivable, `state = 'consumed'` es archivable (`conventions/decisions.md`, 2026-09-08).

#### 11.2.1 Registro de clasificación por tabla

La clasificación de cada tabla se declara en este registro, que es el sitio único donde "debe documentarse por tabla" (2026-09-23). Al cerrar la auditoría de una tabla se añade o actualiza su fila. Una clasificación que no está decidida se escribe como **pendiente** con su referencia; no se deduce del código ni de la naturaleza de la tabla.

| Tabla | Clasificación | Borrado | Fuente |
|---|---|---|---|
| `users` | **Pendiente**: ciclo de vida sin definir (sin `deleted_at` y sin ninguna ruta que ponga `is_active = FALSE`). | Ninguno hoy. | `audit/AUDIT_PLAN.md` (documento local, fuera de git), "Deuda técnica ya conocida". |
| `auth_sessions` | **Dependent** de `users` (operativa, ni clínica ni histórica). | Físico: `ON DELETE CASCADE` desde `users` y purga a los 14 días. | `audit/audit_auth_sessions.md`; decisión 2026-09-02/03. |
| `auth_rate_limits` | **Pendiente**: no hay clasificación documentada. | Físico en la práctica (contador operativo). | Sin auditoría propia; extraída de `auth/service.py`. |
| `catalog` | **Archivable**, irreversible (sin `restore_`). Contrato completo en §11.2.2. | Solo `deleted_at`; nunca físico (otras personas tienen porciones, recetas y favoritos que apuntan al alimento). | `audit/audits/audit_catalog.md`, hallazgos 5 y 6; decisiones 2026-09-23 y 2026-09-24. |
| `food_brands` | **Pendiente**: por naturaleza no archivable (catálogo auxiliar), pero `is_active` actúa como soft-delete de facto y no encaja en §11.2/§11.3. | Sin función de borrado. | `audit/audit_food_brands.md`; `audit/deuda_pendiente.md`, H4 y H11. |
| `insulin_injections` | **Historical**. Pendiente decidir si es archivable (`deleted_at`) o no archivable con borrado físico documentado. | Físico (statu quo). | `audit/audit_insulin_injections.md`; `audit/deuda_pendiente.md`, "Clasificación archivable / no archivable". |
| `intake_event` | **Híbrida por `state`**: `planned` no archivable, `consumed` archivable. | Físico en `planned`; `deleted_at` en `consumed`. | Decisión 2026-09-08. |
| `manual_intake` | **Archivable**, irreversible (sin `restore_`), con el mismo contrato que `catalog`. Contrato completo en §11.2.3. | Solo `deleted_at`; nunca físico (porciones de eventos consumidos y, si se publica, favoritos y recetas de otros usuarios apuntan al plato). | `audit/audits/audit_manual_intake.md`, hallazgos 5 y 14; decisiones 2026-10-09. |
| `recipe` | **Non-archivable**, con borrado físico solo por su propietario. Contrato completo en §11.2.4. | Físico: lo consumido no referencia la receta. Se revisa en la fase 2. | Decisión del usuario (2026-11-05), `audit/audits/audit_recipe.md`. |
| `user_favorites` | **Dependent** de su usuario y de su alimento, plato o receta. Una fila también concede visibilidad sobre lo retenido. Contrato completo en §11.2.5. | Físico: al quitar el favorito, y `CASCADE` desde `users`, `catalog`, `manual_intake` y `recipe`. Sin auditoría de cambios. | Decisión del usuario (2026-11-06), `audit/audits/audit_user_favorites.md`. |
| `recipe_plate` | **Dependent** de `recipe`. | `CASCADE` desde `recipe`; borrar una tanda con ingredientes está bloqueado. | `measurement_conventions.md` §4.7. |
| `off_product` | **Datos de referencia**, sin propietario: los ven todos los usuarios y la app no los escribe (`init_db` le retira esos permisos). | Físico: cada carga reemplaza la tabla entera, en una transacción (`scripts/off/load_off.sh`). | `measurement_conventions.md` §12.2. |
| `ciqual_food` | **Datos de referencia**, igual que `off_product`. | Físico: cada carga reemplaza la tabla (`scripts/ciqual/load_ciqual.sh`). | `measurement_conventions.md` §12.3. |
| `portion_detail` | **Dependent** de su destino (`intake_event`, `recipe` o `fridge`); hereda su propietario y su ciclo de vida. | `CASCADE` desde el destino. El borrado físico es apropiado en recetas y en eventos `planned`; en un evento `consumed` es histórico clínico y hoy lo impide la ruta, no la query (limitación declarada). | `audit/audit_portion_detail.md`; `measurement_conventions.md` §6.9.3; `audit/deuda_pendiente.md`, `portion_detail` H27. |
| `fridge` | **Híbrida por uso**: un tupper del que nunca se ha sacado nada es no archivable; uno con alguna porción consumida que lo referencia es histórico. Contrato completo en §11.2.6. | Físico si nada lo referencia; si no, `closed_at`. `CASCADE` desde `users`. | Decisión del usuario (2026-11-07), `audit/audits/audit_fridge.md`. |
| `fridge_move` | **Dependent** de `fridge`: historial de cambios de sitio, de solo inserción (el rol de ejecución no puede modificar ni borrar filas). | `CASCADE` desde `fridge`. | Decisión del usuario (2026-11-07), `audit/audits/audit_fridge.md`. |
| `insulin_brand` | **Híbrida por uso**: una marca sin bolis es no archivable; una con algún boli es archivable (`deleted_at`), sin `restore_`. Contrato completo en §11.2.7. | Físico si ningún boli la usa; si no, `deleted_at`. `CASCADE` desde `users`. | Decisión del usuario (2026-11-08). |
| `insulin_pen` | **Híbrida por uso**, como `fridge`: un boli sin inyecciones es no archivable; uno con alguna es histórico y se cierra (`closed_at`). Contrato completo en §11.2.7. | Físico si ninguna inyección lo referencia; si no, `closed_at`. `CASCADE` desde `users`. | Decisión del usuario (2026-11-08). |
| `tags` | **Mixta**: las de sistema (`SystemTag`, sin propietario) son de todos y fijas; las personales son de un usuario. Non-archivable. Contrato completo en §11.2.8. | Físico, solo las personales y solo su propietario; sus enlaces se van con ellas (`CASCADE`). `CASCADE` desde `users`. | Decisión del usuario (2026-11-08), `audit/audits/audit_tags.md`. |
| `linked_tags` | **Dependent** de su usuario, su etiqueta y su alimento, plato o receta. Privada. Contrato completo en §11.2.8. | Físico: al quitar la etiqueta, y `CASCADE` desde `users`, `tags`, `catalog`, `manual_intake` y `recipe`. | Decisión del usuario (2026-11-08), `audit/audits/audit_tags.md`. |
| `assistant_conversation` | **Histórica** y privada: una conversación del asistente con un usuario, ligada a una comida. Non-archivable. Contrato completo en §11.2.9. | Solo `CASCADE` desde `users`; ninguna ruta la borra. Si se borra su comida, `intake_event_id` pasa a `NULL` y la conversación se conserva. | Decisión del usuario (2026-11-12), §8.12. |
| `assistant_message` | **Dependent** de `assistant_conversation`: sus mensajes, de solo inserción (el rol de ejecución no puede modificar ni borrar filas). Contrato completo en §11.2.9. | `CASCADE` desde su conversación. | Decisión del usuario (2026-11-12), §8.12. |

#### 11.2.2 Contrato de ciclo de vida de `catalog`

Decisión 2026-09-24 (`conventions/decisions.md`). Cuando un contrato no cabe en una fila del registro de §11.2.1, se desarrolla en una subsección propia como esta.

- **Propietario**: `created_by`. En `catalog`, creador y propietario son la misma persona y no hay transferencias (§11.1).
- **Biblioteca general**: las filas con `created_by IS NULL` son la biblioteca general de la web (alimentos cargados por scraping y, en el futuro, los de usuarios eliminados). Nadie las edita, archiva ni versiona. Para cambiarlas, se copian.
- **Visibilidad**: personal o publicado, con la regla común de §11.4.1. Todo nace personal y publicar es explícito. Despublicar tiene para los demás la misma semántica que archivar. La regla se aplica en SQL (§11.4).
- **Archivar**:
  - Solo lo hace el propietario. Es **irreversible** (§11.3, excepción 2026-09-23), salvo el undo de 15 s.
  - Un alimento archivado **sale de las búsquedas y listados para todos**, incluido su propietario.
  - **Sigue visible** para quien lo tenga en favoritos o en una receta propia, con la etiqueta "Archivado". **Se puede seguir usando tal cual** por todos los caminos que crean porciones (registrar, ingrediente de receta, añadir comida, importar receta a un evento, rescate). No hay que copiarlo antes.
  - Nadie lo edita ni lo versiona. Se puede copiar.
  - Se puede quitar de favoritos, pero no añadirlo.
  - El histórico de comidas no se toca.
  - La lectura que incluye archivados visibles lo declara con un parámetro explícito (§11.3).
  - El texto del modal describe lo que ocurre de verdad: se retira del catálogo, y quien ya lo usa puede seguir usándolo. No se llama "borrar".
  - Al archivarlo, se quita de los favoritos de su propietario en la misma transacción (decisión 2026-09-24).
- **Origen de los macros, método de la cantidad y confianza declarados** (decisión 2026-10-09, extensión a `catalog`; listas cerradas U1/U2 desde el 2026-11-12, `study_conventions.md` §6.3): `macros_source` (dato del alimento, leído en vivo por la porción), `default_amount_method` (se copia a la porción al crearla) y `macros_confidence` (escala `0–2`), los tres opcionales (`NULL` = sin dato), con el mismo significado que en `manual_intake` (`measurement_conventions.md` §6.10 y §6.11). Los alimentos existentes el 2026-10-09 empiezan en `NULL`. `glycemic_index` e `ig_confidence` no existen en `catalog` (sin decidir).
- **Corregir no es archivar**: si los valores de un alimento son incorrectos, se corrigen editándolos (con el versionado, creando una versión nueva). Archivar queda para "ya no lo mantengo" o "está duplicado".
- **Copiar**:
  - Crea una **fila nueva** con su propio `id`, `created_by` = quien copia y `origin_root_id` = el alimento raíz de la familia. Una copia de una copia también apunta a la raíz.
  - Duplica los datos y es independiente del original: archivar o cambiar uno no afecta al otro.
  - Lo puede copiar cualquiera que vea el alimento, **también su propietario**, por ejemplo para partir de él y crear una variante (decisión 2026-10-27). Hasta entonces, copiar un alimento propio y activo abría su edición en vez de copiarlo. La copia se llama `<nombre> (copy)`, queda en favoritos de quien copia y se abre en edición. Lo mismo vale para `manual_intake` (§11.2.3) y `recipe`.
  - Con el versionado, además guarda `origin_version_id` y crea su propia v1. **Copiar solo hace falta para tener valores distintos**: las fechas de vigencia son de cada usuario y se gestionan sobre cualquier alimento visible, sin copiarlo (decisión 2026-09-24, versionado).
  - Los alimentos con el mismo `COALESCE(origin_root_id, id)` forman una **familia**.
- **Versionado**: los valores son del dueño del alimento y la línea de tiempo de vigencias es de cada usuario (decisión 2026-09-24). El diseño está pendiente de implementar y se detalla en `audit/deuda_pendiente.md`, `portion_detail` H1. Mientras no exista, el alimento se comporta como si tuviera una única versión.
- **Multiusuario** (diseñado, no se construye todavía): se aplican las reglas de congelación de versiones y de aviso de H1. Que las copias nazcan personales ya no es algo solo de multiusuario: lo cubre la regla general de §11.4.1.

#### 11.2.3 Contrato de `manual_intake`

Decisiones 2026-10-09 (`conventions/decisions.md`). Las unidades, la entrada de nutrientes, el índice glucémico y las confianzas están en `measurement_conventions.md` §5.4, §5.5, §6.10 y §6.11.

- **Qué va a cada tabla**:
  - `catalog`: productos industriales (envasados, de supermercado, con etiqueta o código de barras) e ingredientes genéricos (plátano, tomate, arroz).
  - `manual_intake`: lo que ha preparado alguien, sea un local (restaurante, bar, puesto, cadena) o una persona (la abuela, un amigo), **aunque sus macros se conozcan** por la carta o por internet. El criterio es quién lo ha preparado, no si se conocen los macros: un Whopper es un plato manual con origen "Burger King" y `macros_source = official`.
  - Si se conocen los ingredientes y sus cantidades, se registra como receta con ingredientes de `catalog`, no como plato manual.
- **Dos tipos de fila**, distinguidos por `is_quick_add BOOLEAN NOT NULL DEFAULT FALSE`:
  - **Plato reutilizable** (`is_quick_add = FALSE`): se guarda para volver a usarlo y se puede publicar para que otros lo reutilicen.
  - **Añadido rápido** (`is_quick_add = TRUE`, "Quick add" en la interfaz): una comida puntual (un plato, una comida entera o varios platos) que se registra en un evento y no se quiere recordar. Se guarda en la base, pero no se ofrece para reutilizarla.
- **Propietario**: `created_by`, `NOT NULL`. Creador y propietario son la misma persona y no hay transferencias (§11.1). No hay biblioteca general de platos: toda fila tiene creador. La FK a `users` conserva `ON DELETE CASCADE`; borrar un usuario sigue bloqueado por el `RESTRICT` de `portion_detail` (decisión 2026-09-22).
- **Campos del plato reutilizable**:
  - Obligatorios: `name` y `carbs_100g` (`NOT NULL` también en la base). Un `0` de hidratos es un valor válido; lo que no se admite es "no lo sé".
  - Opcionales (`NULL` = sin dato, nunca `0`): `description` (500 caracteres, constante `MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH`, §7.3), `subtype`, `origin`, el resto de nutrientes, `caffeine`, `alcohol`, `default_portion`, `glycemic_index`, `ig_confidence`, `macros_confidence`, `macros_source` y `default_amount_method`.
  - Los macros se introducen por 100 g o como total de una porción (`measurement_conventions.md` §5.4).
- **Añadido rápido**:
  - Se abre desde el botón "Quick add" de la página principal y desde la opción equivalente del `+` de la página de Food.
  - El formulario lleva arriba el selector de comida y tanda (el mismo que hay bajo el buscador de Food y en la ficha de un alimento). Debajo: nombre, peso estimado, macros del total (smart macros), de dónde salen los macros (`Macros from`, U1) y cómo se obtuvo el peso (`Weight from`, U2), los dos opcionales y vacíos al abrir (decisión 2026-11-12, `study_conventions.md` §6.3), y notas, que se guardan en `description`. Son obligatorios el nombre, el peso y los hidratos.
  - No pide `subtype`, `origin`, índice glucémico ni confianzas: se quedan en `NULL`.
  - Al guardar, en una sola transacción, se crea la fila (`default_portion` = peso, nutrientes convertidos a 100 g según §5.4, `macros_source` y `default_amount_method` los elegidos, o `NULL`) y su porción en la tanda elegida, con `amount` = peso.
  - Solo existe a través de su porción. No aparece en búsquedas, listados, favoritos, etiquetas, sugerencias de origen ni en el selector de ingredientes de receta.
  - No se puede publicar: `CHECK (NOT (is_quick_add AND is_published))`.
  - No entra en los índices únicos: puede haber varios "Menú del día".
  - No se puede editar por ahora. Solo se puede cambiar la cantidad de su porción en el carrito, que escala los macros como en cualquier porción. Corregir sus valores queda para el futuro historial de comidas en estadísticas (`audit/deuda_pendiente.md`, sección `manual_intake`).
  - Si se borra su porción, la fila se queda en la base, invisible. Es un comportamiento interino: qué conviene hacer con ella está pendiente en la deuda.
  - Pendiente (`audit/deuda_pendiente.md`, sección `manual_intake`): convertirlo después en plato reutilizable.
- **Visibilidad y publicación**: regla común de §11.4.1, en SQL. Solo se publican platos reutilizables.
  - Se publica y despublica con la acción Publish/Unpublish de la ficha, como en `catalog`. Sustituye a la casilla "Published" de la edición, que la decisión 2026-09-25 solo admitía de forma provisional.
  - Concepto de duplicado: nombre normalizado + origen normalizado, con un origen `NULL` equivalente a la cadena vacía. Es la "marca" de §11.4.1 para esta tabla. El `409` de publicar dice que ya existe un plato publicado con ese nombre y ese origen.
- **`origin`**: de dónde viene el plato, sea una persona ("abuela Geno") o un lugar ("Saona", "Burger King").
  - Texto libre de 255 caracteres como máximo (constante de dominio, §7.3).
  - Se normaliza con la misma función que el nombre, compartida por Python y por los índices SQL (§7.3, §11.5).
  - Autocompletado con los orígenes de los platos activos propios y de los publicados; nunca con los de platos personales ajenos ni con los de añadidos rápidos.
  - Sirve para buscar (el buscador encuentra por nombre o por origen) y para el análisis por origen.
  - No es una enumeración abierta de §4.5.
- **Archivar, corregir, copiar y versionar**: el mismo contrato que `catalog` (§11.2.2), salvo lo que allí depende de la biblioteca general, que aquí no existe. Archivar es irreversible, solo lo hace el propietario, saca el plato de búsquedas y listados para todos, lo mantiene visible y utilizable para quien lo tenga en favoritos o en una receta propia, y en la misma transacción lo quita de los favoritos del propietario. Corregir no es archivar. La tabla de versiones (`portion_detail` H1) cubre también `manual_intake`.
- **Concurrencia**: en la edición gana la última escritura (§6.7, §6.10), como en `catalog`. No hay columna `version` y se documenta en el docstring de la función de edición. Alta, copia, archivar, publicar y despublicar se comportan al repetirse como en `catalog`.
- **Porciones de un plato manual**:
  - Se muestran cocción, conservación y estado final.
  - Nunca se muestra `Cooked weight`, porque un plato manual no tiene `cooking_factor` (`measurement_conventions.md` §5.2). Esto vale para el carrito y para la ficha.
  - Cambiar la cantidad de la porción escala los macros (§5.2), como en `catalog`.
  - `amount_method` nace con el `default_amount_method` del plato; `macros_source` no se guarda en la porción, se lee en vivo del plato (`measurement_conventions.md` §6.11).

#### 11.2.4 Contrato de `recipe`

Decisión del usuario del 2026-11-05. Una receta es una comida o un plato recurrente que se reutiliza para añadirlo rápido al carrito. Solo hay un tipo de receta, con una o más tandas (`measurement_conventions.md` §4.7). Una comida de base fija que varía cada día es una receta con la base, y lo del día se añade en el carrito.

- **No es histórico.** Lo confirmado referencia a los alimentos, nunca a la receta: cambiarla o borrarla no toca ninguna comida. Tampoco guarda datos del estudio.
- **Propietario y visibilidad.** `users_id` es el propietario y es `NOT NULL`; en Python se expone como `user_id` (§3.5). La lee quien la posee o quien la ve publicada. Solo el propietario la edita o la borra. Todo va en SQL: `get_recipe` y `list_recipes` llevan la visibilidad en el `WHERE`, y `update_recipe` y `delete_recipe` al propietario.
- **Quien no es propietario** la usa, la marca como favorita, la copia y la añade a su carrito. No ve controles de edición (§9.4 de `frontend_conventions.md`).
- **Campos.** `name` normalizado (`normalize_food_text`, `ck_recipe_name_normalized`); `notes`, texto libre del usuario de hasta `RECIPE_NOTES_MAX_LENGTH` que puede contener toda la preparación; `meal_type` opcional, sin `rescue`, que tiene su propio flujo (`exercise` sí, 2026-11-08), y es el tipo principal: el que toma una comida creada desde la receta; `extra_meal_types`, otros tipos con los que también se come, que solo sirven para encontrarla (decisión 2026-11-06). Necesitan un principal y no lo repiten (`ck_recipe_extra_meal_types_need_main`); `servings` opcional, entero de 1 a 100; `created_at` y `updated_at`. La preparación de cada ingrediente son campos de su porción, no notas.
- **Editar** es una sustitución completa: un opcional vacío se guarda como `NULL` (§3.4). Gana la última escritura (§6.7, §6.10).
- **Unicidad.** `uq_recipe_personal_name` por propietario y `uq_recipe_published_name` entre publicadas, sobre `lower(name)`. Una receta no tiene marca, así que el duplicado es solo el nombre. Se puede llamar igual que la receta publicada de otra persona.
- **Copiar** (§11.2.2) crea una receta personal y editable, en favoritos, con sus tipos de comida, notas, raciones, tandas con ingredientes e ingredientes. No copia etiquetas. La original no se toca.
- **Borrar** es físico y lo hace solo el propietario: `CASCADE` a tandas, porciones y favoritos, y `SET NULL` en las copias. Quien la tuviera en favoritos la pierde.
- **Auditoría de cambios** (§11.10): no se requiere, porque no es dato clínico.

#### 11.2.5 Contrato de `user_favorites`

Decisión del usuario del 2026-11-06. Es la tabla puente entre un usuario y sus favoritos: exactamente un alimento (`catalog`), un plato (`manual_intake`) o una receta (`recipe`) por fila. Es una preferencia, no un dato clínico: las comidas confirmadas no la leen.

- **Propietario.** `user_id`, `NOT NULL`, que es propietario y actor a la vez; no hay transferencias. Es privada: cada usuario solo lee y escribe sus filas. El propietario del alimento no interviene, salvo al archivar (§11.2.2).
- **Una fila también concede visibilidad.** Quien tiene en favoritos un alimento o plato despublicado o archivado lo sigue viendo y usando (§11.2.2, §11.4.1). Por eso añadir una fila es una decisión de autorización, y su condición va en el SQL (§5.3).
- **Escritura.** `set_user_favorite(value)`, nunca un toggle (§6.3). Cada petición dice el estado que quiere, y repetirla es un no-op.
- **Añadir.** Solo lo que el usuario puede listar. Si no lo ve, `NotFoundError`; si lo ve porque está retenido, `ConflictError`; si ya es favorito, no-op (`CreationResult.ALREADY_EXISTED`). Quien crea o copia un alimento lo añade en la misma transacción, y al archivar el propietario pierde su propio favorito; los demás lo conservan.
- **Quitar.** Se puede siempre, sin pedir visibilidad, y es un `DELETE`: volver a marcarlo crea otra fila igual, así que un `deleted_at` no aportaría nada. Si el favorito era lo único que daba acceso, un despublicado solo se recupera si el propietario vuelve a publicarlo, y un archivado no se recupera nunca. Por eso la interfaz lo confirma antes (§9.3.2 de `frontend_conventions.md`); si el alimento también está en una receta propia, sigue visible y no se pregunta.
- **Borrado.** Las cuatro FK son `CASCADE`, porque un favorito no significa nada sin sus dos extremos y no destruye ningún histórico. Hoy solo se dispara desde `recipe`: nadie borra usuarios, y alimentos y platos se archivan.
- **Recetas.** Borrar o despublicar una receta no tiene retención: quien la tiene en favoritos la pierde, aunque la fila de una receta despublicada se puede quitar. Se revisa en la fase 2, con la propuesta anotada en `audit/deuda_pendiente.md`: conservarla como los alimentos archivados, porque un aviso tras un borrado físico llega tarde.
- **Timestamps.** Solo `created_at`: las filas nunca se actualizan, así que un `updated_at` no cambiaría nunca. En las filas anteriores a esta decisión es la fecha de la migración (§12.7).
- **Auditoría de cambios** (§11.10): no se requiere, porque no es dato clínico ni alimenta modelos.

#### 11.2.6 Contrato de `fridge`

Decisión del usuario del 2026-11-07. Cada fila es **un tupper** guardado en la nevera o en el congelador: sobras de una comida, una tanda cocinada para varios días o algo que llega hecho (un tupper que te dan). No hay despensa a temperatura ambiente. El modelo y las cantidades están en `measurement_conventions.md` §4.8.

- **Propietario.** `users_id`, `NOT NULL`, propietario y actor a la vez; en Python, `user_id` (§3.5). Es privada: solo su propietario la lee y la escribe, con la condición en el SQL.
- **Contenido.** Sus ingredientes son porciones de `portion_detail` con destino `fridge_id`, escaladas como las de una receta. Un tupper de un solo alimento tiene una sola porción.
- **Abierto y cerrado.** Un tupper con `closed_at` nulo está en la nevera o en el congelador. Se cierra con un motivo, `closed_reason`: `emptied` al sacar lo último que queda y `discarded` al tirarlo si ya se había sacado algo. Un tupper cerrado no se lista. Solo uno vaciado se reabre, cuando vuelve lo sacado de él porque se borra la comida o el ingrediente antes de confirmar (`measurement_conventions.md` §4.8.6).
- **Tirar.** Si ninguna porción de una comida lo referencia (`portion_detail.source_fridge_id`), se borra físicamente con su contenido y su historial: lo que se tira no se guarda. Si alguna lo referencia, se cierra como tirado, porque esas porciones son histórico clínico. La base lo impide con una FK `NO ACTION DEFERRABLE INITIALLY DEFERRED` (§11.8): con `RESTRICT` la comprobación se hace dentro de cada cascada y borrar un usuario fallaba si la cascada llegaba al tupper antes que a la porción que lo referencia. Como el error saldría en el commit, tirar bloquea primero el tupper, en una sentencia aparte (§6.8), y solo después comprueba si hay porciones que lo referencian: así ve la porción de una toma que termina mientras espera y cierra el tupper en vez de intentar borrarlo.
- **Caducar no borra.** Un tupper caducado sigue abierto y se marca en la interfaz hasta que el usuario lo tira o se lo come (`frontend_conventions.md` §9.8).
- **Cambiar de sitio.** Actualiza `location`, recalcula `expires_at` (`measurement_conventions.md` §4.8) y añade una fila a `fridge_move` en la misma transacción.
- **Borrado del usuario.** `CASCADE` desde `users`, como el resto de sus datos.
- **Auditoría de cambios** (§11.10): no se requiere. El dato del estudio son las porciones consumidas y `fridge_move`, que es en sí el historial.
- **`fridge_move` es de solo inserción.** La aplicación añade movimientos y los lee, pero nunca cambia ni borra uno: `init_db` retira al rol de ejecución `UPDATE`, `DELETE` y `TRUNCATE` sobre la tabla (decisión 2026-11-07). La cascada desde `fridge` sigue borrándolos, porque las acciones referenciales se ejecutan con los permisos del propietario de la tabla.
- **Timestamps de `fridge_move`.** Solo `moved_at`, que se fija al insertar la fila y nunca cambia, así que hace de `created_at`; no lleva `updated_at` (decisión 2026-11-07, que cierra para esta tabla lo que la del 2026-11-06 dejó pendiente). `fridge` lleva `created_at` y `updated_at`, porque su nombre, su caducidad, su peso, su sitio y su cierre cambian.

#### 11.2.7 Contrato de `insulin_brand` e `insulin_pen`

Decisión del usuario del 2026-11-08. Modelo y cálculo de lo que queda en `measurement_conventions.md` §8.4.

- **Propietario.** `users_id`, `NOT NULL`, propietario y actor a la vez; en Python, `user_id` (§3.5). Las dos son privadas: solo su propietario las lee y las escribe, con la condición en el SQL. Un boli solo puede ser de una marca del mismo usuario, y una inyección o una comida solo pueden apuntar a un boli del mismo usuario: lo comprueba la query que escribe, en el mismo `UPDATE`/`INSERT`.
- **Nombre de la marca.** Obligatorio, normalizado (espacios de los extremos fuera e internos colapsados) y de hasta `INSULIN_BRAND_NAME_MAX_LENGTH` caracteres. Único por usuario entre las marcas activas, sin distinguir mayúsculas: índice único parcial `uq_insulin_brand_users_id_name` sobre `(users_id, lower(name)) WHERE deleted_at IS NULL` (§11.5). Un choque es `409`.
- **Borrar una marca.** Si ningún boli la usa, se borra físicamente; si alguno la usa, se archiva (`deleted_at`) y deja de ofrecerse al abrir un boli, pero sus bolis siguen abiertos y se siguen viendo. No hay `restore_` (decisión 2026-09-23). FK `insulin_pen.insulin_brand_id` `NO ACTION DEFERRABLE INITIALLY DEFERRED`, por el mismo motivo que la de `fridge` (§11.2.6): con `RESTRICT`, borrar un usuario fallaría si la cascada llegara antes a la marca que al boli.
- **Abierto y cerrado.** Un boli con `closed_at` nulo está en uso. Se cierra con un motivo, `closed_reason` (`PenCloseReason`: `empty`, `expired`, `discarded`), deducido al cerrarlo (`measurement_conventions.md` §8.4). Un boli cerrado no se lista en los selectores ni se puede elegir para una inyección nueva; sí se muestra como el boli de las inyecciones que ya lo usan. No se reabre.
- **Descartar un boli.** Bloquea el boli (§6.8). Si ninguna inyección lo referencia, se borra físicamente; si alguna lo referencia, se cierra. FK `insulin_injections.insulin_pen_id` `NO ACTION DEFERRABLE INITIALLY DEFERRED`, como la de la marca. Las comidas `planned` que lo tenían elegido pasan al boli por defecto en la misma transacción; `intake_event.insulin_pen_id` es `ON DELETE SET NULL`, porque es un borrador.
- **Borrado del usuario.** `CASCADE` desde `users`, como el resto de sus datos.
- **Auditoría de cambios** (§11.10): no se requiere. El dato del estudio son las inyecciones.
- **Timestamps.** Las dos llevan `created_at` y `updated_at`, que se escribe en cada `UPDATE`.

#### 11.2.8 Contrato de `tags` y `linked_tags`

Decisión del usuario del 2026-11-08 (`audit/audits/audit_tags.md`). Sustituye a las etiquetas globales y al botón provisional `Rescue` (decisión 2026-10-11).

- **Dos clases de etiqueta.** Las **de sistema** no tienen propietario (`users_id` nulo) y se identifican por `system_key`, un valor de `SystemTag` (`rescue`, `exercise`), nunca por el nombre. Su nombre visible es una etiqueta de presentación del enum, `SYSTEM_TAG_LABELS` (`components/food/tags.py`, §3.6), que usan las píldoras, ajustes y las pestañas del pop-up de rescate (decisión del usuario, 2026-11-12). La fila guarda la clave en `name`, que no se muestra ni se compara; las filas creadas antes conservan `Rescue` y `Exercise`, sin efecto, porque el bootstrap no las reescribe. Las crea el bootstrap si faltan, y nadie las renombra, recolorea ni borra. Las **personales** son de un usuario (`users_id`), sin `system_key`. `ck_tags_owner` exige una cosa o la otra.
- **Visibilidad.** Cada usuario ve y usa las de sistema y las suyas. Las de otro usuario no existen para él: editarlas, borrarlas o enlazarlas da `404` (§5.4).
- **Nombre.** Obligatorio, normalizado (`ck_tags_name_normalized`) y de hasta `TAG_NAME_MAX_LENGTH` caracteres (40; la columna admite 100). Único por propietario sin distinguir mayúsculas: `uq_tags_users_id_name` sobre `(users_id, lower(name)) WHERE users_id IS NOT NULL`. Una personal no puede llamarse como el nombre visible de una de sistema, sin distinguir mayúsculas: lo comprueban las rutas que crean o renombran, contra `SYSTEM_TAG_LABELS`, antes de escribir. Un choque es `409`.
- **Color.** `#RRGGBB` (lo que da el selector) o el `hsl(h s% l%)` que se calcula del nombre al crearla. `ck_tags_color` lo exige, porque el valor acaba dentro de un atributo `style`.
- **Edición concurrente.** Renombrar o recolorear es "última escritura gana": dos pestañas que editan la misma etiqueta conservan el último guardado (§6.7, monousuario; §6.10, es una preferencia, no un dato clínico).
- **Enlace (`linked_tags`).** Una fila dice que un usuario puso una etiqueta en un alimento, plato o receta: `users_id`, `tag_id` y exactamente una de `catalog_id`, `manual_intake_id`, `recipe_id` (`ck_linked_tags_one_entry`). Es **privada**: nadie lee los enlaces de otro, así que etiquetar un alimento de la biblioteca general o publicado no cambia nada para los demás. Se puede etiquetar todo lo que el usuario ve, retenidos incluidos (regla de visibilidad de §11.4.1), con una etiqueta de sistema o suya: las dos condiciones van en el `INSERT`. Una fila por usuario, etiqueta y entrada (`uq_linked_tags_users_id_tag_id_<columna>`).
- **Etiquetas de sistema en recetas.** Se pueden poner, pero son solo una marca: el pop-up de rescate ofrece alimentos y platos, no recetas (`frontend_conventions.md` §9.6), así que una receta `Rescue` o `Exercise` no aparece en sus pestañas (decisión del usuario, 2026-11-12).
- **Operación.** `set_entry_tag(..., linked)` deja el enlace como se pide, y repetirla no hace nada (§6.3). Quitar no comprueba la entrada: si ya no existe o no es visible, también es un no-op con éxito. No hay reemplazo en bloque de todas las etiquetas de una entrada.
- **Crear desde la ficha.** Escribir un nombre pone la de sistema con ese nombre visible, o la personal del usuario con ese nombre, o crea una. Si otra petición acaba de crear la misma, se reutiliza en vez de dar `409`: la inserción va en un savepoint y, si choca, se vuelve a buscar (§6.2).
- **Contrato de las queries** (§3.4). `update_tag` y `delete_tag` lanzan `NotFoundError` si la etiqueta no es del usuario, es de sistema o ya no existe, como `update_recipe` y `delete_recipe`; no devuelven `False`.
- **Borrado.** Una etiqueta personal se borra físicamente y sus enlaces con ella. Todo hace `CASCADE` desde `users`; los enlaces, también desde su etiqueta y su entrada. Ninguna de las dos es dato clínico: el tipo de comida de cada evento es lo que cuenta para el estudio.
- **Copias.** Copiar un alimento, plato o receta no copia sus etiquetas.
- **Timestamps.** Solo `created_at` en las dos (decisión 2026-11-06 sobre tablas sin cambios con valor). `description` existe y no se usa (fase 2).
- **Auditoría de cambios** (§11.10): no se requiere.
- **Datos anteriores** (migración única, `_migrate_tags_to_owners`, backfill técnico de §12.7). `Rescate` pasó a ser la de sistema `rescue`. Cada enlace tomó el propietario de su alimento, porque hasta entonces solo él podía etiquetarlo, y cada etiqueta, el de sus enlaces (con una copia por propietario si había más de uno). Se borró una etiqueta sin enlaces y se fusionaron las del mismo propietario que solo se distinguían en mayúsculas o espacios (`Alto en fibra` / `alto en fibra`), comparando el nombre ya normalizado. La copia por propietario no funciona si dos propietarios compartían una etiqueta, porque el `UNIQUE (name)` global antiguo se quita después de migrar: la migración aborta. Se deja así porque hay un único usuario (decisión del usuario, 2026-11-12). Los datos que la migración no admite (un color fuera de `TAG_COLOR_PATTERN`, por ejemplo) se corrigen a mano antes de desplegar, si aparecen; la migración sigue abortando si quedan (§12.2).


#### 11.2.9 Contrato de `assistant_conversation` y `assistant_message`

Decisión del usuario del 2026-11-12. Guardan cada conversación del asistente (§8.12) para medir sus errores (P1) y auditarlo (`study_conventions.md` §7.1).

- **Propietario.** `assistant_conversation.users_id`, `NOT NULL`, propietario y actor a la vez; en Python, `user_id` (§3.5). Es privada: solo su propietario la lee y la escribe, con la condición en el SQL. Los mensajes heredan el propietario de su conversación, y toda lectura de un mensaje hace `JOIN` con ella.
- **Una conversación por comida.** `intake_event_id` es la comida en la que escribe. Es `NULL` hasta que su primer añadido crea la comida, y vuelve a `NULL` si la comida se borra (`ON DELETE SET NULL`). Solo se enlaza a una comida `planned` del mismo usuario, y lo comprueba la sentencia que escribe (§5.3). La base no lo impone con una FK compuesta porque `intake_event` no tiene un único `(users_id, id)`. Si una comida tuviera varias conversaciones, se abre la última.
- **Se crea con su primera respuesta guardada.** Un mensaje cuya primera llamada al modelo falla no deja ninguna fila.
- **Mensajes.** Cada fila es un mensaje de la API de Claude, tal como se envió o se recibió: `role` (`AssistantRole`), `position` desde 1 (única por conversación) y `content`, la lista de bloques en `JSONB`, nunca vacía. La conversación se reenvía al modelo a partir de estas filas, en orden. Por eso son de **solo inserción**: `init_db` retira al rol de ejecución `UPDATE`, `DELETE` y `TRUNCATE` sobre `assistant_message`, como en `fridge_move` (§11.2.6). Añadir bloquea antes la fila de la conversación, para que dos envíos simultáneos no choquen en la posición (§6.8).
- **Fotos.** Nunca se guardan. Se envían una vez y en la fila se sustituyen por un marcador de texto (`study_conventions.md` §7.1).
- **Uso.** Las filas `assistant` llevan el uso de esa respuesta: tokens de entrada, de escritura y lectura de caché, de salida, duración y `stop_reason`. Las filas `user` no llevan ninguno (`ck_assistant_message_usage_role`). `stop_reason` es un conjunto abierto de la API, así que no tiene CHECK.
- **Qué acabó en el carrito.** Los resultados de las herramientas (`tool_result`) lo dicen: el alimento, los gramos, los hidratos y el `amount_method` de cada añadido, o el borrador de un alimento nuevo. La página los vuelve a leer de ahí al reabrir una conversación.
- **Borrado.** Solo `CASCADE` desde `users`; los mensajes, desde su conversación. Ninguna ruta borra una conversación.
- **Timestamps.** La conversación lleva `created_at` y `updated_at`, que cambia con cada mensaje y al enlazarla a su comida. Los mensajes solo llevan `created_at`, porque no cambian.
- **Auditoría de cambios** (§11.10): no se requiere. Los mensajes son en sí el historial.

Una entidad archivable utiliza un campo nullable `deleted_at`.

- `NULL` significa registro activo.
- Un timestamp significa registro archivado.
- Archivar es una actualización, no un `DELETE` físico.
- Restaurar elimina `deleted_at` y comprueba de nuevo los conflictos de unicidad.
- Archivar actualiza también `updated_at`.
- Las lecturas normales excluyen archivados.
- Las consultas que incluyan archivados deben indicarlo explícitamente en su nombre o parámetros.
- Sugerencias, búsquedas, listados y joins deben respetar el filtro activo por defecto.
- Los endpoints no deben obtener una fila archivada para filtrarla después en Python.

Las operaciones se llaman `archive_<entity>` y `restore_<entity>`. Las entidades no archivables utilizan `delete_<entity>` y documentan por qué el borrado físico es correcto.

**Excepción documentada (decisión 2026-09-23)**: la restauración **no se construye por defecto**. Una entidad archivable sin `restore_` queda irreversible; no se le añade salvo que el usuario lo indique expresamente para esa tabla. `catalog` es el primer caso (archivar un ítem no tiene vuelta atrás). Las rutas de restauración ya existentes (p. ej. `intake_event`) se conservan. El caso normal de equivocación se cubre con el **undo** de la última acción destructiva, con una ventana de 15 segundos (`audit/deuda_pendiente.md`, "Undo de la última acción destructiva", 2026-09-23). Consecuencia sobre la unicidad: al no existir `restore_`, el índice único parcial de §11.5 nunca tiene que resolver el conflicto de "restaurar una fila equivalente a otra ya activa".

### 11.4 Lecturas y escrituras con visibilidad

Una query debe declarar su intención de visibilidad: solo activos, solo archivados, todos o visibles para un usuario.

Para una entidad cuyo propietario físico sea `owner_column`, una lectura de recursos públicos y propios sigue este patrón:

```sql
WHERE entity.id = %(entity_id)s
  AND entity.deleted_at IS NULL
  AND (
      entity.owner_column = %(user_id)s
      OR entity.is_published
  )
```

`owner_column` representa la columna propietaria real de la tabla; no se escribe literalmente si no existe. Para una escritura, la visibilidad pública nunca concede permiso:

```sql
WHERE entity.id = %(entity_id)s
  AND entity.owner_column = %(user_id)s
```

El owner column real debe aplicarse dentro de SQL y estar documentado por tabla. La lógica detallada de ownership y agregados sigue la sección 5 y la sección 6.9.

#### 11.4.1 Alimentos personales y publicados

Aplica por igual a `catalog`, `manual_intake` y `recipe` (decisión 2026-09-24, privacidad). Cada tabla la implementa en su propia auditoría.

**Significado.** Un alimento es **personal** o **publicado**.
- **Personal**: solo lo ve su propietario. Significa "no publicado", **no "secreto"**: si antes estuvo publicado, lo que otros ya tengan de él no desaparece (ver *Despublicar*).
- **Publicado**: entra en la búsqueda y en los listados de todos.
- El diario del usuario (eventos, porciones, dosis) es siempre privado y no se rige por esta regla.
- Físicamente es la columna **`is_published`**: `TRUE` = publicado y `FALSE` = personal. Sustituye a `is_private` en las tres tablas, con el valor invertido. El renombrado se hace a la vez en las tres, dentro de la auditoría de `catalog`, para que nunca convivan dos nombres con significados opuestos.
- **Por qué `is_published`** y no `is_private` ni `is_personal`: nombra la acción que existe de verdad en la interfaz ("Publish"/"Unpublish"). Con `FALSE` como valor por defecto, un `INSERT` que olvide la columna deja el alimento personal, que es el lado seguro. Y "personal" se confundiría con "es mío", porque un alimento publicado también puede ser mío. En la interfaz se habla siempre de "personal" y "publicado", nunca de "privado" y "público".

**Por defecto, todo nace personal.** Crear un alimento, copiarlo o crear una receta produce un alimento personal (`is_published DEFAULT FALSE`). Publicar es una acción explícita del propietario. La biblioteca general (`created_by IS NULL`, §11.2.2) siempre está publicada: `CHECK (created_by IS NOT NULL OR is_published)`.

Los formularios de alta de las tres tablas no ofrecen publicar (decisión 2026-09-25): se crea siempre personal y se publica después con la acción del propietario.

**Qué ve cada usuario** (la condición va en SQL, §11.4):
- en la búsqueda y los listados: los alimentos publicados y activos, más los suyos (personales o publicados) activos;
- además, los que dejaron de estar visibles para él (despublicados o archivados) pero tiene en favoritos o en una receta suya. Esos siguen la regla de visibilidad del archivado de §11.2.2.

**Unicidad** (§6.1, §6.2, §11.5). Hay dos índices únicos parciales, los dos con `deleted_at IS NULL` y con la normalización única del nombre. En `manual_intake`, el papel de la marca lo hace el origen normalizado y los añadidos rápidos quedan fuera de los dos índices (§11.2.3):
- **Personales**: únicos **por propietario**, es decir `(created_by, nombre normalizado, marca) WHERE NOT is_published`. Que otra persona tenga un alimento personal igual no impide crear el tuyo, y el sistema no revela que existe.
- **Publicados**: únicos **entre todos los publicados**, incluida la biblioteca general: `(nombre normalizado, marca) WHERE is_published`.
- **Publicar** un alimento cuando ya hay uno publicado equivalente da **`409`**. El mensaje dice que ya existe un alimento publicado con ese nombre y esa marca, sin nada de datos privados. El usuario puede cambiar el nombre y volver a publicar. Tener un alimento personal igual que uno publicado de otra persona está permitido.

**Despublicar** (el propietario pasa a personal un alimento publicado) tiene, **para los demás, exactamente la misma semántica que archivar** (§11.2.2):
- sale de su búsqueda y sus listados;
- quien lo tiene en favoritos o en una receta suya lo sigue viendo y usando tal cual;
- se puede quitar de favoritos, pero no añadirlo.

A diferencia de archivar, **se puede volver a publicar**, con la misma comprobación de `409`, y el propietario lo sigue viendo y editando con normalidad. Los datos del alimento siguen siendo visibles dentro de las recetas publicadas que lo contienen.

**Publicar una receta** (decisión 2026-11-05; sustituye al popup que publicaba los ingredientes, de la decisión 2026-09-24).
- Hasta la fase 2 la interfaz no publica ni despublica recetas: ninguna ruta escribe `recipe.is_published`. La columna y las recetas ya publicadas se conservan, y se siguen viendo, usando y copiando.
- En la fase 2, un ingrediente personal seguirá sin publicar y solo será visible dentro de esa receta, con un aviso antes de publicar. Así no llena la búsqueda pública. Queda por decidir qué ocurre con él al copiar la receta (`audit/deuda_pendiente.md`).
- Quien ve una receta publicada ve sus ingredientes.

### 11.5 Unicidad y soft-delete

Toda restricción `UNIQUE` sobre una entidad archivable debe implementarse como índice único parcial:

```sql
CREATE UNIQUE INDEX uq_entity_active_name
ON entity (normalized_name)
WHERE deleted_at IS NULL;
```

Así, una fila archivada no bloquea la creación de una fila activa equivalente. Esta regla se aplica a unicidad simple, compuesta y normalizada por expresiones.

La condición de unicidad debe coincidir con la normalización de Python. Una comprobación previa puede mejorar el mensaje, pero nunca sustituye la constraint ni `ON CONFLICT`.

### 11.6 Constraints de integridad

Las reglas importantes deben reforzarse en PostgreSQL:

- rangos numéricos;
- valores cerrados;
- cantidades positivas;
- relaciones obligatorias;
- exactamente una alternativa no nula;
- coherencia entre columnas;
- unicidad;
- estados válidos.

Los constraints nuevos tienen nombres explícitos y siguen estos patrones:

- `ck_<tabla>_<regla>`;
- `uq_<tabla>_<columnas>`;
- `fk_<tabla>_<columna>_<tabla_referenciada>`;
- `trg_<tabla>_<evento>`.

Ejemplo correcto:

```text
fk_recipe_users_id_users
```

Un constraint debe coincidir con la validación Python.

### 11.7 Índices

Los índices se crean para consultas y relaciones reales:

- las FKs utilizadas en joins frecuentes deben revisarse para indexación;
- los filtros por propietario deben tener índices adecuados;
- los listados activos pueden usar índices parciales;
- los índices de expresión deben coincidir con la normalización de duplicados;
- no se crean índices duplicados sin justificarlo;
- después de una migración se revisan las queries críticas.

Los índices deben seguir `idx_<tabla>_<columnas>` o `uq_<tabla>_<columnas>` y documentar qué consulta soportan cuando no sea evidente.

**Búsqueda difusa** (`_build_fuzzy_search`, decisión 2026-10-09). En PostgreSQL, un `OR` solo usa índices si todas sus ramas pueden usarlos, así que cada rama se escribe sobre una expresión indexada:
- subcadena: `lower(col) ILIKE '%texto%'`;
- similitud trigram: `lower(col) % 'texto'`. No se usa `similarity(...) >= x`, porque no puede usar índice. El umbral es `TRGM_SIMILARITY_THRESHOLD`, que el helper fija en la sesión (`pg_trgm.similarity_threshold`);
- forma colapsada, con las letras repetidas reducidas a una ("coffee" → "cofe"): `fuzzy_compact_sql(col) ILIKE '%texto%'`.

Cada columna buscada tiene dos índices GIN trigram: `idx_<tabla>_<columna>_trgm` sobre `lower(col)` e `idx_<tabla>_<columna>_compact_trgm` sobre `fuzzy_compact_sql(col)`. La expresión del índice y la de la consulta salen de la misma función. La columna se pasa sin envolver: un `COALESCE` o cualquier otra función rompe la coincidencia con el índice. Si la búsqueda se hace sobre una tabla relacionada, sus ids se resuelven aparte, con `= ANY(ARRAY(SELECT ...))` y no con `IN (...)`, porque solo así el `OR` puede combinarse con los demás índices (marca de `catalog`).

**Texto sin acentos** (2026-11-05). `catalog` se busca por `search_name`, una columna generada con el nombre en minúsculas y sin acentos, y el término se normaliza igual, así que "limon" encuentra "Limón". El mapa de caracteres vive en `domain/search_text.py`, que da tanto la expresión SQL de la columna como la normalización del término. No es el antiguo `catalog.slug`, eliminado el 2026-09-25: aquel era un dato aplicado a mano y sin uso, y este lo calcula PostgreSQL y lo usa la búsqueda. `recipe` hace lo mismo desde el 2026-11-05. `tags` y el buscador del pop-up de rescate también ignoran mayúsculas y acentos desde el 2026-11-08, con la expresión de `search_text_sql` sobre la columna, sin columna generada, y tratan `%` y `_` como caracteres (`_escape_like`). Las demás tablas siguen buscando por su columna original.

**Búsqueda de recetas** (2026-11-05). Por `recipe.search_name`, igual que `catalog`, o por el nombre de un ingrediente, con `= ANY(ARRAY(SELECT ...))`: `catalog.search_name` y `manual_intake.name`. Solo filtra recetas que el usuario ya puede ver, así que no revela nada nuevo. Una receta encontrada por un ingrediente queda detrás en la relevancia, que mira solo el nombre. Se puede filtrar por uno o varios tipos de comida, separados por comas en `meal_type`, cada uno validado con `parse_enum`. Una receta aparece si alguno coincide con su tipo principal o con los adicionales. Las favoritas van primero y no hay orden por uso, porque lo consumido no referencia la receta.

**Excepción: `off_product` y `ciqual_food`** (2026-11-05). Las dos tablas comparten `_search_reference_foods` (`queries/crud.py`), con los mismos criterios, y no usan `_build_fuzzy_search`, porque compara el término entero y "hacendado gazpacho" devolvía cualquier producto de Hacendado. Cada palabra debe aparecer en `search_text`, sin acentos: nombre y marca en `off_product`, y nombre en español e inglés en `ciqual_food`. Se ordena primero por los que empiezan por la primera palabra, después por los que tienen una palabra que empieza por ella y, por último, por el desempate de cada tabla: escaneos, nombre y código en `off_product`; crudos, nombre más corto y código en `ciqual_food`, que no tiene escaneos. Solo si ninguna fila de la tabla contiene todas las palabras, aunque ya se le ofrezcan al usuario por otra vía, se busca por similitud, para tolerar erratas, con el mismo desempate. Así todas las páginas de una búsqueda siguen el mismo modo y no salen parecidos de algo que el usuario ya tiene. Cada tabla tiene un único índice GIN trigram sobre `search_text`: `idx_<tabla>_search_text_trgm`.

### 11.8 Claves foráneas

Toda FK documenta su relación y su política de borrado:

- `RESTRICT`: impide borrar datos con dependencias relevantes;
- `CASCADE`: elimina dependencias sin significado independiente;
- `SET NULL`: conserva el registro y elimina una referencia opcional;
- `NO ACTION`: solo se usa con comportamiento diferido deliberadamente elegido.

La política se decide por ciclo de vida, no por comodidad. Para datos históricos o clínicos se prioriza conservar información mediante `RESTRICT` o `SET NULL`; `CASCADE` requiere justificar qué histórico destruye.

### 11.9 SQL seguro e integridad declarativa

- Todo valor dinámico viaja como parámetro; nunca se interpola con f-strings ni concatenación.
- Los nombres dinámicos de tabla o columna usan `psycopg.sql.Identifier` junto con una whitelist central definida en la sección 4.6.
- Los updates dinámicos usan `_build_update_query()` o el helper central que lo sustituya.
- Las queries de lectura con filtros opcionales reutilizan helpers comunes.
- Los listados tienen orden estable, incluyendo el ID como desempate.
- Los límites y offsets se normalizan en un helper común.

Las constraints e índices son parte del contrato de persistencia y deben existir en la base de datos junto con las comprobaciones correspondientes en Python. La clasificación de whitelists internas como enumeraciones técnicas se define en la sección 4.6.

### 11.10 Auditoría de cambios

La auditoría de cambios conserva la historia de modificaciones de datos; no es el logging técnico de la aplicación.

Las tablas o campos que requieran trazabilidad deben especificar:

- entidad y operación;
- actor;
- timestamp UTC;
- motivo si aplica;
- valores anterior y nuevo si se necesita reconstrucción;
- política de retención.

Para datos clínicos, históricos o que alimenten modelos, se debe distinguir entre valor original, valor corregido e información calculada. La auditoría debe incluir `request_id` cuando exista, siguiendo `error_conventions.md`.

La auditoría puede implementarse mediante tabla histórica, trigger o servicio centralizado. La estrategia elegida debe ser única por caso y debe documentar si cubre escrituras realizadas fuera de la aplicación.

### 11.11 Borrado físico

El borrado físico solo se permite cuando la entidad está declarada como no archivable y no destruye información histórica necesaria.

Antes de utilizar `DELETE` se revisan FKs, cascadas, favoritos, etiquetas, porciones, snapshots y auditoría. No se utiliza el borrado físico para resolver conflictos de unicidad ni para ocultar un error de ownership.

## 12. Migraciones y evolución del esquema

El esquema debe evolucionar de forma explícita, idempotente y verificable. Un cambio de esquema incluye también los datos, queries, dataclasses, mappers y endpoints que dependan de él.

### 12.1 Fuentes y responsabilidades

- `schema.py` representa la definición declarativa esperada para instalaciones nuevas.
- `db_init.py` puede mantener bootstrap y migraciones pragmáticas durante el TFG.
- Cada migración debe tener una finalidad identificable y no mezclar cambios funcionales no relacionados.
- Un cambio aplicado manualmente a PostgreSQL debe reflejarse en `schema.py` y en el bootstrap/migración.
- La base de datos real debe poder compararse con la definición esperada.
- La migración no se considera completa hasta que el código que la consume también esté actualizado.

Mientras no exista un sistema de migraciones versionadas independiente, las funciones de `db_init.py` deben seguir el patrón `_ensure_<feature>_schema` y ser idempotentes. Si el proyecto requiere despliegues con historial formal, se introducirá una tabla de versiones o herramienta de migraciones como decisión separada.

### 12.2 Idempotencia

Una migración idempotente puede ejecutarse más de una vez sin duplicar objetos, perder datos ni producir un estado diferente.

- Usar `IF NOT EXISTS` o comprobaciones equivalentes cuando sea seguro.
- Comprobar la definición existente antes de modificarla.
- No asumir que la ausencia de una tabla implica que no existen datos relacionados.
- No crear índices duplicados con nombres alternativos para ocultar una migración incompleta.
- No tratar un error de “ya existe” como éxito si la definición puede ser incorrecta.
- Si una migración detecta una definición incompatible, debe fallar y exigir una decisión explícita.

### 12.3 Procedimiento obligatorio

Antes de ejecutar un cambio de esquema:

1. Definir la decisión de modelo, ciclo de vida y compatibilidad.
2. Identificar tablas, columnas, FKs, índices, constraints y triggers afectados.
3. Identificar queries, mappers, dataclasses, endpoints y componentes afectados.
4. Definir cómo se conservan, convierten o eliminan los datos existentes.
5. Definir el comportamiento para `NULL`, valores antiguos e índices únicos.
6. Preparar una migración idempotente.
7. Actualizar `schema.py` y el bootstrap/mecanismo de migración.
8. Actualizar código dependiente.
9. Verificar esquema, constraints, índices y muestras de datos antes y después.
10. Verificar que la aplicación puede arrancar y ejecutar las operaciones afectadas.

### 12.4 Datos y migraciones destructivas

- Una migración destructiva requiere decisión explícita y estrategia de recuperación.
- No eliminar una columna antes de migrar sus consumidores.
- No borrar filas para hacer que una constraint nueva “entre” sin documentar qué se pierde.
- Las conversiones de tipo deben definir la expresión `USING`, precisión, redondeo y tratamiento de valores inválidos.
- Los cambios `REAL` a `NUMERIC` y `TIMESTAMP` a `TIMESTAMPTZ` siguen además la sección 10.5.
- Los datos clínicos, históricos o importados deben conservar su trazabilidad cuando el cambio lo requiera.

### 12.5 Fallos y transacciones de migración

- Las migraciones se ejecutan dentro de la transacción que corresponda al bootstrap.
- Un savepoint solo puede tolerar un fallo si se demuestra que continuar es seguro.
- Una migración obligatoria fallida aborta el arranque o deja el sistema marcado como no actualizado.
- No imprimir un warning y continuar como si el esquema fuese correcto.
- El resultado final debe ser inequívoco: aplicada, omitida de forma segura y documentada, o abortada.
- Las operaciones que PostgreSQL no permita ejecutar de forma transaccional deben documentar su estrategia específica.

### 12.6 Identidad de conexión para bootstrap y migraciones

El bootstrap de esquema (`db_init.py`) ejecuta sentencias DDL: `CREATE TABLE`, `ALTER TABLE`, `ADD CONSTRAINT`, `CREATE INDEX`. Estas operaciones requieren privilegios de propietario sobre el objeto, distintos y más amplios que los privilegios DML (`SELECT`/`INSERT`/`UPDATE`/`DELETE`) que necesita el runtime de la aplicación.

Por eso el bootstrap y el runtime de la aplicación no comparten identidad de conexión:

- `init_db()` se conecta con una identidad de migraciones, propietaria de los objetos de esquema (`MIGRATIONS_DATABASE_URL` o el nombre equivalente que defina `config.py`). Esta identidad no se usa desde `routes/`, `services/` ni `database/queries/`.
- El resto de la aplicación —rutas, servicios, CRUD— se conecta con `DATABASE_URL`, una identidad de mínimo privilegio sin permisos de DDL. Esta identidad nunca debe poder modificar esquema ni constraints, ni siquiera durante el arranque.
- `get_connection()` (o el helper equivalente) no decide qué identidad usar según el contexto de llamada; el bootstrap usa explícitamente su propio helper de conexión de migraciones, distinto del que usan rutas, servicios y CRUD.
- Ambas variables se validan al arrancar según la sección 8.1. Si la identidad de migraciones falta y el bootstrap está activado, el arranque falla con severidad `CRITICAL`, no se omite en silencio.
- Conceder a la identidad de runtime privilegios de propietario o equivalentes a DDL, aunque sea temporalmente, deshace la separación de privilegios y no se considera una solución válida a un fallo de bootstrap.

Un fallo del bootstrap por permisos (`must be owner of table ...`) es una señal de que se ha usado la identidad equivocada, no un problema de la tabla afectada. No se corrige ampliando los privilegios del runtime; se corrige asegurando que `init_db()` use la identidad de migraciones.

Antes de dar por cerrada una tabla en el ciclo de auditoría (sección 13), debe verificarse contra la base de datos real —no solo contra `schema.py`— que el bootstrap se ejecutó efectivamente con la identidad correcta y que el esquema físico coincide con la definición esperada. Un cambio de esquema fusionado en el código y documentado como decisión no se considera aplicado hasta que esa verificación directa contra PostgreSQL lo confirme.

### 12.7 Datos preexistentes ante una regla nueva

Una migración que añade una columna, un `CHECK` o un contrato nuevo (p. ej. "si `insulin_dose` es `TRUE` debe existir una inyección asociada") no puede asumir que las filas ya existentes lo cumplen. Antes de cerrar una tabla se debe comprobar contra la base real cuántas filas violan la regla nueva.

- El criterio por defecto es **no tocar los datos existentes**: se añaden las columnas nuevas con el backfill técnico estrictamente necesario para que la migración sea válida (p. ej. rellenar `created_at` desde una columna de evento ya existente), pero no se corrigen, marcan ni completan datos para que cumplan una regla de negocio nueva que no existía cuando se escribieron.
- Backfillear, marcar como inconsistente o borrar datos preexistentes que incumplen la regla nueva es una decisión de producto explícita, no una consecuencia automática de la migración. Se documenta en `conventions/decisions.md` solo si el usuario decide desviarse del criterio por defecto.
- Cualquier análisis, estadística o modelo que lea esa tabla debe considerar que puede haber filas anteriores a la regla nueva que no la cumplen.
- Esto no exime de aplicar la regla a los datos nuevos desde el momento en que la migración se cierra.

Aplicado sin excepción (criterio por defecto, sin entrada en `decisions.md`) en `intake_event` (hallazgo 17 de `audit/audit_intake_event.md`: 40 filas `consumed` con `insulin_dose = TRUE` sin inyección asociada, 48 de 51 sin métricas de confianza) e `insulin_injections` (9 de 9 filas con `intake_event_id IS NULL`), ambos verificados contra la base real el 2026-09-09.

## 13. Procedimiento obligatorio de auditoría por tabla

Para cada tabla se revisará siempre en este orden:

1. Nombre de tabla, columnas de usuario, timestamps y soft-delete.
2. Dataclasses de lectura y payloads de escritura.
3. Enums y constantes de dominio usados por la tabla.
4. Constraints, índices, unicidad parcial y políticas de FK.
5. Funciones `create`, `get`, `list`, `update`, `archive/delete` y sus contratos.
6. Filtros de propietario, visibilidad y registros archivados dentro de SQL.
7. Uso de parámetros SQL, composición dinámica y mappers.
8. Control de conexiones y transacciones simples y compuestas.
9. Endpoints consumidores, autenticación, códigos HTTP y respuestas HTMX.
10. Formularios, validación cliente/servidor y mensajes de usuario.
11. Concurrencia, idempotencia y conflictos de unicidad.
12. Ciclo de vida declarado: archivable, no archivable, histórico o dependiente.
13. Política `ON DELETE`, impacto sobre históricos y posibilidad de borrado físico.
14. Auditoría requerida, actor, timestamps, valores originales y `request_id`.
15. Coincidencia entre `schema.py`, migraciones/bootstrap y esquema real.

Cada hallazgo se clasifica como una de estas categorías:

- inconsistencia de convención;
- bug funcional o de seguridad;
- decisión pendiente de producto o modelo;
- deuda técnica que puede aplicarse solo a código nuevo.

No se refactoriza una tabla hasta decidir la convención aplicable y el alcance de migración. Las correcciones deben mantener una única fuente de verdad y actualizar código, esquema y documentación cuando corresponda.

Si una tabla revela la necesidad de un patrón que todavía no existe en ningún punto del proyecto (por ejemplo enums centrales, capa `services/`, versionado optimista o adapters de servicios externos), el hallazgo se clasifica como "decisión pendiente de producto o modelo" o "deuda técnica" y se documenta, pero esa infraestructura nueva no se construye dentro de la auditoría de esa tabla salvo que el usuario lo pida explícitamente para ese caso. El objetivo de cada auditoría es dejar la tabla coherente y correcta, no adelantar arquitectura que ninguna otra tabla necesita todavía.
