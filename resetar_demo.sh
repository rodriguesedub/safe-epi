#!/usr/bin/env bash
# Recria os dados de demonstração (rode antes de cada apresentação).
set -e
cd "$(dirname "$0")"
.venv/bin/python manage.py seed_demo --reset
