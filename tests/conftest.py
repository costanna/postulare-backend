"""Fixtures compartidas: BD SQLite en memoria + TestClient con la dependencia get_db sobrescrita.

Los tests nunca tocan la base de datos real ni Alembic: las tablas se crean
directamente desde los modelos (Base.metadata.create_all), algo aceptable en
tests aunque esté prohibido en producción.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str = "ana@example.com", password: str = "supersecret123") -> dict:
    """Registra un usuario, hace login y devuelve los headers de Authorization listos para usar."""
    client.post("/auth/register", json={"email": email, "password": password, "full_name": "Ana"})
    login = client.post("/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_headers(client) -> dict:
    return register_and_login(client)
