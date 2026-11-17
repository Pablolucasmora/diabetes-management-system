# DayBetes — Sistema de gestión personalizada para la diabetes

> Registro preciso de comidas, insulina y contexto diario, guardando junto a cada dato **cuánto se puede confiar en él**, como base para entender cómo responde la glucosa de una persona concreta y, a futuro, ayudarla con recomendaciones hechas a su medida.

| | |
|---|---|
| **Estado** | En producción, uso personal diario (un único usuario). Datos todavía de prueba |
| **Web** | [daybetes.com](https://daybetes.com), de acceso privado |
| **Fase** | Trabajo de Fin de Grado (TFG): diseño del estudio y adaptación de la app |
| **Stack** | Python 3.12 · FastHTML · HTMX · PostgreSQL 17 · Tailwind CSS · Docker |
| **Despliegue** | VPS + Cloudflare Tunnel, con despliegue continuo desde GitHub Actions |

---

## Índice

1. [Qué es DayBetes](#1-qué-es-daybetes)
2. [Objetivo y visión](#2-objetivo-y-visión)
3. [Fases del proyecto](#3-fases-del-proyecto)
4. [Estado actual](#4-estado-actual)
5. [Funcionalidades](#5-funcionalidades)
6. [Modelo de datos](#6-modelo-de-datos)
7. [Arquitectura técnica](#7-arquitectura-técnica)
8. [Despliegue y operación](#8-despliegue-y-operación)
9. [Cómo se desarrolla](#9-cómo-se-desarrolla)
10. [Desarrollo local](#10-desarrollo-local)
11. [Hoja de ruta](#11-hoja-de-ruta)
12. [Documentación del proyecto](#12-documentación-del-proyecto)

---

## 1. Qué es DayBetes

Una persona con diabetes tipo 1 decide varias veces al día cuánta insulina ponerse. La regla que se enseña divide los gramos de hidratos de la comida entre un número fijo, el *ratio*. En la práctica se queda corta:

- **La comida es más que hidratos.** La grasa y la proteína provocan subidas tardías, a veces horas después.
- **El contexto cambia la respuesta.** El ejercicio, una mala noche, el estrés, una enfermedad o el alcohol modifican la sensibilidad a la insulina.
- **Los datos de partida son inciertos.** Nadie sabe con exactitud cuántos hidratos tiene un plato de restaurante, y estimar a ojo tiene un error considerable.
- **Cada persona responde de forma distinta**, y la misma persona cambia con el tiempo.

Cada uno acaba construyendo su propio conocimiento a base de prueba y error. Las aplicaciones generalistas de salud no tratan la glucosa ni la insulina como el centro, y las de diabetes suelen limitarse a un diario de dosis e hidratos.

DayBetes parte de la idea contraria a "las mismas reglas para todos": **cada persona necesita su propio modelo**, y para construirlo hacen falta datos buenos de esa persona. Lo que se registra habitualmente no lo es por dos razones: registrar con detalle cuesta demasiado tiempo, y los registros no dicen cuánto se puede confiar en cada dato. La aplicación ataca las dos:

- **Baja el esfuerzo de registrar**, con recetas reutilizables, un escáner de códigos de barras, una nevera de sobras reutilizables y un asistente de IA (DiaBot) que convierte una frase o una foto en una comida lista para revisar.
- **Guarda la fiabilidad con el dato**: cómo se obtuvo cada cantidad (báscula, envase, medida casera, a ojo o estimación de la IA), de dónde salen los macros de cada alimento, si se pesó crudo o cocinado y qué parte de cada plato se comió de verdad.

---

## 2. Objetivo y visión

### Fase 1: TFG, estudio de un único participante (actual)

El TFG es un estudio observacional **n-of-1**: un único participante, el autor, que registra su vida normal sin cambiar el tratamiento por estar en el estudio. Durante la recogida ningún modelo decide ni sugiere dosis; todo se analiza después.

Las preguntas, en su versión actual (pendientes de revisar con orientación metodológica):

| | Pregunta |
|---|---|
| P1 | ¿Cuánta incertidumbre tienen los valores nutricionales de cada comida? |
| P2 | ¿Cuáles son los parámetros reales (ratio, sensibilidad, duración de la insulina) y cómo cambian con el momento y el contexto? |
| P3 | ¿Cómo responde la glucosa a los distintos alimentos: subidas tardías, momento del bolo, comidas que funcionan bien? |
| P4 | ¿Se puede predecir la glucosa a 30–120 minutos con un margen de error razonable? |
| P5 | ¿Un cálculo de dosis ajustado a los datos personales habría acertado más que la fórmula clásica? (evaluado después, sin cambiar ninguna dosis real) |

El estudio une cuatro fuentes en una misma línea de tiempo:

| Fuente | Qué aporta | Situación |
|---|---|---|
| DayBetes | Comidas, macros y su fiabilidad, insulina y contexto | Comidas e insulina, hecho; contexto, pendiente |
| Sensor continuo (LibreView) | Glucosa cada pocos minutos | Se cruza en el análisis, fuera de la app |
| Boli de insulina con memoria | Hora y unidades exactas de cada dosis | Pendiente de importar |
| Reloj (Apple Health) | Ejercicio, frecuencia cardiaca, sueño, pasos | Se cruza en el análisis, fuera de la app |

Criterios ya pensados: un piloto de dos semanas cuyos datos no se analizan, unas doce semanas de recogida con las últimas reservadas para validar, una comida de referencia repetida para medir la variabilidad propia, y estimaciones previas al pesado en comidas elegidas al azar para medir el error real de estimar a ojo y con la IA.

### Fase 2: aplicación para personas con diabetes (posterior al TFG, condicionada)

Si el estudio demuestra que el planteamiento funciona, la idea es abrir la aplicación a otras personas: un modelo por usuario, predicción de la glucosa con su margen de error, avisos y una **carga de registro ajustable**, en la que cada usuario elige cuánto registrar sabiendo qué gana y qué pierde con cada dato. Eso exige antes protección de datos de salud (RGPD), consentimiento expreso, encaje regulatorio como posible producto sanitario y validación clínica. Nada de esto está hecho.

> DayBetes no es un producto sanitario. Sus análisis y sus futuras recomendaciones son una herramienta de apoyo y no sustituyen el criterio del equipo médico.

---

## 3. Fases del proyecto

| N.º | Fase | Periodo | Estado |
|---|---|---|---|
| 0 | Prototipo | dic. 2025 – verano 2026 | Completada: biblioteca de alimentos, comidas, escáner y cuentas |
| 1 | Estabilización | sept. – oct. 2026 | Completada en su mayor parte: convenciones y auditoría tabla a tabla |
| 2 | Puesta en producción | oct. 2026 | Completada: servidor propio, despliegue automático y copias cifradas |
| 3 | Diseño del estudio | oct. 2026 – inicio de 2027 | En curso: variables, pautas de registro, métricas y plan de análisis |
| 4 | Adaptación de la app al estudio | nov. 2026 – inicio de 2027 | En curso: lo que el estudio necesita y la app aún no recoge |
| 5 | Piloto | dos semanas | Planificada |
| 6 | Recogida de datos | unas doce semanas, primavera de 2027 | Planificada |
| 7 | Análisis y memoria | tras la recogida | Planificada |
| 8 | Apertura a otros usuarios | después del TFG | Condicionada a los resultados |

---

## 4. Estado actual

La aplicación está **en producción** y se usa a diario desde el móvil y el ordenador. Es de acceso privado y el registro de usuarios está cerrado. La interfaz está en inglés.

| Área | Estado |
|---|---|
| Alimentos, recetas y platos preparados por otros, con origen de los macros | ✅ Construido |
| Comidas por platos: planificar, ajustar, confirmar lo comido de cada plato | ✅ Construido |
| Método de cada cantidad, confianza y cobertura de los macros | ✅ Construido |
| Fracción comida de cada plato, guardada al confirmar | ✅ Construido |
| Insulina: inyecciones con dosis, hora, zona y boli; historial de cambios | ✅ Construido |
| Bolis de insulina: apertura, caducidad y lo que queda | ✅ Construido |
| Nevera y congelador: sobras reutilizables con su origen | ✅ Construido |
| Escáner de código de barras, Open Food Facts y Ciqual | ✅ Construido |
| Rescate de hipoglucemias y registro durante el ejercicio | ✅ Construido |
| Asistente DiaBot (texto y fotos) | 🟡 Funcional, en fase preliminar |
| Estadísticas | 🟡 Versión básica, por pulir |
| Campos del estudio (objetivo del bolo, hora de fin, diario, periodos, contexto…) | ⏳ En definición (fase 4) |
| Versionado de los alimentos | ⏳ Diseñado, sin construir |
| Glucosa y Apple Health | ⏳ Se cruzan en el análisis del TFG, fuera de la app |
| Modelo predictivo y recomendaciones | ⏳ Fase 2 |

En cifras: unas 39 000 líneas de Python y 4 100 de JavaScript; 25 tablas; 136 rutas; 64 pruebas automáticas de la lógica de dominio; seis documentos de convenciones versionados más el protocolo del estudio; y 86 decisiones de arquitectura registradas.

---

## 5. Funcionalidades

La interfaz se organiza en cuatro secciones, accesibles desde una barra de navegación flotante (**Menu, Stats, Food, Settings**), más un **carrito** siempre accesible con las comidas en curso y el asistente **DiaBot**.

### 5.1 Alimentos (Food)

- **Biblioteca personal** con tres tipos de entrada: alimentos con sus valores por 100 g, **recetas** que combinan ingredientes por platos, y **platos preparados por otros** (un bar, un familiar).
- **Origen de los macros** de cada alimento: etiqueta, web oficial, Open Food Facts, tabla de composición, calculado de sus ingredientes, estimación de la IA o propia.
- **Búsqueda en tiempo real**, filtros, favoritos y etiquetas.
- **Smart macros**: se escribe `120kcal 30hc 12az 20prot` y se rellenan los campos, con una gramática estricta que rechaza lo que no entiende en vez de adivinar.
- **Escáner de código de barras** contra una copia local de **Open Food Facts** y, si no está, su API. **Alimentos genéricos de Ciqual**, la tabla de composición de la agencia francesa de seguridad alimentaria.
- **Rescate**: registro rápido de lo que se toma para tratar una bajada o haciendo deporte.

### 5.2 Comidas y carrito

Cada comida se **planifica**, se ajusta y se **confirma**. Dentro de ella:

- **Platos (tandas)** servidos en momentos distintos, cada uno con su desfase o su hora exacta.
- **Porciones** con su cantidad, **cómo se obtuvo** (báscula de cocina o de mano, peso del envase, medida casera, a ojo, estimación de la IA), cocción, conservación, estado final, madurez en la fruta y si se pesó ya cocinado.
- **Datos de la comida**: tipo (propuesto según el horario), hora, si se comió fuera, notas y el borrador de la insulina (dosis, zona y boli).
- **Confirmación**: se indica cuánto se comió de cada plato, en % o en gramos. La fracción se **guarda** para recuperar después lo servido (con lo que se decidió la dosis) y saber qué platos no se acabaron. Lo que sobra se puede guardar en la nevera.
- **Nevera y congelador**: tuppers con su contenido, su fecha y sus movimientos, que se usan en comidas posteriores sin perder de dónde venían.

### 5.3 Confianza y cobertura

Para cada comida se calculan, entre 0 y 1 y ponderadas por la cantidad de cada ingrediente:

- la **confianza en la cantidad** (`amount_confidence`): la parte del peso medida con báscula o con el peso del envase; se guarda al confirmar;
- la **confianza en la calidad** (`quality_confidence`): la parte del peso cuyos macros son publicados por quien hace o vende el producto;
- la **cobertura de cada nutriente**: qué parte de lo comido tiene ese nutriente informado. Un valor que falta es desconocido, nunca cero.

Las reglas exactas están en [`measurement_conventions.md`](conventions/measurement_conventions.md) §6.

### 5.4 Asistente DiaBot

El usuario escribe lo que ha comido, o adjunta hasta cuatro fotos, y DiaBot lo deja en el carrito para revisarlo. Busca primero entre los alimentos del usuario, después en Ciqual y Open Food Facts, y solo estima cuando no encuentra nada, marcándolo como estimación de la IA. También lee etiquetas nutricionales y prepara borradores de alimentos, platos y recetas, que el usuario revisa en el formulario antes de guardar.

Sus límites son estructurales, no instrucciones del prompt: tiene un conjunto fijo de herramientas y **ninguna borra, confirma comidas, edita la biblioteca ni calcula dosis**. La insulina de la comida solo la anota cuando el usuario la indica expresamente. Cada conversación se guarda para medir sus errores; las fotos no se guardan. Usa la API de Claude (por defecto, Claude Haiku con esfuerzo alto), con un tiempo máximo por mensaje por debajo del de Cloudflare.

### 5.5 Insulina, ajustes y estadísticas

- **Inyecciones** rápidas y basales con dosis, hora, zona y boli. Cada cambio o borrado guarda la versión anterior.
- **Bolis**: marcas, apertura, caducidad, capacidad y motivo de retirada.
- **Ajustes**: horario de los tipos de comida, etiquetas, bolis e inyecciones.
- **Estadísticas**: totales y promedios diarios de macronutrientes y su reparto por tipo de comida.

---

## 6. Modelo de datos

PostgreSQL 17, con **25 tablas**. Las restricciones de integridad, los valores de los enumerados (generados desde el código) y la propiedad de cada fila se garantizan **también en SQL**, no solo en la aplicación.

| Grupo | Tablas | Para qué |
|---|---|---|
| Usuarios y seguridad | `users`, `auth_sessions`, `auth_rate_limits` | Cuentas, sesiones revocables y límite de intentos |
| Alimentos | `catalog`, `manual_intake`, `recipe`, `recipe_plate`, `food_brands` | Alimentos, platos preparados, recetas con sus platos y marcas |
| Referencia | `off_product`, `ciqual_food` | Copias de Open Food Facts y Ciqual, de solo lectura para la app |
| Comidas | `intake_event`, `intake_plate`, `portion_detail`, `meal_type_schedule` | Comidas, sus platos, sus porciones y el horario de los tipos de comida |
| Sobras | `fridge`, `fridge_move` | Tuppers y su historial de movimientos (solo inserción) |
| Insulina | `insulin_injections`, `insulin_injection_history`, `insulin_brand`, `insulin_pen` | Inyecciones, su historial de cambios, marcas y bolis |
| Organización | `tags`, `linked_tags`, `user_favorites` | Etiquetas y favoritos |
| Asistente | `assistant_conversation`, `assistant_message` | Conversaciones con DiaBot (solo inserción) |

`portion_detail` usa un **patrón de arco**: cada porción tiene un único origen (alimento o plato preparado) y un único destino (una comida, una receta o un tupper). Cada instante se guarda en UTC con la **zona horaria del navegador** en la que se registró.

---

## 7. Arquitectura técnica

### 7.1 Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Web | [FastHTML](https://fastht.ml) 0.14 sobre Starlette 1.x y Uvicorn |
| Interactividad | HTMX 2, con JavaScript propio y mínimo en `static/js/` |
| Estilos | Tailwind CSS 4. El CSS se compila en desarrollo y se versiona |
| Base de datos | PostgreSQL 17 con `psycopg` 3 y un pool de conexiones (SQL explícito, sin ORM) |
| Seguridad | Argon2 con pepper, sesiones en base de datos, CSRF, límite de intentos, CSP |
| Datos externos | Open Food Facts, Ciqual, API de Claude (asistente) |
| Contenedores | Docker y Docker Compose, imágenes fijadas por digest |
| Infraestructura | VPS de OVH en la UE, Cloudflare (DNS, Tunnel, R2), GitHub Actions |

### 7.2 Estructura del código

```
DayBetes_food/
├── main.py              # Arranque, middleware de seguridad y gestión de errores
├── config.py            # Toda la configuración, cargada y validada al arrancar
├── auth/                # Autenticación, sesiones, contraseñas y CSRF
├── domain/              # Reglas de negocio puras: enumerados, dataclasses, nutrición y confianza
├── services/            # Operaciones de varios pasos: comidas, recetas, nevera, bolis, asistente
├── database/
│   ├── schema.py        # Definición del esquema
│   ├── db_init.py       # Orquesta el bootstrap del esquema
│   ├── bootstrap/       # Pasos idempotentes del esquema, por área
│   └── queries/         # SQL, un módulo por tabla
├── integrations/        # Adaptadores externos: Open Food Facts, Ciqual, Claude
├── routes/              # Endpoints; los de Food, en routes/food/ por área
├── components/          # Interfaz: funciones Python que devuelven HTML, sin acceso a la base
└── static/              # CSS compilado, JavaScript e imágenes
tests/                   # Pruebas automáticas de la lógica de domain/
```

### 7.3 Principios de diseño

- **HTML desde el servidor.** HTMX actualiza solo la parte de la página que cambia. Apenas hay estado en el navegador.
- **Capas con responsabilidades claras.** Las rutas validan y autorizan; los servicios coordinan; `domain/` es lógica pura; `queries/` contiene el SQL; los componentes solo pintan lo que la ruta les pasa.
- **Dos identidades de base de datos.** La app trabaja con un rol sin permisos para modificar el esquema; el esquema lo cambia una identidad de migraciones que nunca se usa en ejecución.
- **La propiedad de los datos se comprueba en SQL.** Cada consulta filtra por usuario dentro del propio SQL.
- **Historiales que la app no puede reescribir.** Los movimientos de la nevera, los mensajes del asistente y el historial de inyecciones son de solo inserción, también por permisos.
- **Errores tipados y uniformes**, con códigos HTTP con significado y mensajes que no revelan información interna.

### 7.4 Datos de terceros

DayBetes usa datos de [Open Food Facts](https://world.openfoodfacts.org) bajo la [Open Database License](https://opendatacommons.org/licenses/odbl/1-0/) (contenidos bajo la [Database Contents License](https://opendatacommons.org/licenses/dbcl/1-0/)) y de [Ciqual](https://ciqual.anses.fr) (ANSES). Son datos orientativos, sin garantía de exactitud; el detalle está en [`measurement_conventions.md`](conventions/measurement_conventions.md) §12.

---

## 8. Despliegue y operación

En producción en **[daybetes.com](https://daybetes.com)** desde octubre de 2026.

### 8.1 Cómo llega una visita

```
Navegador ──HTTPS──▶ Cloudflare ──Tunnel (conexión saliente)──▶ VPS
                                                                  │
                                              ┌─── Docker Compose ┴─────────────┐
                                              │ tunnel ─▶ web (FastHTML) ─▶ db │
                                              └─────────────────────────────────┘
```

- **El servidor no tiene ningún puerto web abierto.** `cloudflared` abre una conexión saliente y las visitas entran por ella; el firewall solo deja pasar SSH.
- **Acceso privado.** El registro está cerrado en producción y la autenticación de la app es la barrera. Cloudflare Access se estudiará más adelante.
- La app corre en el contenedor con un **usuario sin privilegios** y envía cabeceras de seguridad, incluida una `Content-Security-Policy`.

### 8.2 Servidor

VPS de OVH en la UE, con Ubuntu 26.04 LTS: SSH solo con clave y sin root, firewall cerrado salvo SSH, parches de seguridad automáticos, swap de reserva y logs de contenedores limitados.

### 8.3 Despliegue continuo

Producción ejecuta siempre `main`, protegida: solo admite cambios por Pull Request.

```
rama ─▶ Pull Request ─▶ pip-audit + pruebas ─▶ merge en main ─▶ GitHub Actions
                                                                   │  (SSH con clave dedicada y comando forzado)
                                                                   ▼
                          VPS: git ─▶ migraciones ─▶ build + up ─▶ comprobación de salud ─▶ vuelta atrás si falla
```

- Las **migraciones** se ejecutan en un contenedor de un solo uso **antes** de sustituir la app.
- Si la versión nueva no responde, el despliegue **vuelve a la imagen y al código anteriores** y termina en error.
- Las dependencias, transitivas incluidas, están **bloqueadas con hashes**; `pip-audit` las revisa en cada PR y Dependabot propone sus actualizaciones.
- El usuario de despliegue no tiene terminal: su clave solo puede lanzar el script de despliegue.

### 8.4 Copias de seguridad

- Volcado nocturno de la base, **cifrado con `age` en el propio servidor** (que solo tiene la clave pública).
- Copias en Cloudflare R2, jurisdicción UE, durante 90 días, y localmente durante 7 días.
- Un vigilante externo avisa si una copia falla **o si no llega a ejecutarse**, y la restauración se prueba cada mes.

El detalle está en [`infra_conventions.md`](conventions/infra_conventions.md).

---

## 9. Cómo se desarrolla

### 9.1 Desarrollo guiado por convenciones

Todas las decisiones de diseño están escritas en [`conventions/`](conventions/) y el código se escribe siguiéndolas. Cuando aparece una decisión nueva no cubierta, se para hasta acordarla y documentarla; las relevantes se registran con su contexto, alternativas y motivo. El código, en inglés; la documentación, en español.

### 9.2 Auditorías

El código se revisa **tabla a tabla** contra las convenciones (esquema, restricciones, consultas, rutas e interfaz), con agentes de [Claude Code](https://claude.com/claude-code) definidos en [`.claude/agents/`](.claude/agents/). En noviembre de 2026 se hizo además una auditoría general del proyecto, cuyos hallazgos se han ido cerrando.

### 9.3 Pruebas

Un conjunto mínimo de pruebas automáticas (`tests/`, con `pytest`) cubre la lógica de la que depende el estudio: cantidades y unidades, factor de cocción, fracción comida, confianza y cobertura, smart macros, hora exacta, zona horaria e historial del asistente. Se ejecutan en cada Pull Request y bloquean el despliegue si fallan. El resto se verifica a mano.

### 9.4 Flujo de trabajo

[GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow) con commits en formato [Conventional Commits](https://www.conventionalcommits.org) (`feat`, `fix`, `refactor`, `docs`…).

---

## 10. Desarrollo local

Requisitos: Docker (o Docker Desktop).

```sh
git clone https://github.com/Pablolucasmora/diabetes-management-system.git
cd diabetes-management-system
cp .env.example .env        # rellenar los valores (no se suben nunca a git)
docker compose up -d        # base de datos, app con recarga automática y Tailwind en modo watch
```

La app queda en `http://localhost:8000`, solo accesible desde el propio equipo (para probar desde el móvil: `WEB_BIND_ADDRESS=0.0.0.0 docker compose up -d`). En desarrollo el registro está abierto y el esquema se crea solo al arrancar.

Las pruebas:

```sh
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c "pip install -q --require-hashes -r requirements.txt && pip install -q -r requirements-dev.txt && python -m pytest"
```

Desarrollo y producción usan **archivos de Compose separados** y **volúmenes distintos**. Los comandos de producción se ejecutan siempre con `./scripts/prod.sh`.

---

## 11. Hoja de ruta

**Antes del piloto (fases 3 y 4)**
- Cerrar el protocolo: preguntas, variables, pautas de registro, reglas de calidad y métricas.
- Añadir los campos del estudio: objetivo del bolo y "qué tuve en cuenta", hora de fin de la comida, comida sin detalle, estimaciones previas al pesado.
- Registros de contexto: diario del día, periodos especiales, eventos, peso, medicación, cambios de sensor.
- Importación de las dosis del boli con memoria.
- Versionado de los alimentos e historial formal de migraciones.
- Pulir DiaBot y las estadísticas.

**TFG**
- Piloto de dos semanas, recogida de unas doce semanas y análisis, cruzando la glucosa de LibreView y los datos de Apple Health fuera de la app.
- Memoria con los resultados del análisis personal.

**Después del TFG (condicionado a los resultados)**
- Requisitos para abrir a otras personas: protección de datos, consentimiento, encaje regulatorio, seguridad reforzada (límites de uso del asistente, Cloudflare Access o WAF) y validación clínica.
- Modelo predictivo personalizado, avisos e integración directa de Apple Health.

---

## 12. Documentación del proyecto

| Documento | Contenido |
|---|---|
| [`code_conventions.md`](conventions/code_conventions.md) | Capas, transacciones, tipado, seguridad, configuración, asistente y esquema |
| [`measurement_conventions.md`](conventions/measurement_conventions.md) | Unidades, cantidades, porciones, platos, nevera, confianza, insulina y tiempo |
| [`error_conventions.md`](conventions/error_conventions.md) | Tipos de error, códigos HTTP, mensajes y registros |
| [`frontend_conventions.md`](conventions/frontend_conventions.md) | Componentes, HTMX, páginas e idioma |
| [`infra_conventions.md`](conventions/infra_conventions.md) | Entornos, despliegue, servidor, copias de seguridad y dependencias |
| [`decisions.md`](conventions/decisions.md) | Registro histórico de decisiones de arquitectura |
| `study_conventions.md` | Protocolo del estudio (privado, fuera de git) |
