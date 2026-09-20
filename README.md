# Postulare — Backend

🇪🇸 Español · [🇬🇧 English](README.en.md)

API REST de **Postulare**, una aplicación para organizar tu búsqueda de empleo: guarda tus candidaturas, encuentra ofertas afines a tu perfil, puntúa cada una según lo bien que encaja contigo y te ayuda a escribir la carta de presentación.

- 🌐 Demo en vivo: <https://postulare.vercel.app> (pulsa **«Prueba la demo»**, no hace falta registrarse)
- 📖 Documentación interactiva de la API (Swagger): <https://postulare-backend.onrender.com/docs>
- 🖥️ Frontend (Angular 18): [postulare-frontend](https://github.com/costanna/postulare-frontend)

> La API corre en el plan gratuito de Render, que duerme el servicio tras un rato sin uso: la primera petición puede tardar ~30 s en despertarlo.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (Neon) · JWT · pytest

## ¿Qué es Postulare?

Buscar trabajo genera mucho ruido: decenas de candidaturas en hojas de cálculo, ofertas repetidas, no saber a quién hay que volver a escribir. Postulare junta en un solo sitio:

| | |
|---|---|
| **Candidaturas** | Tablero Kanban y tabla con filtros. Cada cambio de estado (guardada → enviada → entrevista → oferta…) deja rastro en una línea de tiempo. |
| **Ofertas recomendadas** | Busca en [Adzuna](https://developer.adzuna.com/) (y en [InfoJobs](https://developer.infojobs.net/), si lo activas) con tu puesto y tus skills, descarta ofertas de otro nivel y repetidas, y puntúa cada una de 0 a 100. |
| **Carta de presentación** | Por oferta, con IA (Claude) si está activada o con una plantilla gratuita en catalán, castellano e inglés. |
| **Importar CV** | Sube tu CV en PDF y se rellena el perfil (puesto, ubicación, nivel, skills, resumen). El PDF no se guarda. |
| **Seguimientos** | Avisa de las candidaturas que llevan días sin novedades. |
| **Exportar** | Todas tus candidaturas en CSV. |
| **Demo sin registro** | Cuenta temporal con datos de ejemplo para probar la app. |

## Capturas

<p>
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/dashboard.png" alt="Dashboard con seguimientos pendientes" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/matches.png" alt="Ofertas recomendadas" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/cover-letter.png" alt="Carta de presentación" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/profile-cv-import.png" alt="Importar CV" width="49%">
</p>

## Arquitectura

```mermaid
flowchart LR
    U[Navegador] --> V[Frontend Angular<br/>Vercel]
    V -->|HTTPS + JWT| R[API FastAPI<br/>Render]
    R --> N[(PostgreSQL<br/>Neon)]
    R -->|ofertas| A[Adzuna API]
    R -.->|cartas, opcional| C[Anthropic API]
```

El backend es la única pieza que habla con servicios de terceros: el navegador nunca ve las claves de Adzuna ni de Anthropic.

## Endpoints principales

Todos salvo `/auth/*` y `/health` exigen `Authorization: Bearer <token>` y solo devuelven datos del usuario autenticado. El detalle completo está en `/docs`.

| Recurso | Endpoints |
|---|---|
| Autenticación | `POST /auth/register` · `/auth/login` · `/auth/refresh` · `/auth/forgot-password` · `/auth/reset-password` · `/auth/demo` · `GET /auth/me` |
| Perfil | `GET/PATCH /profile` · `POST /profile/import-cv` |
| Candidaturas | `GET/POST /applications` · `GET/PATCH/DELETE /applications/{id}` · `GET /applications/follow-ups` · `GET /applications/export` |
| Eventos | `GET/POST /applications/{id}/events` · `DELETE /events/{id}` |
| Ofertas | `GET/PUT /matches/filters` · `POST /matches/search` · `GET /matches` · `POST /matches/{id}/convert` · `/dismiss` · `/cover-letter` |
| Estadísticas | `GET /stats/summary` · `/by-status` · `/timeline` · `/by-source` |

## Puesta en marcha local

Requisitos: Python 3.12+ y PostgreSQL 16 (o Docker).

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); en Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                 # rellena DATABASE_URL, SECRET_KEY y, si quieres buscar ofertas, ADZUNA_APP_ID/KEY
docker compose up -d db              # PostgreSQL local (o apunta DATABASE_URL a tu propia base)
alembic upgrade head
uvicorn app.main:app --reload
```

- API: <http://localhost:8000> · Swagger: <http://localhost:8000/docs>
- Todo en Docker (base de datos + API, con migraciones automáticas): `docker compose up --build`

### Variables de entorno

La lista completa y comentada está en [`.env.example`](.env.example). Nunca subas un `.env` real (ya está en `.gitignore`).

| Variable | ¿Obligatoria? | Para qué sirve |
|---|---|---|
| `DATABASE_URL` | Sí | Conexión a PostgreSQL (con Neon, la cadena «directa» y `?sslmode=require`) |
| `SECRET_KEY` | Sí | Firma de los JWT. Usa un valor largo y aleatorio |
| `CORS_ORIGINS`, `FRONTEND_URL` | Sí en producción | URL del frontend, sin barra final. `FRONTEND_URL` se usa en el enlace del email de recuperar contraseña |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Para buscar ofertas | Claves gratuitas de [developer.adzuna.com](https://developer.adzuna.com/) |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | No | Activan InfoJobs como segunda fuente de ofertas (ver más abajo) |
| `ANTHROPIC_API_KEY` | No | Activa las cartas con IA. Sin ella se usa la plantilla gratuita |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | No | Envío real del email de recuperar contraseña. Sin SMTP el enlace solo se escribe en el log |

## Tests

```bash
pytest
```

218 tests con SQLite en memoria: no tocan PostgreSQL, ni Alembic, ni las APIs reales (Adzuna y Anthropic se simulan).

## Despliegue: Neon + Render

### 1. Base de datos en Neon

1. Crea un proyecto en [neon.tech](https://neon.tech) (capa gratuita sin caducidad).
2. Copia la cadena de conexión **«directa»** (no la «pooled»): `postgresql://usuario:contraseña@ep-xxxx.aws.neon.tech/postulare?sslmode=require`.

### 2. Servicio web en Render

1. En Render: **New +** → **Blueprint** y elige este repositorio. [`render.yaml`](render.yaml) describe el servicio a partir del `Dockerfile`.
2. Rellena los valores marcados como pendientes (tabla de abajo). `SECRET_KEY` se genera sola.
3. Cada despliegue ejecuta `alembic upgrade head` antes de arrancar, así que las migraciones se aplican solas contra Neon. El health check es `GET /health`.

### Qué hay que configurar en Render

Las variables de un servicio ya creado **no se sincronizan solas** desde `render.yaml`: añádelas a mano en *Dashboard → tu servicio → Environment*.

| Variable | Valor | Notas |
|---|---|---|
| `DATABASE_URL` | Cadena de Neon | Obligatoria |
| `SECRET_KEY` | Aleatoria y larga | Obligatoria. Si la cambias, se cierran todas las sesiones |
| `CORS_ORIGINS` | `https://postulare.vercel.app` | Sin barra final |
| `FRONTEND_URL` | `https://postulare.vercel.app` | Debe ser exacta: el email de recuperar contraseña enlaza a `FRONTEND_URL/auth/reset-password` |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Tus claves de Adzuna | Sin ellas (y sin InfoJobs) «Buscar ofertas» responde 502 |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | Tus claves de InfoJobs | **Opcional**: activa InfoJobs como segunda fuente |
| `ANTHROPIC_API_KEY` | Tu clave de Anthropic | **Opcional**: activa las cartas con IA |
| `ANTHROPIC_MODEL` | `claude-opus-5` (por defecto) | `claude-haiku-4-5` sale mucho más barato |
| `LLM_DAILY_LIMIT` / `COVER_LETTER_DAILY_LIMIT_PER_USER` | `20` / `5` | Topes de gasto diarios (global y por usuario) |
| `DEMO_ENABLED`, `DEMO_TTL_HOURS` | `true`, `24` | Cuentas demo temporales |
| `SMTP_*` | Tu proveedor de correo | **Opcional**, pero sin ello no llega ningún email de recuperar contraseña |

## Ofertas de empleo: qué APIs se pueden usar

- **Adzuna** (en uso): API oficial y gratuita, agrega ofertas de muchas webs.
- **InfoJobs** (opcional): [API oficial](https://developer.infojobs.net/) (`GET /api/9/offer`). Se activa poniendo `INFOJOBS_CLIENT_ID` y `INFOJOBS_CLIENT_SECRET`. Para conseguirlas: entra en <https://developer.infojobs.net/> con tu cuenta de InfoJobs (créala en infojobs.net si no tienes) y registra una aplicación en <https://developer.infojobs.net/app/manage-app/create.xhtml>; al crearla te da las dos claves. Los resultados se mezclan con los de Adzuna, se quitan los repetidos y tiene su propio tope diario (`INFOJOBS_DAILY_LIMIT`). Si una de las fuentes falla, la búsqueda sigue con la otra. El listado de InfoJobs no trae la descripción completa, así que la puntuación de esas ofertas se apoya en el título, el requisito mínimo y la categoría.
- **LinkedIn**: **no** existe una API pública para buscar ofertas; su API de empleo es solo para socios que *publican* ofertas y no acepta nuevos. Hacer scraping incumple sus términos y arriesga el bloqueo de la cuenta, así que el proyecto no lo hace.

## Protección de cuotas y gasto

Una demo pública no debe agotar tus cuotas ni tu saldo. Cada recurso de pago tiene su tope, y el que importa no depende de quién llame ni desde dónde.

**Adzuna (gratis, pero con cuota):**

1. Espera entre búsquedas por usuario (`MATCH_SEARCH_COOLDOWN_MINUTES`, 10 min).
2. Caché de búsquedas idénticas (`ADZUNA_CACHE_MINUTES`, 6 h).
3. Límite por IP en registro, login y recuperar contraseña. La IP viene de `X-Forwarded-For`, que se puede falsear: por eso hay una cuarta capa.
4. **Tope diario global** (`ADZUNA_DAILY_LIMIT`, 50), contado en la tabla `adzuna_usage`. Al alcanzarlo, la búsqueda responde `503` y el resto de la app sigue.

**Cartas con IA (cada carta cuesta dinero):**

- Sin `ANTHROPIC_API_KEY` no se gasta nada: sale la plantilla gratuita.
- Tope global diario (`LLM_DAILY_LIMIT`) y por usuario (`COVER_LETTER_DAILY_LIMIT_PER_USER`), en la tabla `llm_usage`. Al agotarse sigue saliendo la plantilla, nunca un error.
- Si la IA falla se devuelve la plantilla y **se devuelve la reserva** del tope.
- La descripción de la oferta es texto de un tercero: va delimitada y el prompt ordena no obedecer instrucciones que contenga.

## Cuentas demo

`POST /auth/demo` crea al instante un usuario con datos ficticios, sin email ni contraseña. No puede buscar ofertas reales (403), sus cartas usan siempre la plantilla, caduca a las `DEMO_TTL_HOURS` horas y las caducadas se borran solas con todos sus datos. Hay límite por IP y un tope global de demos al día.

## Seguridad

- Contraseñas con `bcrypt`; JWT de acceso de 15 min y refresh de 7 días.
- Cada endpoint filtra por el `user_id` del token: nadie ve ni modifica datos de otro usuario (un recurso ajeno responde 404, no 403).
- Los emails no distinguen mayúsculas; «recuperar contraseña» responde igual exista o no la cuenta.
- CORS restringido a `CORS_ORIGINS`. El CSV exportado neutraliza fórmulas de Excel.
- El CV se procesa en memoria y se descarta.

## Estructura del proyecto

```text
app/
├── main.py        FastAPI, CORS y routers
├── core/          configuración, seguridad (JWT, hashing) y límites por IP
├── db/            engine, sesión y tipos portables PostgreSQL/SQLite
├── models/        modelos SQLAlchemy
├── schemas/       esquemas Pydantic (entrada/salida)
├── routers/       endpoints por recurso
└── services/      lógica de negocio: búsqueda y puntuación de ofertas, cartas,
                   importador de CV, duplicados, demo, cuotas de IA, estadísticas
alembic/           migraciones
tests/             pytest
```

## Ideas para seguir

- Puntuación de ofertas razonada con IA (hoy es por palabras clave).
- Recordatorios por email de los seguimientos pendientes.

## Licencia

[MIT](LICENSE) © 2026 Anna Costa
