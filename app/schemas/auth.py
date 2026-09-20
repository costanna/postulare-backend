from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import PreferredLanguage


class _NormalizedEmail(BaseModel):
    """Los emails no distinguen mayúsculas: se guardan y comparan siempre en minúsculas."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.strip().lower()


class UserRegister(_NormalizedEmail):
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class UserLogin(_NormalizedEmail):
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenOnly(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(_NormalizedEmail):
    pass


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class DemoRequest(BaseModel):
    """Idioma de los datos de ejemplo de la cuenta demo."""

    language: PreferredLanguage = PreferredLanguage.es
