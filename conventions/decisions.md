
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
