"""Configurações do SAFEEPI.

Padrão: SQLite local, sem nenhuma dependência além do Django.
Para usar PostgreSQL, defina DATABASE_URL=postgres://usuario:senha@host:5432/banco
e instale requirements-postgres.txt.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nome, padrao):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


SECRET_KEY = os.environ.get(
    "SAFEEPI_SECRET_KEY",
    "dev-somente-local-troque-em-producao-9f3c2a7e1b5d4c8a",
)
DEBUG = _env_bool("SAFEEPI_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("SAFEEPI_ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("SAFEEPI_CSRF_ORIGINS", "").split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps de domínio (monolito modular — decisão D1)
    "core",
    "contas",
    "cadastros",
    "epis",
    "liberacoes",
    "alertas",
    "reposicao",
    "relatorios",
    "auditoria",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "safeepi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.safeepi",
            ],
        },
    },
]

WSGI_APPLICATION = "safeepi.wsgi.application"


def _database_from_url(url):
    p = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": p.path.lstrip("/"),
        "USER": p.username or "",
        "PASSWORD": p.password or "",
        "HOST": p.hostname or "localhost",
        "PORT": str(p.port or 5432),
    }


_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith(("postgres://", "postgresql://")):
    DATABASES = {"default": _database_from_url(_db_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # SAFEEPI_SQLITE troca o arquivo (o gravador de vídeo usa um banco separado)
            "NAME": os.environ.get("SAFEEPI_SQLITE") or BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "contas.Usuario"
AUTHENTICATION_BACKENDS = ["contas.backends.UsuarioOuEmailBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "contas:login"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "contas:login"

# Alertas por e-mail: no MVP local, os e-mails aparecem no terminal.
EMAIL_BACKEND = os.environ.get(
    "SAFEEPI_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = "SAFEEPI <alertas@safeepi.local>"

SESSION_COOKIE_AGE = 60 * 60 * 10  # um turno

SAFEEPI = {
    # Antecedência dos alertas de vencimento, em dias (RF13)
    "ALERTA_DIAS": [30, 15, 7],
    # Barra de troca rápida de usuário para apresentações
    "DEMO_MODE": _env_bool("SAFEEPI_DEMO", True),
    # Tamanho máximo da foto de avaria (bytes)
    "FOTO_MAX_BYTES": 5 * 1024 * 1024,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    # 403/404 esperados não poluem o terminal durante a apresentação
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}

if len(sys.argv) > 1 and sys.argv[1] == "test":
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
