#!/usr/bin/env bash
# SAFEEPI: grava sozinho o vídeo do tutorial em videos/safeepi-tutorial.mp4
# Opções: --720 (arquivo menor), --velocidade 1.25 (mais rápido), --ver (mostra a janela).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Rode primeiro o ./iniciar.sh, que prepara o ambiente do SAFEEPI."
  exit 1
fi
if ! .venv/bin/python -c "import playwright, imageio_ffmpeg" 2>/dev/null; then
  echo "Instalando o gravador (só na primeira vez)..."
  .venv/bin/python -m pip install -q -r requirements-gravacao.txt
fi
.venv/bin/python -m playwright install chromium
.venv/bin/python ferramentas/gravar_video.py "$@"
