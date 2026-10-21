from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from epis.views import api_epi

admin.site.site_header = "SAFEEPI — cadastros"
admin.site.site_title = "SAFEEPI"
admin.site.index_title = "Cadastros e dados mestres"

urlpatterns = [
    path("", include("core.urls")),
    path("contas/", include("contas.urls")),
    path("pre-liberacoes/", include("liberacoes.urls")),
    path("epis/", include("epis.urls")),
    path("reposicoes/", include("reposicao.urls")),
    path("alertas/", include("alertas.urls")),
    path("painel/", include("relatorios.urls")),
    path("auditoria/", include("auditoria.urls")),
    path("cadastros/", include("cadastros.urls")),
    path("api/v1/epis/<str:codigo>/", api_epi, name="api_epi"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
