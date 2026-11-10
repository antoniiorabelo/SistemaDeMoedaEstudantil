from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.utils import timezone

from cadastros.services import creditar_semestre


class Command(BaseCommand):
    help = 'Credita 1.000 moedas a cada professor ativo, uma vez por semestre.'

    def add_arguments(self, parser):
        parser.add_argument('semestre', nargs='?', help='Formato AAAA.1 ou AAAA.2; padrão: semestre atual')

    def handle(self, *args, **options):
        try:
            hoje = timezone.localdate()
            semestre = options['semestre'] or f'{hoje.year}.{1 if hoje.month <= 6 else 2}'
            quantidade = creditar_semestre(semestre)
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write(self.style.SUCCESS(f'{quantidade} professor(es) creditado(s) em {semestre}.'))
