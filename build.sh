#!/usr/bin/env bash
# Exit on error
set -o errexit

# Atualiza pip e instala dependências de produção
pip install --upgrade pip
pip install -r requirements-postgres.txt

# Coleta os arquivos estáticos (CSS, JS, fontes, etc.)
python manage.py collectstatic --noinput
