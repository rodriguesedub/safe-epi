from django.core.management.base import BaseCommand

from alertas.services import gerar_alertas


class Command(BaseCommand):
    help = "Gera e resolve alertas de vencimento (rodar 1 vez ao dia; RF13)."

    def add_arguments(self, parser):
        parser.add_argument("--sem-email", action="store_true", help="Não envia o resumo por e-mail.")

    def handle(self, *args, **opts):
        r = gerar_alertas(enviar_email=not opts["sem_email"])
        self.stdout.write(self.style.SUCCESS(
            f"{r['criados']} novos, {r['atualizados']} atualizados, "
            f"{r['resolvidos']} resolvidos, {r['abertos']} abertos."))
