# Plan de auditoría y estabilización — DayBetes

Última actualización: 2026-09-23

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

> **Actualización 2026-09-24 (auditoría de `catalog`, hallazgo 12).** Los
> estados físicos (`catalog.initial_state`, `portion_detail.final_state`),
> la cocción (`portion_detail.cooking`) y la conservación
> (`portion_detail.conservation`) **dejan de ser listas abiertas**: pasan a
> ser enums cerrados con `CHECK` con nombre en las cuatro columnas, porque
> solo se amplían editando el código (`code_conventions.md` §4.1, y §4.5 con
> la definición de "ampliar"). La asimetría de `initial_state` se resuelve
> añadiendo el `CHECK` a las otras tres, no quitándoselo. La categoría ya se
> había decidido cerrada (hallazgo 1). En §4.5 quedan tres conceptos
> abiertos, ahora listados en la propia convención: marcas (ya
> implementado), subtipos (`catalog.subtype`, `manual_intake.subtype`) y
> origen de comida manual (`manual_intake.origin`), estos dos últimos
> todavía sin catálogo. Detalle en `audit/feedbacks/feedback_catalog.md`,
> punto 12. No registrado en `decisions.md`, por decisión del usuario. El
> texto de abajo se conserva como estaba el 2026-09-08.

`code_conventions.md` §4.5 nombra seis conceptos que deberían vivir en
tablas de catálogo (id, código, etiqueta, `is_active`): subtipos de
comida, marcas de comida, origen de comida manual, estados físicos
inicial/final, métodos de cocción y métodos de conservación. Estado
real comprobado hoy:

| Concepto | Columna | Estado |
|---|---|---|
| Marcas | `food_brands` + `catalog.brand_id` | **Cerrado 2026-09-05**: `food_brands` es catálogo §4.5 (`code`, `label`, `is_active`) y `catalog.brand_id` es FK real. Deuda menor en `audit/deuda_pendiente.md`. |
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
- [x] `food_brands` — 2026-09-05 (audit → plan → review → build; deuda
      restante en `audit/deuda_pendiente.md`)
- [x] `insulin_injections` — 2026-09-08 (audit → plan → review → build →
      bootstrap ejecutado y verificado contra la base real, pasada de
      verificación P1/P1.5 confirmada en `audit/audit_insulin_injections.md`;
      deuda restante —H12, H13 parte de captura, clasificación
      archivable, H14/H15/H16 y la divergencia Python/Postgres del
      tiempo— en `audit/deuda_pendiente.md`)
- [x] `intake_event` — 2026-09-11 (audit → plan → review → build, siete
      pasadas de auditoría, 52 hallazgos: resueltos, diferidos por decisión
      explícita o trasladados a su tabla; hallazgo 36 —commit pendiente y
      `confirm` real por navegador— era el único bloqueante y quedó resuelto
      en esta fecha; deuda restante —H13 defaults "inteligentes" parcial
      (`meal_type` ya implementado), H15 `render_page()` transversal, H21
      caducidad de `planned`, H27 interfaz de archivado, listeners
      `addSuccess`/`addError`— en `audit/deuda_pendiente.md`)
- [x] `portion_detail` — 2026-09-23 (audit → feedback → plan → review →
      build → review de cierre, 27 hallazgos: resueltos, diferidos por
      decisión explícita o dejados como limitación declarada; plan
      `audit/plan.md` T0-T6 implementado, hallazgos del review de cierre
      corregidos en `29beae9`, merge en `main` con `abfde09`; ajuste
      posterior del mismo día: `is_cooked_weight` entra en la clave única de
      la tanda y la vista previa de la página del ingrediente aplica el
      `cooking_factor` (`3403a15`); deuda restante —H1 versionado de
      alimentos, H4 borrado de usuario, H11 actor, H27 rutas que exigen
      `planned`, `ml` en líquidos, y la parte transversal del fallo SQL →
      `None` en `crud.py`— en `audit/deuda_pendiente.md`)

Fuera de alcance por ahora (decisión tuya, no técnica):
- `fridge` — funcionalidad todavía no implementada, no se audita hasta que exista.
- `tags` — no se va a mantener en esta fase, no se audita.
- `linked_tags` — es la tabla de relación de `tags`; si `tags` no se
  mantiene, probablemente tampoco haga falta auditar esta. **Pendiente
  de que lo confirmes** cuando lleguemos ahí — la dejo fuera de los
  grupos de abajo salvo que me digas lo contrario.

**Nota sobre el orden real seguido**: la secuencia de grupos de abajo era la
prevista el 2026-09-08, pero en la práctica se auditó `intake_event` (Grupo 4)
antes que `recipe`/`catalog`/`manual_intake`/`user_favorites` (Grupos 2-3), por
decisión del usuario en el momento. Se deja constancia aquí en vez de
reescribir la secuencia con efecto retroactivo. `portion_detail` (también
Grupo 4) se auditó justo después por continuidad directa con
`intake_event` (hallazgo 28 trasladado, dependencia de
`measurement_conventions.md` §6.9.3) y quedó cerrada el 2026-09-23. Con ella
el Grupo 4 está completo; se retoma el orden previsto por el Grupo 2,
empezando por `catalog` (decisión del usuario, 2026-09-23): es la raíz de
la que dependen `recipe` y `manual_intake`, y es la tabla donde se documenta
la decisión de catálogos abiertos del §4.5.

Pendientes (4), agrupadas por tamaño/dependencia — dentro de cada
grupo el orden es libre, pero conviene mantener el orden entre grupos:

### En curso
- [ ] `catalog` — siguiente tabla (Grupo 2), a partir del 2026-09-23. Aún
      no existe `audit/audit_catalog.md`: el primer paso es la auditoría
      contra §13. Puntos de partida ya conocidos, que no hay que
      redescubrir:
      - la decisión de catálogos abiertos del §4.5 (sección dedicada
        arriba; **resuelta el 2026-09-24**: estados, cocción y
        conservación pasan a enums cerrados, hallazgo 12), incluido el `CHECK`/validación de servidor de
        `portion_detail.cooking/conservation/final_state` que el hallazgo
        19 de `portion_detail` difirió aquí, y `manual_intake.origin`;
      - los tres "Defectos de `catalog`" que dejó el cierre de
        `food_brands` en `audit/deuda_pendiente.md` (timestamps sin zona,
        índice único no parcial, constraints sin nombre);
      - `cooking_factor`: "sin factor" y "factor 1.0" son hoy
        indistinguibles (comportamiento interino de la decisión
        2026-09-18, pendiente de la tabla de equivalencias);
      - la convención nueva `code_conventions.md` §1.3.2 (columnas
        cualificadas en SQL), que nació de un `AmbiguousColumn` en
        `queries/catalog.py`.

### Grupo 2 — Entidades principales de comida
- [ ] `recipe` — sus porciones viven en `portion_detail` (destino
      `recipe`, ya cerrada); la lectura de recetas públicas pasa por
      `list_viewable_recipe_portions`; deuda relacionada: "Add recipe to
      plate functionality" (2026-09-20) en `audit/deuda_pendiente.md`.
- [ ] `manual_intake`

### Grupo 3 — Relaciones dependientes
- [ ] `user_favorites`

### Opcionales, fuera del audit global actual
Tablas creadas después de este plan, ya siguiendo `conventions/`. Por
decisión del usuario (2026-09-23) no entran en el audit global actual ni
cuentan para el cierre del plazo: se pueden auditar después, si se ve
necesario.
- `intake_plate` — tandas de un evento (decisión 2026-09-19), nacida
  durante la auditoría de `portion_detail`.
- `meal_type_schedule` — franjas horarias por defecto de cada tipo de
  comida (`feat/meal-type-schedule`).

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
- Catálogos abiertos del §4.5 sin migrar: tras el 2026-09-24 solo quedan
  subtipos y origen de comida manual (ver sección dedicada arriba).
