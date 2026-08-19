# Convenciones de Desarrollo - DayBetes

Este documento define la forma obligatoria de construir código nuevo y refactorizar código existente en DayBetes. Su objetivo es mantener una arquitectura coherente, evitar errores de seguridad y concurrencia, y hacer que funciones equivalentes tengan contratos equivalentes.

Durante una auditoría de tabla, módulo o Pull Request, este documento es el criterio de decisión. Si una decisión concreta de producto o modelo no está cubierta aquí, debe documentarse antes de implementar el código y añadirse a este documento si puede repetirse.

Las convenciones se aplican inmediatamente al código nuevo. El código existente se adapta progresivamente por tabla o módulo, sin mezclar en una misma corrección cambios funcionales no relacionados.

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

### 1.2 Servicios

Las funciones de `services/` contienen casos de uso reutilizables que combinan varias operaciones o reglas de negocio.

Un servicio:

- recibe datos ya parseados y validados;
- puede coordinar varias queries;
- es dueño de la transacción si coordina una operación compuesta fuera de una ruta;
- no devuelve `HTMLResponse`, `JSONResponse` ni fragmentos HTMX;
- no debe depender de headers, cookies o detalles de la petición HTTP.

Un endpoint puede llamar directamente a `database/queries/` cuando la operación es una única lectura o escritura sin reglas de negocio adicionales. Se introduce un servicio cuando hay coordinación de varias operaciones, una transacción compuesta, una regla de negocio no trivial o una operación que deba reutilizarse desde más de un endpoint.

Si un servicio recibe una conexión, la usa como parte de la unidad de trabajo existente. No abre otra conexión salvo que su contrato documente explícitamente que es el coordinador raíz.

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

## 2. Ciclo de vida de conexiones y transacciones

### 2.1 Dueño de la conexión

Una petición HTTP utiliza una única conexión por unidad de trabajo. El endpoint o servicio coordinador raíz es el único dueño de esa conexión y es responsable de cerrarla.

Reglas:

- Abrir la conexión en el boundary de la unidad de trabajo.
- Pasar la misma conexión a los servicios, queries y componentes que la necesiten para leer datos.
- No abrir varias conexiones para completar una misma operación lógica.
- No abrir conexiones dentro de componentes, mappers o helpers de presentación.
- No mantener conexiones en variables globales ni en `ContextVar`.
- Un componente no puede ocultar una lectura de base de datos durante el renderizado.

### 2.2 Operaciones simples

Toda función CRUD de escritura acepta `commit: bool = True`.

- `commit=True`: el CRUD puede confirmar su operación cuando termina correctamente.
- `commit=False`: el CRUD participa en una transacción propiedad del llamador y no confirma ni revierte la transacción.
- Las funciones de solo lectura siempre llaman a los helpers de query con `commit=False`.
- El valor de `commit` se propaga hasta el helper que ejecuta el cursor.

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

### 2.5 Errores dentro de una transacción propia

Los helpers genéricos deben distinguir los dos modos:

- En modo propietario (`commit=True`), pueden hacer rollback y devolver el resultado de error definido por el contrato.
- En modo caller-owned (`commit=False`), deben propagar la excepción SQL y no hacer rollback.

Un error de infraestructura nunca se convierte silenciosamente en un resultado exitoso.

## 3. Tipado de datos, firmas y nomenclatura

### 3.1 Dataclasses

Se abandona el uso de diccionarios planos como contrato entre capas.

- Toda conversión de una fila SQL a un objeto de dominio debe usar una dataclass de lectura.
- Todo payload que viaje de una ruta a un servicio o CRUD debe usar una dataclass de comando/update.
- Las dataclasses centralizan conversión de `REAL`, `Decimal`, `NULL`, fechas y booleanos.
- Los campos opcionales deben declararse como opcionales; no representar opcionalidad mediante claves ausentes ambiguas.
- Los datos HTTP se convierten a dataclass después de validar la entrada y antes de llamar al servicio/CRUD.
- Las respuestas JSON pueden serializar dataclasses mediante un mapper explícito; no se devuelve directamente una fila de psycopg.

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

- `create_<entity>`: crea una fila y devuelve su ID u objeto creado.
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

### 3.5 Parámetros

- Usar `user_id` en Python, aunque la columna heredada se llame `users_id`.
- Usar nombres explícitos: `catalog_id`, `manual_intake_id`, `recipe_id`, `intake_event_id`.
- No usar un parámetro genérico `id` cuando el concepto pueda confundirse.
- Mantener el orden: `connection`, contexto de usuario, identificador de entidad, payload, opciones como `commit`, `limit` y `offset`.
- Los updates de entidad reciben un payload dataclass. Las operaciones especializadas pueden tener argumentos explícitos si ejecutan una acción distinta, no si son otro update equivalente.
- No usar `**kwargs` para campos de tablas; los campos aceptados deben estar tipados y validados.

## 4. Constantes de dominio

### 4.1 Fuente única de verdad

Valores cerrados como tipos de comida, zonas de inyección, tipos de insulina, estados de eventos, estados físicos y opciones de índice glucémico deben definirse mediante `enum.Enum` en un módulo central, por ejemplo `domain/constants.py`.

Reglas:

- Los endpoints y componentes no escriben literales sueltos como `"rapid"`, `"basal"`, `"planned"` o `"consumed"`.
- Las validaciones consumen los enums centrales.
- Los servicios y queries reciben enums o valores ya normalizados.
- Al persistir se usa explícitamente `.value`.
- El esquema SQL y sus constraints deben reflejar los valores del enum.
- Cambiar un valor requiere actualizar el enum, el esquema/migración, las validaciones, los componentes y los tests.

### 4.2 Constantes de configuración

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

### 6.1 Unicidad

La base de datos es la autoridad definitiva sobre unicidad.

- No usar el patrón “comprobar si existe en Python y después insertar” como garantía de unicidad.
- Las comprobaciones previas solo pueden mejorar el mensaje de usuario; nunca sustituyen una constraint.
- Todo conflicto de constraint se traduce a `ConflictError` y posteriormente a HTTP `409`.

### 6.2 `ON CONFLICT`

Las operaciones repetibles o susceptibles de peticiones duplicadas usan SQL nativo:

- `ON CONFLICT DO NOTHING` cuando repetir debe ser un no-op.
- `ON CONFLICT DO UPDATE` cuando repetir debe actualizar el mismo recurso.
- La operación debe documentar si devuelve el estado anterior o posterior.

Las operaciones toggle deben evitarse para acciones que puedan reintentarse. Preferir `set_favorite(value)` frente a `toggle_favorite()` cuando el cliente pueda repetir la petición.

### 6.3 Operaciones compuestas

Las operaciones que modifican varias tablas usan una única transacción. Si necesitan garantizar exclusión o evitar lecturas obsoletas, deben documentar el nivel de aislamiento o el bloqueo utilizado.

### 6.4 Actualizaciones concurrentes del mismo recurso

`ON CONFLICT` resuelve colisiones de creación, pero no evita que dos clientes sobrescriban silenciosamente el mismo recurso.

- Las entidades con transiciones críticas o snapshots clínicos deben usar control de concurrencia optimista.
- Se preferirá una columna `version INTEGER NOT NULL DEFAULT 1` que se incremente en cada update.
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
- Para datos no críticos puede aceptarse “última escritura gana”, pero debe quedar documentado por entidad; no es el comportamiento implícito por defecto.
- No usar `updated_at` como versión si su precisión o zona horaria no garantizan detectar dos escrituras cercanas. Si se usa temporalmente, debe documentarse como deuda de migración.

## 7. Validación y normalización de entrada

El servidor es la autoridad final. HTML y JavaScript solo mejoran la experiencia.

- Validar en helpers reutilizables, no mediante lógica ad-hoc por endpoint.
- Normalizar espacios antes de comprobar campos obligatorios.
- Las cadenas opcionales vacías se convierten uniformemente en `None`.
- Los números se parsean con un helper común que valida formato, finitud, rango y signo.
- Los booleanos solo aceptan valores explícitos. Un valor desconocido produce `422`.
- Las opciones cerradas se validan contra enums/constants centrales.
- Los identificadores se validan antes de ejecutar SQL.
- La misma regla de negocio debe existir en servidor y, cuando sea útil, reflejarse en el formulario.

### 7.1 Campos parciales y limpieza explícita

Se distinguen tres estados:

- campo ausente: no modificar el valor existente;
- campo presente vacío: normalizar según el tipo, normalmente `None`;
- sentinel `CLEAR`: borrar explícitamente un valor nullable.

El sentinel se define en un módulo común. No se crean variantes como `"__clear__"`, `"clear"` o cadenas equivalentes por formulario.

## 8. Configuración, logging y servicios externos

### 8.1 Configuración

- Las variables obligatorias, como credenciales de base de datos y secretos, se validan al arrancar.
- Si faltan o son inválidas, la aplicación no arranca.
- Las variables opcionales tienen defaults documentados.
- Una variable presente pero inválida no se sustituye silenciosamente por el default; produce error de configuración.
- La configuración de desarrollo, test y producción debe ser explícita.
- Las opciones de inicialización automática de base de datos no deben quedar habilitadas accidentalmente en producción.

### 8.2 Logging

- Usar el módulo `logging`, nunca `print()` para eventos operativos o errores.
- Usar niveles `DEBUG`, `INFO`, `WARNING`, `ERROR` y `CRITICAL` según la gravedad.
- Incluir contexto útil: operación, entidad, identificador técnico y usuario cuando sea seguro.
- Nunca registrar contraseñas, tokens, cookies, hashes, secretos ni datos médicos detallados.
- Una excepción inesperada debe registrarse con traceback en el boundary adecuado, no repetirse en todas las capas.

### 8.3 Servicios externos

Toda llamada HTTP externa debe:

- tener timeout explícito y configurable;
- validar el status HTTP antes de interpretar el cuerpo;
- validar la estructura JSON recibida;
- capturar errores de red, timeout y parseo;
- definir si admite reintentos, con límite y backoff;
- registrar el fallo internamente sin datos sensibles;
- devolver al usuario un mensaje genérico y estable.

## 9. Endpoints, HTTP y HTMX

### 9.1 Códigos HTTP

- `200`: operación o lectura correcta.
- `201`: creación correcta cuando la respuesta sea una API HTTP convencional.
- `303`: redirección posterior a un `POST` tradicional.
- `400`: petición malformada que no puede interpretarse.
- `401`: usuario no autenticado.
- `403`: autenticado pero sin permiso, salvo recursos cuya existencia deba ocultarse.
- `404`: recurso inexistente, archivado no visible o ajeno cuando no se deba revelar.
- `409`: conflicto de unicidad, estado o concurrencia.
- `429`: petición rechazada por rate limiting.
- `422`: entrada bien formada pero inválida según las reglas de negocio.
- `500`: fallo inesperado de infraestructura.

No devolver `200` con un mensaje de error salvo una decisión HTMX documentada para un fragmento visual que necesite reemplazarse con una respuesta no exitosa. Esa decisión debe aplicarse igual a todas las acciones equivalentes.

### 9.2 Estructura de errores

Los errores HTML devuelven siempre el componente común de error. No mezclar texto plano, HTML arbitrario y cuerpos vacíos para el mismo tipo de acción.

Los endpoints JSON usan esta estructura:

```json
{
  "error": {
    "code": "validation_error",
    "message": "...",
    "fields": {}
  }
}
```

Los códigos internos (`validation_error`, `not_found`, `conflict`, `infrastructure_error`) son estables. El texto visible puede localizarse o mejorar sin cambiar el código.

### 9.3 HTMX

- Una acción equivalente usa el mismo `hx_target`, `hx_swap`, eventos y estados de éxito/error.
- Los errores de validación tienen un target visible y estable.
- El refresco posterior ocurre solo si `event.detail.successful` es verdadero.
- Una navegación posterior a una petición HTMX usa `HX-Redirect` de forma uniforme.
- `HX-Trigger` se reserva para eventos documentados y usa nombres estables.
- No mezclar `HX-Redirect`, `HX-Location` y fragmentos intercambiados para el mismo flujo sin una razón documentada.
- Los botones de envío se deshabilitan o muestran estado de carga para evitar dobles peticiones.

## 10. Tipos de datos, fechas y números

### 10.1 Fechas

- La aplicación usa una única representación temporal.
- Los timestamps se almacenan en UTC.
- Las columnas temporales se llaman `created_at`, `updated_at`, `deleted_at`, `expires_at` o el nombre de dominio equivalente definido en el esquema.
- La conversión entre UTC y zona local ocurre en los boundaries de presentación o entrada, no en cada componente de forma arbitraria.
- No mezclar `NOW()`, `datetime.utcnow()` y timestamps locales sin una política explícita.

### 10.2 Números nutricionales

- Los campos nutricionales existentes que usan `REAL` mantienen ese tipo durante las correcciones actuales.
- Todo campo nuevo que participe en cálculos de dosis de insulina, snapshots clínicos o decisiones terapéuticas usa `NUMERIC` con una escala explícita desde su creación, y se representa como `Decimal` en Python.
- El resto de campos nutricionales nuevos puede seguir temporalmente `REAL` mientras no participe en esos cálculos y hasta aprobar una migración global a `NUMERIC(6,2)` u otra precisión.
- Los campos existentes `REAL` que participen en cálculos clínicos deben migrarse prioritariamente a `NUMERIC`; esa migración puede ejecutarse separada de la corrección funcional, pero no debe tratarse como una deuda indefinida.
- No mezclar una migración de precisión numérica con una corrección de comportamiento en el mismo cambio salvo que la corrección dependa directamente de la precisión.
- La migración a `NUMERIC` queda documentada como deuda técnica independiente.

## 11. Base de datos, soft-delete y auditoría

### 11.1 Timestamps y soft-delete

- Las entidades archivables tienen `deleted_at` nullable.
- Las lecturas normales excluyen archivados mediante `deleted_at IS NULL`.
- Las operaciones de archivado se llaman `archive_<entity>` y las de restauración `restore_<entity>`.
- Las entidades no archivables usan `delete_<entity>` y documentan por qué el borrado físico es correcto.
- `updated_at` se actualiza automáticamente mediante trigger o mediante un helper central obligatorio.

### 11.2 Unicidad y soft-delete

Toda restricción `UNIQUE` sobre una entidad archivable debe implementarse como índice único parcial:

```sql
CREATE UNIQUE INDEX uq_entity_active_name
ON entity (normalized_name)
WHERE deleted_at IS NULL;
```

Así, una fila archivada no bloquea la creación de una fila activa equivalente. Esta regla se aplica a unicidad simple, compuesta y normalizada por expresiones.

### 11.3 SQL seguro

- Todo valor dinámico viaja como parámetro.
- Está prohibido interpolar valores de usuario con f-strings.
- Los nombres dinámicos de tablas o columnas usan `psycopg.sql.Identifier` y una whitelist explícita.
- Los updates dinámicos usan `_build_update_query()` o el helper central que lo sustituya.
- Las queries de lectura con filtros opcionales reutilizan helpers comunes.
- Los listados tienen orden estable, incluyendo el ID como desempate.
- Los límites y offsets se normalizan en un helper común.

### 11.4 Constraints, índices y FKs

- Índices: `idx_<tabla>_<columnas>`.
- Índices únicos: `uq_<tabla>_<columnas>`.
- Checks: `ck_<tabla>_<regla>`.
- Foreign keys: `fk_<tabla>_<columna>_<tabla_referenciada>`.
- Triggers: `trg_<tabla>_<evento>`.
- Nombrar explícitamente constraints nuevos; no depender de nombres generados por PostgreSQL.
- Toda FK documenta `RESTRICT`, `CASCADE` o `SET NULL` según el ciclo de vida del dato.
- Las restricciones importantes existen en la base de datos además de validarse en Python.

### 11.5 Auditoría

Las operaciones que lo requieran deben conservar como mínimo actor y timestamp. Para datos clínicos o históricos, la decisión de auditoría debe especificar:

- entidad y operación;
- actor;
- timestamp UTC;
- motivo si aplica;
- valores anterior y nuevo si se necesita reconstrucción;
- política de retención.

## 12. Migraciones y evolución del esquema

El esquema debe evolucionar de forma explícita y verificable.

- `schema.py` representa la definición declarativa esperada.
- `db_init.py` puede mantenerse como bootstrap pragmático durante el TFG, pero no debe ocultar migraciones fallidas.
- Todo cambio manual de esquema se refleja simétricamente en `schema.py` y en el bootstrap/migración correspondiente.
- Las operaciones de bootstrap y migración deben ser idempotentes.
- Una migración debe tener una finalidad identificable y no mezclar cambios funcionales no relacionados.
- Las migraciones destructivas requieren una decisión explícita, respaldo y documentación.
- Si una migración tolera un fallo parcial mediante savepoint, debe dejar claramente indicado si el sistema puede continuar de forma segura.
- No continuar aparentando inicialización correcta después de fallar una modificación obligatoria del esquema.

## 13. Política de testing quirúrgico

Se prioriza la cobertura de comportamiento crítico sobre la cantidad de líneas cubiertas.

### 13.1 Tests obligatorios por CRUD o caso de uso

Cuando se modifique una tabla o función de persistencia, probar según corresponda:

- resultado correcto;
- lista vacía;
- `NotFoundError` o recurso no visible;
- validación inválida;
- ownership y permisos;
- conflicto de unicidad;
- rollback de operaciones compuestas;
- comportamiento con `commit=False`;
- repetición de la misma petición;
- filtrado de soft-delete.

### 13.2 Tests de dominio

Priorizar:

- cálculos de macros e insulina;
- conversiones de unidades y fechas;
- reglas de estados de eventos;
- normalización de nombres;
- algoritmos de estadísticas;
- parsing y validación numérica.

### 13.3 Tests de integración

Cuando la regla dependa de PostgreSQL, usar tests de integración para comprobar:

- constraints y conflictos concurrentes;
- índices únicos parciales;
- cascadas, `RESTRICT` y `SET NULL`;
- rollback real de transacciones;
- filtros de propietario y soft-delete.

Las validaciones puramente visuales pueden hacerse manualmente durante el TFG, pero las respuestas HTMX críticas deben tener al menos una prueba de status, target/evento esperado y mensaje de error.

## 14. Procedimiento obligatorio de auditoría por tabla

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
12. Tests de resultados vacíos, validación, permisos, rollback y concurrencia.

Cada hallazgo se clasifica como una de estas categorías:

- inconsistencia de convención;
- bug funcional o de seguridad;
- decisión pendiente de producto o modelo;
- deuda técnica que puede aplicarse solo a código nuevo.

No se refactoriza una tabla hasta decidir la convención aplicable y el alcance de migración. Las correcciones deben mantener una única fuente de verdad y actualizar código, esquema, tests y documentación cuando corresponda.
