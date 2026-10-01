# Convenciones de infraestructura - DayBetes

Este documento define cómo se organizan los contenedores, los entornos y la exposición de la aplicación a internet, para que desarrollo y producción no se mezclen y el servidor público no exponga más de lo necesario.

Este documento complementa `conventions/code_conventions.md` §8 (configuración y entornos).

## 1. Entornos y archivos de Compose

- Desarrollo y producción son entornos separados: desarrollo es el Mac del desarrollador; producción es el VPS. La aplicación que se usa de verdad (y sus datos reales) vive solo en producción.
- Cada entorno tiene **su propio archivo de Compose completo e independiente**:
  - `docker-compose.yml` — desarrollo.
  - `docker-compose.prod.yml` — producción.
- No se usan archivos base + override ni perfiles para derivar un entorno del otro. Un archivo se lee solo y lo que dice es exactamente lo que se ejecuta. Motivo: en Compose, las listas como `ports:` se **suman** entre archivos combinados, de modo que un puerto añadido a un archivo base llegaría a producción sin que `docker-compose.prod.yml` pudiera quitarlo.
- La repetición entre los dos archivos (por ejemplo, el servicio `db`) se acepta. Un cambio que afecte a ambos entornos (versión de Postgres, variables nuevas) se aplica en los dos archivos en el mismo cambio.

## 2. Comunicación entre servicios

- Todos los servicios de un entorno viven en el mismo proyecto de Compose y se comunican por la red interna que Compose crea, usando `nombre_de_servicio:puerto` (p. ej. `db:5432`, `web:8000`).
- No se usa `host.docker.internal` ni `extra_hosts` para que un contenedor llegue a otro: si dos servicios necesitan hablarse, van en el mismo archivo de Compose.

## 3. Exposición a internet (producción)

- En `docker-compose.prod.yml` **ningún servicio publica puertos** (`ports:`). Motivo: en Linux, un puerto publicado por Docker se salta las reglas de `ufw`, de modo que el firewall del servidor no lo protege.
- El único camino de entrada a la aplicación es Cloudflare Tunnel: el servicio `tunnel` abre una conexión saliente hacia Cloudflare y entrega las peticiones a `web:8000` por la red interna.
- Si en algún momento hace falta acceder a un servicio desde el propio servidor (p. ej. Postgres para mantenimiento por SSH), se publica ligado a `127.0.0.1` (`"127.0.0.1:5432:5432"`), nunca en todas las interfaces, y se documenta el motivo.

## 4. Cloudflare Tunnel

- El túnel `daybetes` y sus credenciales pertenecen a producción. El servicio `tunnel` existe solo en `docker-compose.prod.yml`.
- Desarrollo nunca arranca ese túnel: dos máquinas con las mismas credenciales se tratan como réplicas y Cloudflare repartiría las visitas reales entre el VPS y el portátil.
- Las credenciales del túnel (`~/.cloudflared/<id>.json`) nunca se suben a git; se copian al servidor por un canal seguro (`scp`). El archivo de configuración `cloudflared/daybetes.yml` sí está en git porque no contiene secretos.
- Para probar el entorno de desarrollo desde el móvil se usa la red local (`http://<nombre-del-mac>.local:8000`). Si se necesita acceso remoto al entorno de desarrollo, se decide aparte (red privada o túnel propio de desarrollo con credenciales distintas), nunca reutilizando el túnel de producción.

## 5. Diferencias obligatorias entre entornos

| Aspecto | Desarrollo (`docker-compose.yml`) | Producción (`docker-compose.prod.yml`) |
|---|---|---|
| `ports:` | Permitido, para acceder desde el Mac | Prohibido (§3) |
| Código | Montado con `.:/app` y `--reload` | Copiado dentro de la imagen; sin montaje de código ni `--reload` |
| `restart:` | Opcional | Obligatorio en todos los servicios (`unless-stopped` o `always`) |
| Tailwind `--watch` | Sí | No; `output.css` está versionado en git |
| Túnel | No (§4) | Sí |
| `APP_ENV` | `development` | `production` |
