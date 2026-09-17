#!/bin/sh
# Aplica las migraciones pendientes y arranca la API. Se ejecuta en cada
# arranque del contenedor (local con docker-compose y en el despliegue
# real): alembic no hace nada si el esquema ya está al día, así que es
# seguro repetirlo.
#
# Si se le pasan argumentos (docker-compose.yml lo hace para arrancar con
# --reload en desarrollo) se ejecutan esos en vez del comando por
# defecto; $PORT lo inyectan plataformas como Render/Railway, 8000 es el
# valor por defecto para uso local.
set -e

alembic upgrade head

if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
