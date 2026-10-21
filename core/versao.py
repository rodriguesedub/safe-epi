"""Versão dos arquivos estáticos, para o navegador e o service worker não usarem cópias velhas.

Muda sempre que um arquivo em static/ muda (data e tamanho). Vai como ?v= nos links
de CSS e JS e no nome do cache do service worker.
"""
import hashlib
import time

from django.conf import settings

_cache = {"em": 0.0, "valor": ""}


def versao_estaticos():
    agora = time.monotonic()
    if _cache["valor"] and (not settings.DEBUG or agora - _cache["em"] < 2):
        return _cache["valor"]
    h = hashlib.sha1()
    for pasta in getattr(settings, "STATICFILES_DIRS", []):
        for arq in sorted(p for p in pasta.rglob("*") if p.is_file()):
            info = arq.stat()
            h.update(f"{arq.relative_to(pasta)}:{info.st_mtime_ns}:{info.st_size};".encode())
    _cache.update(em=agora, valor=h.hexdigest()[:10])
    return _cache["valor"]
