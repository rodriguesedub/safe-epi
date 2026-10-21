#!/usr/bin/env bash
# SAFEEPI: prepara o ambiente na primeira vez e sobe o servidor local.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
ENDERECO="${1:-127.0.0.1:8000}"
if [ ! -x .venv/bin/python ]; then
  echo "Criando ambiente virtual (.venv)..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip >/dev/null
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python manage.py migrate --noinput -v 0
.venv/bin/python manage.py seed_demo --se-vazio
echo
echo "SAFEEPI rodando em http://${ENDERECO}  (Ctrl+C para parar)"
echo "Usuários: operador, tecnico, almox, gestor, operador2, admin. Senha: safeepi123"
echo "Tutorial: na tela de login, Tutorial guiado ou Reprodução automática."
echo
.venv/bin/python manage.py runserver "$ENDERECO"
