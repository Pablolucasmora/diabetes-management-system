
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

