# Convenciones de Desarrollo - DayBetes

Este documento define la forma obligatoria de construir código nuevo y refactorizar código existente en DayBetes. Su objetivo es mantener una arquitectura coherente, evitar errores de seguridad y concurrencia, y hacer que funciones equivalentes tengan contratos equivalentes.

Durante una auditoría de tabla, módulo o Pull Request, este documento es el criterio de decisión. Si una decisión concreta de producto o modelo no está cubierta aquí, debe documentarse antes de implementar el código y añadirse a este documento si puede repetirse.

Las convenciones se aplican inmediatamente al código nuevo. El código existente se adapta progresivamente por tabla o módulo, sin mezclar en una misma corrección cambios funcionales no relacionados.

Durante la fase de desarrollo personal (TFG, un único desarrollador, un único usuario) no se exige una suite de tests automatizados. La verificación manual del comportamiento afectado es suficiente antes de dar por cerrada una tabla o módulo. Esta decisión se revisará cuando el proyecto salga de esta fase; no debe señalarse como convención faltante en auditorías mientras siga vigente.

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

- `commit=True`: el CRUD es propietario de una operación simple y debe confirmar su operación cuando termina correctamente. Si falla, puede revertir su propia operación y propagar o traducir el error según su contrato.
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
except Exception:
    return error_response()
```

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

Los helpers genéricos deben distinguir los dos modos:

- En modo propietario (`commit=True`), pueden hacer rollback y devolver el resultado de error definido por el contrato.
- En modo caller-owned (`commit=False`), deben propagar la excepción SQL y no hacer rollback.

Un error de infraestructura nunca se convierte silenciosamente en un resultado exitoso.

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
    is_private: bool | None = None
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

- `create_*` devuelve el identificador u objeto creado. Un fallo de infraestructura lanza excepción.
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

## 4. Constantes de dominio

### 4.1 Fuente única de verdad

Un valor se modela como enumeración cuando pertenece a un conjunto cerrado y conocido de opciones. Ejemplos: tipos de comida, zonas de inyección, tipos de insulina, estados de eventos, Nutriscore y modos internos de navegación. Los estados físicos del alimento, los métodos de cocción y los métodos de conservación son actualmente ampliables y se tratan como catálogos, no como enums.

Los enums de dominio se declaran en un módulo central, por ejemplo `DayBetes_food/domain/constants.py`. Ese módulo no debe importar rutas, componentes ni la base de datos.

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

Debe almacenarse en una tabla de catálogo con, como mínimo:

- identificador;
- código estable;
- etiqueta visible;
- indicador `is_active`;
- timestamps cuando proceda.

Los valores iniciales pueden cargarse mediante bootstrap o migración, pero añadir uno nuevo debe ser un cambio de datos, no un cambio obligatorio de código.

En esta categoría entran actualmente subtipos de comida, marcas de comida, origen de comida manual, estados físicos inicial/final, métodos de cocción y métodos de conservación. Las listas Python existentes solo pueden actuar como datos iniciales mientras se completa el catálogo.

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

- Todas las peticiones con método inseguro (`POST`, `PUT`, `PATCH`, `DELETE`) requieren el token CSRF definido por el middleware.
- Las excepciones CSRF deben estar en una allowlist central y explícita. Solo pueden incluir endpoints de autenticación que no tengan todavía una sesión válida o que deban funcionar para cerrar una sesión inválida.
- Añadir una nueva excepción requiere justificarla y documentarla; no se desactiva CSRF dentro de una ruta individual.
- El rate limiting es obligatorio para login, registro, recuperación de credenciales y cualquier endpoint externo costoso o susceptible de abuso.
- La clave de rate limiting debe combinar el identificador de operación con una identidad suficientemente estable, normalmente IP normalizada e identificador normalizado cuando exista.
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
UPDATE intake_event
SET state = %(state)s,
    version = version + 1
WHERE id = %(event_id)s
  AND users_id = %(user_id)s
  AND version = %(expected_version)s
RETURNING id, version;
```

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

### 7.8 Identificadores, fechas y horas

- Los identificadores de URL, formularios y HTMX se validan antes de ejecutar SQL.
- Un ID mal formado produce `400` o `422`; un ID válido sin recurso visible produce `404`.
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

La configuración de desarrollo, test y producción no se mezcla. La inicialización automática del esquema no debe activarse accidentalmente en producción.

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

No se utiliza `GET` para modificar datos. Las rutas usan nombres de recursos claros, parámetros específicos como `event_id` o `recipe_id` y no reciben `user_id` como fuente de autorización.

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

### 9.6 Entrada, estados de carga y repetición

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

### 11.3 Soft-delete

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

### 11.4 Lecturas y escrituras con visibilidad

Una query debe declarar su intención de visibilidad: solo activos, solo archivados, todos o visibles para un usuario.

Para una entidad cuyo propietario físico sea `owner_column`, una lectura de recursos públicos y propios sigue este patrón:

```sql
WHERE entity.id = %(entity_id)s
  AND entity.deleted_at IS NULL
  AND (
      entity.owner_column = %(user_id)s
      OR entity.is_private = FALSE
  )
```

`owner_column` representa la columna propietaria real de la tabla; no se escribe literalmente si no existe. Para una escritura, la visibilidad pública nunca concede permiso:

```sql
WHERE entity.id = %(entity_id)s
  AND entity.owner_column = %(user_id)s
```

El owner column real debe aplicarse dentro de SQL y estar documentado por tabla. La lógica detallada de ownership y agregados sigue la sección 5 y la sección 6.9.

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
fk_recipe_user_id_users
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
