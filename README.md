# Postulare — Backend

API REST del proyecto **Postulare**: seguimiento de candidaturas de empleo con
búsqueda y scoring automático de ofertas afines a tu perfil.

Stack: **Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL · JWT**.

> Frontend (Angular 18) en un repositorio hermano: [postulare-frontend](https://github.com/costanna/postulare-frontend).

## Estado del proyecto

Este backend se construye de forma incremental, en ramas por funcionalidad:

- [x] `feature/backend-bootstrap` — estructura del proyecto, modelo de datos, migración inicial de Alembic, autenticación JWT (registro, login, refresh, recuperación de contraseña) con tests
- [x] `feature/profile-applications-events` — perfil de usuario, CRUD de candidaturas (con filtros y paginación) y eventos/timeline, con tests
- [x] `feature/matching` — cliente Adzuna, scoring nivel 1 (keywords), endpoints de matches (buscar/listar/convertir/descartar), con tests simulados
- [x] `feature/stats` — estadísticas del dashboard (resumen, por estado, evolución mensual, por origen), con tests
- [x] Docker Compose (backend + PostgreSQL); el frontend ya tiene su propio `Dockerfile` y ambos se orquestan juntos desde el [`docker-compose.yml`](../docker-compose.yml) de la carpeta raíz

**Backend funcionalmente completo de extremo a extremo (MVP del prompt maestro, pasos 1-5)**, más un paquete de mejoras:

- **Cartas de presentación por oferta** (`POST /matches/{id}/cover-letter`): con IA (Claude) si hay clave y quedan cartas del día; si no, con una plantilla gratuita en es/ca/en. Siempre devuelve una carta.
- **Importar CV en PDF** (`POST /profile/import-cv`): propone puesto, ubicación, nivel, skills y resumen. El PDF se lee en memoria y se descarta; el usuario revisa la propuesta antes de guardarla.
- **Seguimientos** (`GET /applications/follow-ups`): candidaturas abiertas sin novedades desde hace `FOLLOW_UP_DAYS` días.
- **Exportar a CSV** (`GET /applications/export`).
- **Ofertas repetidas**: la búsqueda descarta reanuncios y ofertas que ya están en tus candidaturas; los matches indican `already_tracked`.
- **Prueba la demo** (`POST /auth/demo`): cuenta temporal con datos de ejemplo, sin registro (ver más abajo).

El scoring razonado con IA (nivel 2) sigue pendiente; hoy el scoring es por palabras clave.

## Puesta en marcha local

### Requisitos

- Python 3.12+
- PostgreSQL 16 (o Docker)

### 1. Clonar e instalar dependencias

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash) — en cmd: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
# Edita .env con tus valores (DATABASE_URL, SECRET_KEY, ADZUNA_APP_ID/KEY...)
```

### 3. Base de datos y migraciones

Con Docker (recomendado):

```bash
docker compose up -d db
alembic upgrade head
```

O contra un PostgreSQL local ya existente, ajustando `DATABASE_URL` en `.env`.

### 4. Arrancar la API

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Documentación interactiva (Swagger): http://localhost:8000/docs
- Documentación alternativa (ReDoc): http://localhost:8000/redoc

### Todo junto con Docker Compose

```bash
docker compose up --build
```

Levanta PostgreSQL y el backend (aplicando migraciones automáticamente al arrancar).

## Despliegue en Render

El servicio web se despliega en Render; la base de datos vive en
[Neon](https://neon.tech) (Postgres serverless, capa gratuita sin la
caducidad a los 90 días que tiene la de Render).

### 1. Base de datos en Neon

1. Crea una cuenta/proyecto en [neon.tech](https://neon.tech) (tiene capa gratuita).
2. En el dashboard del proyecto, copia la **cadena de conexión "directa"**
   (no la que pone "pooled"/"pgbouncer" — con un único servicio de Render
   corriendo de forma continua no hace falta el pooler, y evita problemas
   de PgBouncer en modo transacción con SQLAlchemy). Tiene esta forma:

   ```text
   postgresql://usuario:contraseña@ep-xxxx.eu-central-1.aws.neon.tech/postulare?sslmode=require
   ```

   El `?sslmode=require` es obligatorio — Neon no acepta conexiones sin TLS.
3. Guarda esa cadena: es el `DATABASE_URL` del paso 3.

### 2. Servicio web en Render

[`render.yaml`](render.yaml) es un [Blueprint de Render](https://render.com/docs/blueprint-spec):
describe el servicio web a partir del `Dockerfile`.

1. Sube este repositorio a GitHub (si no lo está ya).
2. En el dashboard de Render: **New +** → **Blueprint**, y selecciona el repo.
3. Render pide los valores marcados como "a rellenar" en `render.yaml`:
   - `DATABASE_URL`: la cadena de conexión de Neon del paso anterior
   - `CORS_ORIGINS` y `FRONTEND_URL`: la URL real del frontend en Vercel
     (sin barra final), p. ej. `https://postulare.vercel.app`
   - `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`: para que "Buscar ofertas" funcione
     (sin ellos, ese endpoint devuelve error 502; el resto de la app va sin problema)
4. `SECRET_KEY` se genera sola. El resto de variables (SMTP, etc.) son
   opcionales — ver [`.env.example`](.env.example).
5. Cada despliegue aplica las migraciones pendientes automáticamente
   (`docker-entrypoint.sh` corre `alembic upgrade head` antes de arrancar
   uvicorn) directamente contra Neon.

El health check de Render usa `GET /health`.

Railway es la alternativa mencionada en el README raíz: no necesita
`render.yaml` (detecta el `Dockerfile` solo), pero el mismo `DATABASE_URL`
de Neon y las mismas variables de entorno de arriba aplican igual.

## Proteger tu cuota de Adzuna (demo pública)

Cada "Buscar ofertas" real consume una llamada de tu cuota gratuita de
Adzuna. Si compartes la demo, la protegen cuatro capas, de la más fina a la
que no se puede rodear:

1. **Cooldown por usuario** (`MATCH_SEARCH_COOLDOWN_MINUTES`, 10 min).
2. **Caché de búsquedas idénticas** (`ADZUNA_CACHE_MINUTES`, 6 h): dos
   personas con el mismo perfil y filtros comparten una sola llamada real. Vive
   en memoria del proceso, así que se pierde cuando Render duerme el servicio.
3. **Límite por IP** en registro, login y recuperar contraseña
   (`REGISTER_LIMIT_PER_HOUR`, `LOGIN_LIMIT_PER_MINUTE`, ...). Evita que un
   script llene la base de datos de cuentas. La IP sale de `X-Forwarded-For`,
   que un atacante decidido puede falsear: por eso hay una cuarta capa.
4. **Tope diario global** (`ADZUNA_DAILY_LIMIT`, 50): cuenta las llamadas
   *reales* a Adzuna de todos los usuarios juntos (tabla `adzuna_usage`). Al
   alcanzarlo, "Buscar ofertas" responde `503` con `Retry-After` hasta el día
   siguiente (UTC) y el resto de la app sigue funcionando. Esta es la garantía:
   no depende de quién llame ni desde dónde. `0` = sin tope.

Ajusta el tope a la cuota real de tu plan de Adzuna. En Render, las variables
de un servicio ya creado no se actualizan solas desde `render.yaml`: cámbialas
en el dashboard (si no, se usan los valores por defecto de arriba).

## Cartas con IA: control del gasto

A diferencia de Adzuna, **cada carta generada con Claude cuesta dinero** (con
`claude-opus-5`, del orden de céntimos por carta; `claude-haiku-4-5` sale bastante
más barato; comprueba el precio vigente en la consola de Anthropic). Es opcional y se controla así:

- **Sin `ANTHROPIC_API_KEY` no se gasta nada**: la carta sale de una plantilla
  gratuita con los mismos datos del perfil y de la oferta.
- **Tope diario global** (`LLM_DAILY_LIMIT`, 20) y **por usuario**
  (`COVER_LETTER_DAILY_LIMIT_PER_USER`, 5), contados en la tabla `llm_usage`. Al
  agotarse, sigue saliendo la plantilla (nunca un error). Con los valores por
  defecto el gasto máximo diario son 20 cartas, una cifra conocida de antemano
  (unos pocos dólares como mucho, aunque alguien intente abusar).
- Si la API de IA falla, se devuelve la plantilla y **se devuelve la reserva** de
  los topes (no se cobra un intento fallido al usuario).
- Las cuentas demo **nunca** llaman a la IA.
- La descripción de la oferta es texto de un tercero: va delimitada y el prompt
  ordena no seguir instrucciones que contenga; al modelo solo se le pasan datos
  reales del perfil y se le prohíbe inventar experiencia.
- Una carta ya generada se guarda en el match y no se vuelve a pedir salvo que el
  usuario pulse "regenerar".

## Cuentas demo ("Prueba la demo")

`POST /auth/demo` crea al momento un usuario con datos de ejemplo ficticios (sin
pedir email ni contraseña) para que cualquiera pueda probar la app. No cuesta
nada ni se puede abusar: no puede buscar ofertas reales (403, no gasta Adzuna),
sus cartas usan siempre plantilla, caduca a las `DEMO_TTL_HOURS` horas (la sesión
deja de valer y las cuentas caducadas se borran, con sus datos, al crear la
siguiente demo), y hay un límite por IP (`DEMO_LIMIT_PER_HOUR`) y un tope global
de demos al día (`DEMO_ACCOUNTS_DAILY_LIMIT`).

## Tests

```bash
pytest
```

Los tests usan una base de datos SQLite en memoria (no tocan PostgreSQL ni Alembic),
por lo que no requieren infraestructura adicional.

## Estructura del proyecto

```
app/
├── main.py          # instancia de FastAPI, CORS, routers
├── core/            # configuración (.env) y seguridad (JWT, hashing)
├── db/              # engine, sesión, tipos de columna portables
├── models/          # modelos SQLAlchemy (users, applications, events, job_offers, matches)
├── schemas/         # esquemas Pydantic (request/response)
├── routers/         # endpoints agrupados por recurso
├── services/         # lógica de negocio (email, búsqueda de ofertas, scoring, estadísticas)
└── deps.py          # dependencias comunes (sesión de BD, usuario autenticado)
alembic/             # migraciones de base de datos
tests/                # tests con pytest
```

## Variables de entorno

Ver [`.env.example`](.env.example) para la lista completa y comentada. Nunca subas
un `.env` real al repositorio — ya está en `.gitignore`.

## Seguridad

- Contraseñas con `bcrypt` (nunca en texto plano)
- JWT de acceso de corta duración (15 min) + refresh token (7 días)
- Todo endpoint de candidaturas, eventos y matches filtra siempre por el `user_id`
  del token — un usuario nunca puede ver ni modificar datos de otro
- CORS restringido a los orígenes definidos en `CORS_ORIGINS`
