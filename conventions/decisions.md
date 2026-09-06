
## 2026-09-02 — Ciclo de vida y timestamps de auth_sessions

**Origen**: tabla auth_sessions, hallazgos medios de auditoría
**Contexto**: La tabla almacenaba timestamps sin zona, no tenía constraints temporales, no limpiaba sesiones inválidas y sus lecturas se transportaban como diccionarios. Era necesario preservar instantes UTC, evitar estados temporales imposibles, controlar el crecimiento de sesiones y establecer un contrato tipado para autenticación.
**Alternativas consideradas**:
- Mantener `TIMESTAMP` sin zona y continuar interpretando manualmente los valores como UTC.
- Conservar sesiones expiradas indefinidamente para una auditoría histórica.
- Reactivar sesiones mediante un `UPDATE` sin condiciones adicionales.
- Mantener filas SQL como diccionarios entre persistencia y middleware.
- Usar `TIMESTAMPTZ`, retener sesiones inválidas durante 14 días, actualizar sesiones solo si siguen siendo válidas y usar una dataclass específica de autenticación.
**Decisión**: `created_at`, `last_seen_at`, `expires_at` y `revoked_at` se almacenan como `TIMESTAMPTZ` y los valores heredados se interpretan como UTC. Las sesiones revocadas se conservan 14 días desde `revoked_at`; las no revocadas, 14 días desde `expires_at`, y después se eliminan físicamente. `refresh_session()` solo actualiza sesiones no revocadas, no expiradas y asociadas a usuarios activos. PostgreSQL refuerza la coherencia temporal mediante constraints. Las lecturas de sesión usan `AuthSessionRead`, con hashes fuera de `repr`, y la limpieza se ejecuta de forma oportunista durante el login.
**Convención actualizada**: `conventions/measurement_conventions.md sección 9.1`; `conventions/code_conventions.md secciones 2.2, 3.1, 6.6, 11.6 y 11.10`

## 2026-09-03 — Sin auditoría separada para auth_sessions

**Origen**: decisión de alcance para la tabla auth_sessions
**Contexto**: `auth_sessions` es una entidad operativa dependiente usada para autenticación web y control de sesión. La fase TFG del proyecto no requiere conservar una historia separada de revocaciones, logouts o purgas para esta tabla, y la convención de auditoría de cambios solo aplica a tablas o campos que realmente requieran trazabilidad específica.
**Alternativas consideradas**:
- Añadir una tabla de auditoría separada para login, logout, revocación y purge.
- Guardar actor, motivo y `request_id` directamente en `auth_sessions`.
- No añadir auditoría separada para esta tabla en la fase TFG.
**Decisión**: `auth_sessions` no tendrá auditoría separada de cambios en esta fase. La fila operativa mantiene solo los campos necesarios para autenticación, renovación y purga temporal. Si en el futuro se necesita trazabilidad adicional, se decidirá como una auditoría independiente y específica, no como sobrecarga de la tabla de sesión.
**Convención actualizada**: ninguna

## 2026-09-05 — `food_brands` pasa a catálogo global y único; `catalog.brand` se elimina

**Origen**: tabla food_brands, hallazgo 1 de `audit/audit_food_brands.md` (`food_brands` desincronizada de `catalog.brand`, texto libre sin FK)
**Contexto**: `catalog.brand` era texto libre sin relación con `food_brands`, que a su vez era una copia parcial y ya desincronizada (una marca, `SOS`, existía en `catalog` pero no en `food_brands`). El hallazgo planteaba dos vías: (a) promover `food_brands` a fuente única con `catalog.brand_id` como FK, o (b) seguir sincronizando dos copias del mismo dato. La vía (b) no elimina la causa del desfase — cualquier nuevo desfase futuro requeriría el mismo trabajo de reconciliación.
**Alternativas consideradas**:
- (a) `food_brands` como catálogo §4.5, fuente única; `catalog.brand_id INTEGER REFERENCES food_brands(id)`; se elimina `catalog.brand`.
- (b) Mantener `catalog.brand` como texto y sincronizar `food_brands` con una migración periódica o un trigger.
**Decisión**: vía (a). `food_brands(id, code, label, is_active, created_by, created_at, updated_at)` es la fuente única de marcas; `code` es la clave normalizada de deduplicación (`lower` + `btrim` + colapso de espacios) y `label` conserva el texto tal cual lo escribió el usuario, sin forzar Title Case (evita degradar siglas como `"SOS"` a `"Sos"`). `catalog.brand_id` referencia `food_brands(id)` con `ON DELETE SET NULL`. Las marcas son globales y públicas: el nombre de una marca nacida de un ítem privado deja de ser privado al entrar en el catálogo compartido (se asume que un nombre de marca comercial no es información privada). Al migrar duplicados por `code`, gana la `label` que ya existía en `food_brands`, o si no existía ninguna, la grafía más frecuente en `catalog` (desempate por `catalog.id` más bajo).
**Convención actualizada**: ninguna (el patrón de catálogo §4.5 y las reglas de normalización/constraints ya estaban cubiertas por `code_conventions.md` secciones 10.4, 10.5, 11.5, 11.6, 11.7 y 11.8; esta entrada documenta la decisión de modelo aplicada a esta tabla, no una convención nueva)

## 2026-09-05 — Administración de marcas (`is_active`) queda fuera de esta fase

**Origen**: tabla food_brands, hallazgo 4 de `audit/audit_food_brands.md`
**Contexto**: Con `food_brands` como catálogo global compartido, hace falta poder desactivar, renombrar o fusionar una marca con errata, pero eso requiere decidir primero quién administra un catálogo compartido por todos los usuarios (política de roles). `users.category` (`schema.py:19`) existe como columna reservada para un futuro sistema de roles, pero no está definida ni implementada.
**Alternativas consideradas**:
- Implementar ya un endpoint de administración de marcas abierto a cualquier usuario autenticado.
- Bloquear el cierre de `food_brands` hasta decidir la política de roles completa.
- Crear `is_active` y las columnas de auditoría (`created_by`, `updated_at`) ahora, pero dejar sin endpoint de administración hasta que exista la decisión de roles.
**Decisión**: tercera vía. `is_active` se crea en el esquema y ya filtra las sugerencias, pero no existe todavía forma de desactivar una marca salvo SQL manual. Queda registrado como deuda pendiente en `audit/deuda_pendiente.md` hasta que se decida la política de roles.
**Convención actualizada**: ninguna

## 2026-09-05 — Orden de resolución de marca nueva respecto a la comprobación de duplicados en `catalog`

**Origen**: `audit/review.md` (divergencia 2), corrección post-build sobre el plan de food_brands
**Contexto**: Al crear o editar un ítem de `catalog` con una marca nueva (`brand__added=true`), la ruta llamaba a `catalog_name_brand_exists` antes de crear la marca dentro de la transacción, por lo que la comprobación comparaba contra `brand_id = NULL` ("sin marca") y producía falsos positivos de duplicado cuando ya existía un ítem homónimo sin marca.
**Alternativas consideradas**:
- Mover la creación de la marca (`create_food_brand`) dentro de la transacción y antes de `catalog_name_brand_exists`, lanzando `ValueError` en caso de duplicado (mismo patrón que el resto de validaciones dentro de `connection.transaction()` en `food_routes.py`).
- Introducir una excepción `ConflictError` específica para este caso.
**Decisión**: primera vía, por consistencia con las otras 14 apariciones de `except ValueError as error` ya existentes en `food_routes.py` para abortar una transacción con rollback y devolver el mensaje al formulario. Se aplica igual en las rutas de crear y editar catálogo.
**Convención actualizada**: ninguna


## 2026-09-06 — Identidad de conexión separada para bootstrap (migraciones) y runtime

**Origen**: hallazgo 3 (ALTO) de `audit/audit_insulin_injections.md`
**Contexto**: El proyecto separa un rol propietario de base de datos (`plucmor`, dueño de las 14 tablas) de un rol de aplicación con privilegios reducidos (`daybetes_app`), pensado para que un compromiso de la app en ejecución no pueda alterar esquema. Sin embargo, `get_connection()` usa siempre `DATABASE_URL` (la identidad `daybetes_app`), tanto para las queries normales como para `init_db()`, que ejecuta DDL (`CREATE TABLE`, `ALTER TABLE`, `ADD CONSTRAINT`, `CREATE INDEX`). PostgreSQL exige privilegios de propietario para DDL, que un `GRANT` de DML no concede, así que el bootstrap falla (`must be owner of table insulin_injections`, comprobado). Con `DB_INIT_ON_STARTUP=false` en `.env` el fallo queda enmascarado, pero el esquema físico se congela desincronizado de `schema.py`. Verificación directa contra la base real confirmó que este problema ya había impedido aplicar migraciones dadas por cerradas en código: `food_brands` sigue con el esquema antiguo (`id, name, created_at`), `catalog.brand_id` no existe (sigue `catalog.brand`) y `auth_rate_limits` sigue en `TIMESTAMP` sin zona y sin sus `CHECK`, pese a que `database/queries/crud.py` ya usa `catalog.brand_id` y `food_brands.code/label` en producción. Solo `auth_sessions` se aplicó realmente, mediante ejecución manual como `plucmor`.
**Alternativas consideradas**:
- (a) Dos identidades de conexión separadas: una de migraciones (propietaria, usada solo por `init_db()`), otra de runtime (mínimo privilegio, usada por el resto de la app).
- (b) Conceder a `daybetes_app` propiedad o privilegios equivalentes a DDL sobre las tablas, para que el bootstrap funcione con la misma identidad que el runtime.
- (c) Eliminar la ejecución automática del bootstrap al arrancar la app; tratar cualquier cambio de esquema como un paso administrativo manual ejecutado explícitamente por el propietario.
**Decisión**: vía (a). `init_db()` se conecta con una identidad de migraciones propietaria de los objetos de esquema; el resto de la aplicación (rutas, servicios, CRUD) sigue usando `DATABASE_URL` con la identidad `daybetes_app`, sin privilegios de DDL, ni siquiera durante el arranque. La vía (b) se descarta por deshacer el propósito original de la separación de roles. La vía (c) queda como alternativa válida pero más restrictiva operativamente; se prioriza (a) por mantener el arranque automático de un solo comando sin sacrificar la separación de privilegios. Queda pendiente, como acción separada de esta decisión, aplicar contra la base real las migraciones de `food_brands`, `catalog.brand_id` y `auth_rate_limits` que ya existen en código pero nunca se ejecutaron.
**Convención actualizada**: `conventions/code_conventions.md` sección 12 (nueva 12.6); referencia cruzada en sección 8.1.

## 2026-09-06 — Confirmar un evento con `insulin_dose = TRUE` registra siempre una inyección; la zona es opcional

**Origen**: hallazgo 1 (ALTO) de `audit/audit_insulin_injections.md` ("decisión pendiente: qué debe ocurrir al confirmar un evento con `insulin_dose = TRUE` pero sin zona seleccionada")
**Contexto**: Hoy `finalize_injection_zone_for_event` devuelve `True` sin insertar nada cuando el evento no tiene zona, de forma implícita y sin dejar rastro; el confirm responde 200 aparentando éxito. Las 9 filas reales de la tabla tienen `intake_event_id = NULL`: nunca se ha creado una inyección automática. `measurement_conventions.md` §8.2 define `insulin_dose` como indicador, pero no dice si obliga a registrar una inyección.
**Alternativas consideradas**:
- Bloquear el confirm con `400` si falta la zona.
- Confirmar el evento sin registrar inyección (comportamiento implícito actual).
- Registrar siempre la inyección, con `injection_zone = NULL` cuando el usuario no la haya seleccionado.
**Decisión**: tercera vía. Al confirmar un evento con `insulin_dose = TRUE` **siempre** se guarda una fila en `insulin_injections`. Si no hay zona seleccionada, la fila se guarda con `injection_zone = NULL`, que significa "zona no registrada" (no "no hubo inyección"). En consecuencia `injection_zone` permanece **nullable** y no recibe `NOT NULL`, en contra de lo que proponía el hallazgo 5. Una zona presente pero fuera del enum sí es un error de validación explícito, no un `NULL` silencioso.
**Convención actualizada**: `conventions/measurement_conventions.md` sección 8.2 (relación entre `insulin_dose` e `insulin_injections`)

## 2026-09-06 — `basal_units` pasa a llamarse `units`

**Origen**: hallazgo 5 (MEDIO) de `audit/audit_insulin_injections.md` ("decisión pendiente: si en el futuro una inyección rápida podrá llevar unidades")
**Contexto**: La columna se llama `basal_units` pero conceptualmente son unidades de insulina, no "unidades basales". `measurement_conventions.md` §8.1 dejaba abierto si una inyección rápida podrá registrar dosis. Si va a poder, un `CHECK` que obligue a `NULL` en rápida sería demasiado estricto y obligaría a una segunda migración.
**Alternativas consideradas**:
- Mantener `basal_units` y un `CHECK` que fuerce `NULL` para rápida.
- Renombrar a `units`, obligatoria para basal y opcional para rápida.
**Decisión**: la columna pasa a llamarse `units`. Sigue siendo **obligatoria y positiva para insulina basal**. Para insulina rápida es opcional: hoy siempre se guarda `NULL` porque el formulario de rápida no captura dosis, pero el modelo admite un valor positivo sin migración adicional, de cara a poder registrar las unidades cuando se use una pluma que no las envía sola (el bolígrafo inteligente ya las registra por su cuenta). Permitir la captura de unidades en el formulario de rápida queda como trabajo pendiente, no como parte de este ciclo.
**Convención actualizada**: `conventions/measurement_conventions.md` sección 8.1

## 2026-09-06 — Un `intake_event` puede tener varias inyecciones

**Origen**: hallazgo 10 (MEDIO) de `audit/audit_insulin_injections.md` ("¿cuántas inyecciones puede tener un `intake_event`?")
**Contexto**: El código asume "exactamente una" y por eso `finalize_injection_zone_for_event` borra físicamente todas las inyecciones del evento antes de reinsertar una, destruyendo registro clínico. En la práctica una misma comida puede requerir más de un pinchazo: comidas largas que se parten en dos y correcciones post-comida.
**Alternativas consideradas**:
- `UNIQUE (intake_event_id)`: un evento, una inyección; el `DELETE`+`INSERT` se sustituye por `ON CONFLICT DO UPDATE`.
- Cardinalidad N: sin unicidad por evento; el confirm crea una única inyección automática y el resto se registran aparte.
**Decisión**: cardinalidad **N**. Un `intake_event` puede tener varias inyecciones asociadas y no se crea `UNIQUE (intake_event_id)`. El `DELETE` previo desaparece: el confirm crea una sola inyección automática, y su no duplicación se garantiza porque la transición `planned -> consumed` es condicional (un segundo confirm no aplica y revierte la transacción). En la interfaz se prevé, cuando la casilla de insulina esté marcada, un campo con el número de pinchazos de esa comida (1, 2, 3...), y en el formulario de rápida un campo opcional de unidades; ambos quedan pendientes de implementar, pero el modelo ya los admite sin cambio de esquema.
**Convención actualizada**: `conventions/measurement_conventions.md` sección 8.2

## 2026-09-06 — Sin restricción temporal ni control de duplicados en `insulin_injections`

**Origen**: hallazgo 9 (MEDIO) de `audit/audit_insulin_injections.md`
**Contexto**: No hay validación de rango de `shot_time` (se puede registrar el año 2200) ni detección de duplicados: un doble submit crea dos filas idénticas. Pero dos inyecciones legítimas pueden compartir minuto, tipo y zona, así que una `UNIQUE (users_id, shot_time, insulin_type)` rechazaría dato válido.
**Alternativas consideradas**:
- Limitar `shot_time` a un rango (no futuro, no anterior a la creación de la cuenta) con validación y `CHECK`.
- Añadir unicidad o aviso de duplicado.
- No restringir nada por ahora.
**Decisión**: por ahora **se permiten inyecciones en cualquier momento** (incluidas futuras, útiles para planificación de basal) y **no se establece control de duplicados**, precisamente porque una inyección repetida en el mismo sitio y hora es posible aunque sea rara. No se añade `CHECK` temporal ni `UNIQUE`. Si en el futuro aparece ruido real en los datos, se revisará como decisión nueva referenciando esta entrada.
**Convención actualizada**: ninguna (decisión específica de esta tabla)

## 2026-09-06 — La FK `insulin_injections.intake_event_id` pasa a `ON DELETE SET NULL`

**Origen**: hallazgo 11 (BAJO) de `audit/audit_insulin_injections.md`
**Contexto**: La FK es hoy `ON DELETE CASCADE`: borrar un evento de comida elimina en silencio la inyección asociada. `code_conventions.md` §11.8 prioriza `RESTRICT` o `SET NULL` para datos históricos o clínicos.
**Alternativas consideradas**:
- Mantener `CASCADE` documentando qué histórico destruye.
- `RESTRICT`: impedir borrar un evento que tenga inyecciones.
- `SET NULL`: conservar la inyección como registro huérfano del evento.
**Decisión**: `ON DELETE SET NULL`, para que borrar el evento no haga perder el pinchazo. La inyección resultante es indistinguible de una manual (`intake_event_id = NULL`) y sigue siendo válida y visible en el listado de ajustes. La FK a `users` se mantiene en `CASCADE` (§11.1: al eliminar la cuenta desaparece su histórico clínico).
**Convención actualizada**: ninguna (§11.8 ya cubre el criterio; esta entrada documenta su aplicación a esta FK)

## 2026-09-06 — Paquete `DayBetes_food/domain/` y ubicación de los mappers

**Origen**: hallazgo 7 (MEDIO) de `audit/audit_insulin_injections.md` (el módulo `domain/` citado por §4.1 no existe todavía) y hallazgo 6 (dataclasses y mappers)
**Contexto**: `code_conventions.md` §4.1 cita `DayBetes_food/domain/constants.py` como ubicación de los enums centrales, pero el paquete no existe: los enums de zona y tipo de insulina están duplicados en `crud.py`, `components/injection_zone.py`, `schema.py` y `db_init.py`. §3.1 exige dataclasses de lectura/comando, pero no dice dónde viven ni dónde vive el mapper de fila SQL. `auth/models.py` es hoy el único precedente, y es específico de un módulo cerrado.
**Alternativas consideradas**:
- Diferir la creación de `domain/` a un trabajo transversal posterior (§13: no construir infraestructura nueva dentro de la auditoría de una tabla salvo petición explícita).
- Estrenar `domain/` con `insulin_injections`, que es quien necesita los dos enums citados textualmente por §4.1.
- Colocar los mappers dentro de `domain/` junto a las dataclasses, o en la capa de persistencia.
**Decisión**: se crea el paquete `DayBetes_food/domain/` en este ciclo, por petición explícita del usuario. Contiene `constants.py` (enums de dominio) y un módulo por entidad con sus dataclasses (`domain/insulin.py`). `domain/` no importa psycopg, rutas ni componentes. Los **mappers de fila SQL a dataclass viven en la capa de persistencia** (`DayBetes_food/database/mappers.py`), porque conocen nombres físicos de columna (`users_id` → `user_id`) que el dominio no debe conocer. Las etiquetas visibles y las imágenes asociadas a un enum siguen en `components/`, como mapper de presentación, nunca en `domain/`.
**Convención actualizada**: `conventions/code_conventions.md` sección 3.6 (nueva) y ampliación de la sección 4.1
