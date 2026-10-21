#!/usr/bin/env bash
# Exit on error
set -o errexit

# Aplica migrações no banco de dados ativo (PostgreSQL ou SQLite)
python manage.py migrate --noinput

# Cria os usuários e dados de demonstração (se o banco estiver vazio)
python manage.py seed_demo --se-vazio

# Inicia o Gunicorn com timeout de 120s (necessário para o reset de demonstração na web)
exec gunicorn --timeout 120 safeepi.wsgi:application
