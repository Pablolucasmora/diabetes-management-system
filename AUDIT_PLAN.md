# Plan de auditoría y estabilización — DayBetes

Última actualización: 2026-09-04

## Objetivo y marco de tiempo

Cerrar la auditoría de las tablas del esquema contra
`conventions/code_conventions.md` §13, corrigiendo bugs y aplicando
convenciones **a la vez** (no en dos pasadas separadas — ver
diagnóstico más abajo). Plazo objetivo: 2 semanas desde hoy, a razón de
~2h/día. Es tu TFG y lo defiendes tú: el proceso está diseñado para que
apruebes cada plan antes de que se toque código y entiendas el porqué,
no para que corra en piloto automático.

## Diagnóstico: por qué esto se estaba comiendo el tiempo

1. **El pipeline se ejecutaba por hallazgo, no por tabla.** `propose`
   tomaba "un hallazgo" (singular) y generaba un plan solo para ese
   hallazgo. Una tabla con 8 hallazgos eran 8 ciclos completos de
   `propose → review → build`. Eso es lo que consumía el tiempo, no la
   dificultad real del código. **Ya corregido** (ver más abajo).
2. **No había verificación después de `build`.** `review` compara el
   plan contra el código *antes* de construir, pero nada comprobaba
   *después* que `build` (que corre en el modelo más barato/rápido,
   Haiku) implementó realmente todo lo planeado. Por eso cada
   auditoría nueva "encontraba cosas" — no es que algo se hiciera mal
   a propósito, es que nadie comprobaba el resultado final hasta la
   siguiente auditoría completa (cara, con Opus, desde cero).
3. **No había una definición explícita de "tabla cerrada".** Sin un
   techo, cualquier repaso a mayor profundidad siempre encuentra algo
   más — eso no es una señal de fallo del proceso, es la naturaleza de
   una revisión sin límite definido.
4. **El pipeline en sí tenía piezas rotas sin estrenar**: los tres
   scripts de los hooks de seguridad (`restrict-to-audit.sh`,
   `block-audit-writes.sh`, `readonly-bash-decision.sh`) no existían
   — ya creados y verificados (`scripts/`). `audit.md` también
   apuntaba a la antigua "sección 14 / 16 puntos", ya corregido a
   "sección 13 / 15 puntos".

## Los tres cambios de método (ya aplicados)

1. **Agrupar por tabla, no por hallazgo.** `propose.md` ahora recibe
   *todos* los hallazgos ALTO/MEDIO (+ BAJO triviales) de una tabla y
   escribe un único `audit/plan.md` consolidado, con una subsección
   por hallazgo — cada una explica qué sección de `conventions/`
   respalda la decisión, igual que antes. **Tú lees y apruebas ese
   plan.md consolidado antes de que `build` toque nada** — agrupar
   reduce cuántas veces se repite el ciclo, no te saca de la decisión.
2. **Verificación post-build barata.** Después de `build`, se vuelve
   a invocar `review` sobre el **mismo** `audit/plan.md`, ahora contra
   el código ya modificado, para confirmar que el diff real cumple lo
   planeado. Si hay discrepancias puntuales se corrigen directamente,
   sin montar una auditoría nueva.
3. **Backlog único de deuda diferida.** Los hallazgos BAJO no
   triviales y las decisiones que decidas posponer van a
   `audit/deuda_pendiente.md` (un solo archivo para todo el proyecto,
   fuera del ciclo por tabla).

## Cómo te mantienes al mando y aprendes en el camino

- **Nada se implementa sin que veas el plan primero.** `audit_<tabla>.md`
  (hallazgos) y `plan.md` (solución propuesta) son documentos que lees
  tú antes de aprobar — son cortos porque `propose` calibra el detalle
  por severidad, no porque se te oculte nada.
- **Para cada hallazgo, el plan cita la sección de conventions/ que lo
  respalda** — es la forma más rápida de que entiendas el "por qué" sin
  tener que preguntarlo aparte.
- **Al cerrar cada tabla**, pide 1-2 explicaciones de los cambios que
  más te interesen de esa tabla concreta (no de todos — sería demasiado
  tiempo). Es la misma dinámica que hemos seguido con `users` /
  `auth_sessions`: yo investigo y te presento hallazgos con evidencia
  real del código antes de tocar nada, tú decides.
- **Agente `explain`** (`.claude/agents/explain.md`): para cualquier
  duda suelta que te surja — una función, un error, un porqué — al
  margen del ciclo de auditoría. Solo lee código y conventions/, nunca
  edita nada, así que puedes preguntarle lo que quieras sin riesgo de
  que "de paso" cambie algo fuera del plan aprobado.
- **Time-box duro**: si una explicación se alarga más de ~15 min, se
  anota en "Aprendizajes pendientes" (abajo) y se retoma después de
  cerrar el plazo de las 2 semanas — no a mitad de una tabla.

## Qué significa CERRAR una tabla

Una tabla se marca ✅ en este documento cuando:

- [ ] `audit/audit_<tabla>.md` existe y recorre los 15 puntos de la
      sección 13.
- [ ] Todo hallazgo ALTO y MEDIO está implementado y confirmado por el
      review post-build, **o** diferido explícitamente en
      `audit/deuda_pendiente.md` con una razón de una línea.
- [ ] Toda "Decisión pendiente" señalada se resolvió contigo (aunque
      la respuesta sea "no lo necesito ahora, documenta y sigue").
- [ ] Los hallazgos BAJO triviales están implementados; el resto en
      el backlog.

**Regla que corta el bucle de desconfianza: una vez marcada ✅, esa
tabla no se vuelve a auditar desde cero "por si acaso".** Solo se
reabre si tocas su código por una función nueva, o aparece un bug real
de uso. "Cerrada según el checklist de la sección 13" es la
definición de terminado — no "cero hallazgos posibles bajo cualquier
nivel de escrutinio futuro", porque ese segundo estándar no se alcanza
nunca.

## Decisión diferida: catálogos abiertos del §4.5

`code_conventions.md` §4.5 nombra seis conceptos que deberían vivir en
tablas de catálogo (id, código, etiqueta, `is_active`): subtipos de
comida, marcas de comida, origen de comida manual, estados físicos
inicial/final, métodos de cocción y métodos de conservación. Estado
real comprobado hoy:

| Concepto | Columna | Estado |
|---|---|---|
| Marcas | `food_brands` (tabla) + `catalog.brand` | La tabla existe, pero `catalog.brand` es texto libre **sin FK** a ella — solo autocomplete. |
| Subtipos | `catalog.subtype`, `manual_intake.subtype` | `VARCHAR` libre, sin `CHECK`, sin catálogo. |
| Origen manual | `manual_intake.origin` | `VARCHAR` libre, sin `CHECK`, sin catálogo. |
| Estado físico inicial | `catalog.initial_state` | `CHECK` **cerrado** en BD — al revés de lo que pide 4.5 (más rígido que los demás, no más abierto). |
| Estado físico final | `portion_detail.final_state` | `VARCHAR` libre, **sin ningún `CHECK`**. |
| Cocción | `portion_detail.cooking` | `VARCHAR` libre, sin `CHECK`; validado solo en Python (`COOKING_OPTIONS`). |
| Conservación | `portion_detail.conservation` | `VARCHAR` libre, sin `CHECK`; validado solo en Python (`CONSERVATION_OPTIONS`). |

**Decisión**: no se crean las 5 tablas de catálogo nuevas dentro de
este sprint de 2 semanas — es un proyecto de migración en sí mismo
(nuevas tablas + convertir columnas a FK + tocar `food_routes.py` y
`components/food/foods.py`, ambos con miles de líneas). La propia
convención lo permite como estado transicional ("las listas Python
existentes solo pueden actuar como datos iniciales mientras se
completa el catálogo").

**Lo que sí se hace, barato, dentro de las auditorías ya planeadas**:
cuando se audite `catalog` (primera tabla afectada), añadir validación
de servidor contra las listas Python ya existentes en las columnas que
hoy no tienen ni `CHECK` (`portion_detail.cooking/conservation/final_state`,
`manual_intake.origin`) — cierra el agujero real de integridad (hoy una
petición que se salte la UI podría escribir cualquier texto) sin
migrar el modelo. Se documenta la decisión completa **una sola vez**
durante la auditoría de `catalog`; las auditorías de `manual_intake` y
`portion_detail` solo referencian esa decisión, no la repiten.

Si en algún momento quieres formalizar esto en `conventions/decisions.md`,
dímelo explícitamente cuando lleguemos a la auditoría de `catalog` — no
lo registro por iniciativa propia.

## Secuencia de tablas

Ya cerradas (sesión previa a este plan):
- [x] `users` — 2026-09-04
- [x] `auth_sessions` — 2026-09-04 (decisión 2026-09-02/03 en decisions.md)
- [x] `auth_rate_limits` — 2026-09-04 (extraída de auth/service.py)

Fuera de alcance por ahora (decisión tuya, no técnica):
- `fridge` — funcionalidad todavía no implementada, no se audita hasta que exista.
- `tags` — no se va a mantener en esta fase, no se audita.
- `linked_tags` — es la tabla de relación de `tags`; si `tags` no se
  mantiene, probablemente tampoco haga falta auditar esta. **Pendiente
  de que lo confirmes** cuando lleguemos ahí — la dejo fuera de los
  grupos de abajo salvo que me digas lo contrario.

Pendientes (8), agrupadas por tamaño/dependencia — dentro de cada
grupo el orden es libre, pero conviene mantener el orden entre grupos:

### Grupo 1 — Catálogos simples (para coger ritmo con el nuevo proceso)
- [ ] `food_brands`
- [ ] `insulin_injections` *(FK a `intake_event`; su propio análisis no
      depende de que esa tabla esté cerrada, pero ten presente ese
      vínculo al revisar ownership)*

### Grupo 2 — Entidades principales de comida
- [ ] `recipe`
- [ ] `catalog` *(aquí se documenta la decisión de catálogos abiertos del §4.5)*
- [ ] `manual_intake`

### Grupo 3 — Relaciones dependientes
- [ ] `user_favorites`

### Grupo 4 — Núcleo transaccional (las más grandes; deja más margen)
- [ ] `intake_event`
- [ ] `portion_detail`

## Estimación orientativa (revisar tras las 2-3 primeras tablas)

Con ~2h/día durante 14 días tienes ~28h de presupuesto total.

| Tabla | Horas est. |
|---|---:|
| food_brands, insulin_injections | 1-2 h c/u |
| recipe | 2-3 h |
| catalog *(incluye decisión §4.5)* | 4-6 h |
| manual_intake | 3-5 h |
| user_favorites | 1-2 h |
| intake_event, portion_detail | 4-6 h c/u |

Total orientativo: ~24-31 h — encaja con el presupuesto, pero sin
apenas margen si alguna tabla del Grupo 4 se complica. Ajusta esta
tabla después de cerrar las 2 primeras del Grupo 1, que te darán una
medida real de cuánto tarda el ciclo nuevo por tabla.

## Aprendizajes pendientes de retomar con calma

*(vacío — añadir aquí cuando algo se aparque por tiempo)*

## Deuda técnica ya conocida (heredada de users/auth_sessions)

- Ciclo de vida de `users` sin definir: no hay `deleted_at` ni ninguna
  ruta que ponga `is_active=False`; no se puede desactivar/borrar una
  cuenta hoy.
- `verify_password()` mantiene una rama de migración "sin pepper → con
  pepper" para hashes legacy, sin forma de saber cuántos quedan.
- `get_auth_rate_limit()` usa `SELECT ... FOR UPDATE` sin
  `connection.transaction()` explícita (funciona por el modo
  implícito de psycopg, pero no es literal a la letra de §6.8).
- Catálogos abiertos del §4.5 sin migrar (ver sección dedicada arriba).
