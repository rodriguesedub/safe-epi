"""Grava sozinho o vídeo do tutorial do SAFEEPI.

Abre um navegador invisível, roda a reprodução automática do começo ao fim e salva o vídeo.
Não mexe nos seus dados: usa um banco separado (videos/gravacao.sqlite3) e um servidor próprio.

Uso
  python ferramentas/gravar_video.py                       Full HD (1920x1080), velocidade normal
  python ferramentas/gravar_video.py --720                 1280x720, arquivo menor
  python ferramentas/gravar_video.py --velocidade 1.25     mais rápido (0.5 a 3)
  python ferramentas/gravar_video.py --ver                 mostra a janela enquanto grava
  python ferramentas/gravar_video.py --saida meu.mp4

Precisa de
  pip install playwright imageio-ffmpeg
  python -m playwright install chromium
O gravar_video.bat (Windows) e o gravar_video.sh (macOS e Linux) fazem isso na primeira vez.
"""
import argparse
import base64
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_VIDEOS = RAIZ / "videos"
FPS = 30


def avisar(msg):
    print(f"[gravador] {msg}", flush=True)


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def achar_ffmpeg():
    caminho = shutil.which("ffmpeg")
    if caminho:
        return caminho
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def preparar_banco(env):
    avisar("Preparando um banco separado para a gravação...")
    subprocess.run([sys.executable, "manage.py", "migrate", "--noinput", "-v", "0"], cwd=RAIZ, env=env, check=True)


def subir_servidor(env, porta):
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{porta}", "--noreload"],
        cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            with urllib.request.urlopen(base + "/contas/entrar/", timeout=2) as r:
                if r.status == 200:
                    return proc, base
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise SystemExit("O servidor não respondeu. Rode o iniciar.bat ou iniciar.sh uma vez para preparar o projeto.")


class GravadorTela:
    """Grava pelo protocolo do Chrome (quadros JPEG) e codifica em H.264 com o ffmpeg."""

    def __init__(self, pagina, contexto, ffmpeg, saida, largura, altura):
        self.cdp = contexto.new_cdp_session(pagina)
        self.largura, self.altura = largura, altura
        self.ultimo = None
        self.t0 = None
        self.quadros = 0
        self.trava = threading.Lock()
        self.ff = subprocess.Popen(
            [ffmpeg, "-loglevel", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS),
             "-i", "pipe:0", "-vf", f"scale={largura}:{altura}:flags=lanczos,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
             "-r", str(FPS), "-movflags", "+faststart", str(saida)],
            stdin=subprocess.PIPE)
        self.cdp.on("Page.screencastFrame", self._quadro)

    def _completar_ate(self, t):
        """Repete o último quadro até o vídeo chegar ao instante t (taxa fixa de FPS)."""
        if self.ultimo is None:
            return
        alvo = round((t - self.t0) * FPS)
        while self.quadros < alvo:
            self.ff.stdin.write(self.ultimo)
            self.quadros += 1

    def _quadro(self, params):
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass
        dados = base64.b64decode(params["data"])
        t = params.get("metadata", {}).get("timestamp") or time.time()
        with self.trava:
            if self.t0 is None:
                self.t0 = t
            self._completar_ate(t)
            self.ultimo = dados

    def iniciar(self):
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                               "maxWidth": self.largura, "maxHeight": self.altura})

    def terminar(self):
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        with self.trava:
            if self.ultimo is not None:
                self._completar_ate(time.time() + 1.0 / FPS)
            self.ff.stdin.close()
        self.ff.wait()
        return self.quadros / FPS


def main():
    ap = argparse.ArgumentParser(description="Grava o vídeo do tutorial do SAFEEPI.")
    ap.add_argument("--velocidade", type=float, default=1.0, help="0.5 a 3 (padrão 1)")
    ap.add_argument("--720", dest="hd720", action="store_true", help="grava em 1280x720")
    ap.add_argument("--ver", action="store_true", help="mostra a janela do navegador")
    ap.add_argument("--saida", default=str(PASTA_VIDEOS / "safeepi-tutorial.mp4"))
    args = ap.parse_args()
    vel = min(3.0, max(0.5, args.velocidade))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Falta o Playwright. Rode: pip install playwright imageio-ffmpeg "
                         "e depois python -m playwright install chromium")

    ffmpeg = achar_ffmpeg()
    saida = Path(args.saida).resolve()
    if not ffmpeg and saida.suffix.lower() != ".webm":
        avisar("ffmpeg não encontrado: o vídeo sai em .webm (instale com pip install imageio-ffmpeg para ter .mp4).")
        saida = saida.with_suffix(".webm")
    saida.parent.mkdir(parents=True, exist_ok=True)
    PASTA_VIDEOS.mkdir(exist_ok=True)

    env = dict(os.environ, SAFEEPI_DEMO="1", SAFEEPI_DEBUG="1",
               SAFEEPI_SQLITE=str(PASTA_VIDEOS / "gravacao.sqlite3"))
    env.pop("DATABASE_URL", None)
    preparar_banco(env)
    porta = porta_livre()
    servidor, base = subir_servidor(env, porta)
    largura, altura = (1280, 720) if args.hd720 else (1920, 1080)
    escala = largura / 1280
    try:
        with sync_playwright() as p:
            try:
                navegador = p.chromium.launch(headless=not args.ver)
            except Exception as e:
                raise SystemExit(f"Não consegui abrir o Chromium ({e}). Rode: python -m playwright install chromium")

            # 1. Entra como o João (sem gravar): os dados voltam ao início.
            ctx = navegador.new_context(viewport={"width": 1280, "height": 720})
            pg = ctx.new_page()
            pg.goto(base + "/contas/entrar/")
            with pg.expect_navigation(url=lambda u: "tour=" in u, timeout=120000):
                pg.evaluate("""() => {
                  const f = document.querySelector('form[action="/demo/iniciar/"]');
                  f.querySelector('input[name=modo]').value = 'guiado';
                  f.submit();
                }""")
            sessao = ctx.storage_state()
            ctx.close()

            # 2. Grava a reprodução automática do começo ao fim.
            opcoes = dict(viewport={"width": 1280, "height": 720}, device_scale_factor=escala,
                          storage_state=sessao, locale="pt-BR")
            pasta_tmp = None
            if not ffmpeg:
                pasta_tmp = tempfile.mkdtemp()
                opcoes.update(record_video_dir=pasta_tmp, record_video_size={"width": largura, "height": altura})
            ctx = navegador.new_context(**opcoes)
            pg = ctx.new_page()
            gravador = GravadorTela(pg, ctx, ffmpeg, saida, largura, altura) if ffmpeg else None
            if gravador:
                gravador.iniciar()
            avisar(f"Gravando em {largura}x{altura}, velocidade {vel:g}. Leva cerca de {round(4 / vel)} minutos...")
            inicio = time.time()
            pg.goto(base + f"/?tour=auto&vel={vel:g}&contagem=0")
            pg.wait_for_selector("html[data-tour-fim]", state="attached", timeout=15 * 60 * 1000)
            pg.wait_for_timeout(3500)
            duracao = time.time() - inicio
            if gravador:
                duracao = gravador.terminar()
                ctx.close()
            else:
                video = pg.video
                ctx.close()
                shutil.move(video.path(), saida)
                shutil.rmtree(pasta_tmp, ignore_errors=True)
            navegador.close()
    finally:
        servidor.terminate()
        try:
            servidor.wait(timeout=10)
        except Exception:
            servidor.kill()
    avisar(f"Pronto: {saida} ({duracao / 60:.1f} min)")


if __name__ == "__main__":
    main()
