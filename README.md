# Postulare — Backend

API REST del proyecto **Postulare**: seguimiento de candidaturas de empleo con
búsqueda y scoring automático de ofertas afines a tu perfil.

Stack: **Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL · JWT**.

> Frontend (Angular 18) en un repositorio hermano: [postulare-frontend](https://github.com/costanna/postulare-frontend).

## Estado del proyecto

Este backend se construye de forma incremental, en ramas por funcionalidad:

- [x] `feature/backend-bootstrap` — estructura del proyecto, modelo de datos, migración inicial de Alembic, autenticación JWT (registro, login, refresh, recuperación de contraseña) con tests
- [ ] Perfil de usuario + CRUD de candidaturas y eventos
- [ ] Matching de ofertas (cliente Adzuna + scoring por keywords)
- [ ] Estadísticas del dashboard
- [ ] Docker Compose y despliegue

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
