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
- Las credenciales del túnel (`<id>.json`) nunca se suben a git; se copian al servidor por un canal seguro (`scp`). El archivo de configuración `cloudflared/daybetes.yml` sí está en git porque no contiene secretos.
- En el servidor, la credencial vive en `/etc/cloudflared/<id>.json`, fuera del repositorio (no puede subirse a git ni entrar en la imagen por `COPY . .`), y `docker-compose.prod.yml` monta esa ruta fija: `~` no se usa porque depende del usuario que ejecute el comando (con `sudo` es `/root`). El archivo pertenece al UID `65532` (usuario `nonroot` de la imagen de `cloudflared`) con permisos `400`: dentro y fuera del contenedor los usuarios se identifican por número.
- Al servidor solo va la credencial del túnel. `cert.pem` (certificado de la cuenta de Cloudflare, que permite crear y borrar túneles y cambiar el DNS) nunca sale del equipo del desarrollador.
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
| Datos de Postgres | Volumen con nombre `pgdata_dev` | Volumen con nombre `pgdata_prod` |

## 6. Datos persistentes

- Los datos de Postgres viven en **volúmenes con nombre de Docker**, uno distinto por entorno: `pgdata_dev` en `docker-compose.yml` y `pgdata_prod` en `docker-compose.prod.yml`. Ningún volumen de datos se comparte entre entornos.
- No se montan carpetas del proyecto (`./pgdata` o similares) como directorio de datos de Postgres.
- Motivos (incidente del 2026-10-01): dos Postgres arrancados a la vez sobre la misma carpeta de datos la corrompieron, porque el bloqueo de Postgres (`postmaster.pid`) no protege entre contenedores distintos; además, la carpeta del proyecto está en `Documents`, sincronizada con iCloud, y la sincronización de una base de datos en marcha también puede corromperla. Con un volumen por entorno, los dos entornos no pueden compartir datos aunque se arranquen a la vez, y los datos quedan fuera de cualquier carpeta sincronizada.
- Un volumen vacío **no se inicializa dejando que el contenedor de Postgres lo haga con las variables del `.env`**: `POSTGRES_USER` se convertiría en superusuario del clúster y `DB_USER` es el rol de runtime, lo que rompe la separación de identidades de `code_conventions.md` §12.6. Se inicializa explícitamente con el rol propietario (`plucmor`) como superusuario y después se restauran roles (`pg_dumpall --roles-only`) y datos (`pg_dump`/`pg_restore`).
- Los datos se sacan y se meten en un volumen solo con `pg_dump`/`pg_restore`, nunca copiando sus archivos.

## 7. Archivos de entorno

- Cada entorno tiene su propio archivo de variables: `.env` para desarrollo y `.env.prod` para producción. `docker-compose.prod.yml` carga `.env.prod` con `env_file:` solo en los servicios que lo necesitan (mínimo privilegio: `db` y `tunnel` no reciben secretos de la app).
- Ninguno de los dos se sube a git ni entra en la imagen: ambos figuran en `.gitignore` y en `.dockerignore`. Esos patrones excluyen solo el nombre exacto, así que un archivo de entorno nuevo se añade explícitamente a los dos.
- `.env.example` sí se versiona: contiene el nombre de todas las variables y ningún valor real. Se actualiza en el mismo cambio que añade o elimina una variable.
- `APP_ENV=production` solo cambia los valores **por defecto** de `config.py`; un valor escrito en el archivo de entorno gana siempre. Por eso `.env.prod` no se crea copiando `.env`: los valores de desarrollo (`SESSION_COOKIE_SECURE=false`, `DEFAULT_USER_PASSWORD` con valor...) se revisan uno a uno.
- En producción `DEFAULT_USER_PASSWORD` queda vacío, para que el bootstrap no cree el usuario por defecto.
- El registro de usuarios (`REGISTRATION_ENABLED`) está abierto por defecto en desarrollo y cerrado por defecto en producción. Cerrado, sus rutas no se registran y responden `404`, igual que cualquier URL inexistente. Abrirlo en producción es una acción puntual (dar de alta a alguien) que se revierte después.
- `PASSWORD_PEPPER` no se cambia una vez existen usuarios: forma parte de cada hash de contraseña y cambiarlo impide todos los inicios de sesión.
- En el VPS, "el mecanismo de secretos del entorno de despliegue" de `code_conventions.md` §8.2 es `.env.prod`: fuera de git y de la imagen, copiado al servidor por un canal seguro (`scp`) y con permisos de lectura solo para su propietario (`chmod 600`).

## 8. Comandos de producción

- Todo comando de Compose sobre producción se ejecuta con `./scripts/prod.sh <subcomando>` (p. ej. `./scripts/prod.sh up -d --build`, `./scripts/prod.sh logs web`), nunca con `docker compose -f docker-compose.prod.yml` directamente.
- Motivo: Compose rellena los `${...}` del YAML con el archivo `.env` salvo que se indique `--env-file`. Sin él, producción arrancaría en silencio con valores de desarrollo (comprobado: `APP_ENV` resolvía a `development`), porque `environment:` gana sobre `env_file:`.
- `scripts/prod.sh` se sitúa en la raíz del repositorio, se niega a ejecutarse si no existe `.env.prod` y pasa el resto de argumentos a `docker compose --env-file .env.prod -f docker-compose.prod.yml`.
- El primer `up` sobre un volumen `pgdata_prod` vacío no se hace sin inicializarlo antes según §6.

## 9. IP del cliente

- La IP del cliente (clave del rate limiting y `ip_hash` de la sesión) se obtiene en un único punto del código; ninguna ruta lee cabeceras de IP por su cuenta.
- `X-Forwarded-For` no se usa nunca: el cliente puede escribir en ella lo que quiera y Cloudflare añade la IP real al final sin borrar lo anterior, de modo que sus primeros valores son falsificables (comprobado: 7 intentos fallidos con 7 valores distintos crearon 7 claves de rate limiting y ninguna se bloqueó).
- Con `TRUST_CF_CONNECTING_IP` activo (por defecto en `production`) se usa `CF-Connecting-IP`, que Cloudflare sobrescribe siempre. Solo es fiable porque la única entrada a `web` es el túnel (§3): publicar un puerto de `web` exige desactivar este ajuste en el mismo cambio.
- Con el ajuste inactivo (por defecto en `development` y `test`) se usa la IP de la conexión directa (`request.client.host`).
- Si la cabecera falta o no es una IP válida, se usa la IP de la conexión directa; nunca se descarta la petición por ello.
- La IP se normaliza antes de usarla: IPv4 tal cual; IPv6 agrupada por su prefijo `/64` (un cliente IPv6 suele disponer de todo un `/64` y podría cambiar de dirección en cada intento); una IPv6 que encapsula una IPv4 (`::ffff:a.b.c.d`) se trata como esa IPv4.

## 10. Dependencias

- `requirements.txt` fija versiones exactas (`==`) de todas las dependencias directas, para que desarrollo, la imagen de producción y cualquier reconstrucción instalen exactamente lo mismo.
- Antes de cada despliegue se pasa `pip-audit -r requirements.txt`. Con vulnerabilidades conocidas no se despliega: se actualiza la dependencia afectada o se documenta por qué no aplica al proyecto. En la fase de despliegue automático, este paso lo ejecuta la GitHub Action y bloquea el despliegue si falla.
- Cada actualización de dependencias va en su propio commit, junto con las adaptaciones de código que exija y sin mezclarla con otros cambios.
- Una actualización se prueba arrancando la app en desarrollo con la imagen reconstruida (`docker compose up -d --build web`), no solo instalando el paquete: las dependencias viven en la imagen, no en el código montado.
- Los avisos de obsolescencia (`DeprecationWarning`) de las dependencias se tratan como deuda: anuncian que la siguiente versión mayor romperá ese código (caso real: `@app.middleware` y `on_event`, eliminados en Starlette 1.0).

## 11. Servidor de producción

- VPS OVH VPS-1 (Gravelines, Francia) con Ubuntu 26.04 LTS, sin imágenes con aplicaciones preinstaladas.
- **Usuarios**: se trabaja con el usuario `pablo`, del grupo `sudo`, y `sudo` exige contraseña. El usuario `ubuntu` de la imagen y su regla de `sudo` sin contraseña (`/etc/sudoers.d/90-cloud-init-users`) se eliminan.
- **SSH**: solo con clave (`ed25519`, protegida con frase). La configuración propia vive en `/etc/ssh/sshd_config.d/00-daybetes.conf` (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no`, `AllowUsers pablo`). El prefijo `00-` es obligatorio: `sshd` se queda con el primer valor que lee y los archivos de `sshd_config.d/` se leen en orden alfabético, así que un `50-cloud-init.conf` con `PasswordAuthentication yes` ganaría a cualquier archivo posterior. Puerto 22, sin cambiar. Un usuario nuevo con acceso SSH (p. ej. el de despliegue) se añade a `AllowUsers`.
- Todo cambio en la configuración de SSH se valida con `sudo sshd -t` antes de aplicarlo y se prueba con una conexión nueva manteniendo otra sesión abierta.
- **Firewall**: `ufw` con entrada denegada por defecto, salida permitida y solo `OpenSSH` (22/tcp) permitido, sin `limit`. La aplicación no necesita puertos de entrada: el túnel es una conexión saliente.
- **Actualizaciones**: `unattended-upgrades` instala a diario los parches de seguridad de Ubuntu y reinicia automáticamente a las 05:00 solo cuando un parche lo exige. La configuración propia vive en `/etc/apt/apt.conf.d/52unattended-upgrades-daybetes`; en `apt`, al contrario que en `sshd`, gana el último archivo leído. La zona horaria del sistema es `Europe/Madrid`.
- **Docker**: se instala desde el repositorio oficial de Docker (clave de firma con huella `9DC858229FC7DD38854AE2D88D81803C0EBFCD88`). No entra en `unattended-upgrades`, porque actualizarlo reinicia todos los contenedores: se actualiza a mano con `apt`, tras comprobar las notas de la versión.
- Docker se usa con `sudo`. `pablo` no pertenece al grupo `docker`: ese grupo equivale a ser root sin contraseña.
- Los logs de los contenedores se limitan en `/etc/docker/daemon.json` (`json-file`, `max-size` 10m, `max-file` 3), para que no puedan llenar el disco.

## 12. Copias de seguridad

- El backup automático de OVH (imagen diaria del disco) no cuenta como copia de la base de datos: vive en el mismo proveedor que el servidor, solo permite restaurar el servidor entero y copia los archivos de un Postgres en marcha.
- La copia de la base de datos de producción es un `pg_dump -Fc` de los datos y un `pg_dumpall --roles-only` de los roles, cada noche a las 03:30, con `scripts/backup.sh`.
- Las copias se cifran con `age` antes de salir de Postgres. El servidor solo tiene la clave **pública**, así que puede cifrar pero no descifrar. La clave privada vive únicamente en el gestor de contraseñas del desarrollador: sin ella ninguna copia se puede restaurar.
- Destino fuera del servidor: bucket `daybetes-backups` de Cloudflare R2, con jurisdicción UE (datos de salud), que borra los objetos a los 90 días mediante una regla de ciclo de vida. El token de R2 solo tiene permiso *Object Read & Write* sobre ese bucket. Las últimas 7 copias se conservan además en `/var/backups/daybetes` para restaurar sin depender de R2.
- El script falla si cualquier paso falla (`set -euo pipefail`), escribe en `.tmp` y renombra al terminar, y no sube nada si el volcado falla: nunca se guarda una copia vacía o a medias con nombre de copia válida.
- Vigilancia: el script avisa a Healthchecks.io al empezar y con su código de salida al terminar. Healthchecks envía un email si una copia falla **o si no llega ninguna señal** en el plazo previsto (interruptor de hombre muerto).
- Ejecución: timer de systemd (`deploy/systemd/daybetes-backup.timer`, `Persistent=true`) que lanza `daybetes-backup.service` como root con la configuración de `/etc/daybetes/backup.env` (root, `chmod 600`, plantilla en `deploy/backup.env.example`).
- Root nunca ejecuta un archivo que pueda modificar un usuario sin privilegios. El script se instala como copia propiedad de root (`sudo install -m 755 scripts/backup.sh /usr/local/sbin/daybetes-backup`) y no se ejecuta desde `/opt/daybetes`. Un cambio en `scripts/backup.sh` o en `deploy/systemd/` no tiene efecto hasta que se reinstala en el servidor.
- `deploy/` contiene los archivos de configuración del servidor que se versionan (unidades de systemd, plantillas): se copian o instalan en el VPS, no se ejecutan desde el repositorio.
- Una copia que nunca se ha restaurado no cuenta como copia. Se hace una prueba de restauración completa al ponerlas en marcha y después **una vez al mes**: descargar de R2 la copia más reciente, descifrarla y restaurarla en un Postgres desechable en el Mac, comparar el recuento de filas por tabla con producción y borrar después la copia descifrada.
