from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cadastros.forms import AlunoForm, EmpresaForm
from cadastros.models import InstituicaoEnsino
from cadastros.services import salvar_cadastro


class Command(BaseCommand):
    help = 'Cria instituições e contas fictícias para apresentação local, sem alterar contas existentes.'

    def add_arguments(self, parser):
        parser.add_argument('--senha', required=True, help='Senha inicial das três contas de demonstração.')

    @transaction.atomic
    def handle(self, *args, **options):
        senha = options['senha']
        try:
            password_validation.validate_password(senha)
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        instituicao, _ = InstituicaoEnsino.objects.get_or_create(nome='Instituição de Demonstração (fictícia)')
        User = get_user_model()
        if not User.objects.filter(username__iexact='admin_demo').exists():
            User.objects.create_superuser('admin_demo', 'admin@demo.example', senha)
            self.stdout.write('Administrador criado: admin_demo')
        exemplos = [
            ('aluno_demo', AlunoForm, dict(nome='Ana Silva (demonstração)', email='aluno@demo.example',
                cpf='52998224725', rg='123456789', endereco='Rua de Exemplo, 100',
                instituicao=instituicao.pk, curso='Sistemas de Informação')),
            ('empresa_demo', EmpresaForm, dict(nome='Café Campus (demonstração)', email='empresa@demo.example')),
        ]
        for login, form_class, dados in exemplos:
            if User.objects.filter(username__iexact=login).exists():
                self.stdout.write(f'Conta preservada: {login}')
                continue
            form = form_class(data=dict(dados, username=login, senha=senha, confirmar_senha=senha))
            if not form.is_valid():
                raise CommandError(str(form.errors))
            salvar_cadastro(form)
            self.stdout.write(f'Conta criada: {login}')
        self.stdout.write(self.style.SUCCESS('Demonstração pronta. As senhas de contas existentes foram preservadas.'))
