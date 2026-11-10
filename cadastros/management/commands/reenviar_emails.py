from django.core.management.base import BaseCommand

from cadastros.models import NotificacaoEmail
from cadastros.services import enviar_notificacao


class Command(BaseCommand):
    help = 'Reenvia notificações pendentes ou que falharam.'

    def handle(self, *args, **options):
        ids = list(NotificacaoEmail.objects.exclude(status=NotificacaoEmail.Status.ENVIADA).values_list('pk', flat=True))
        for notificacao_id in ids:
            enviar_notificacao(notificacao_id)
        self.stdout.write(self.style.SUCCESS(f'{len(ids)} notificação(ões) processada(s).'))
