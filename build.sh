#!/usr/bin/env bash
# Exit on error
set -o errexit

# Atualiza pip e instala dependências de produção
pip install --upgrade pip
pip install -r requirements-postgres.txt

# Coleta os arquivos estáticos (CSS, JS, fontes, etc.)
python manage.py collectstatic --noinput

# Aplica migrações do banco de dados
python manage.py migrate --noinput

# Popula dados de demonstração se for a primeira inicialização
python manage.py seed_demo --se-vazio
