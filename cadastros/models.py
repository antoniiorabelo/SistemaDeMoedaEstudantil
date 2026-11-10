import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.core.validators import MinValueValidator

from .validators import validar_cpf, validar_rg


def gerar_codigo_cupom():
    return uuid.uuid4().hex.upper()


class InstituicaoEnsino(models.Model):
    nome = models.CharField('nome', max_length=180, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'instituição de ensino'
        verbose_name_plural = 'instituições de ensino'

    def __str__(self):
        return self.nome


class UsuarioSistema(models.Model):
    """Dados comuns; credenciais e hash de senha pertencem ao User do Django."""

    class Tipo(models.TextChoices):
        ALUNO = 'aluno', 'Aluno'
        EMPRESA = 'empresa', 'Empresa parceira'
        PROFESSOR = 'professor', 'Professor'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cadastro')
    nome = models.CharField('nome', max_length=180)
    email = models.EmailField('e-mail', unique=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='cadastro_email_sem_distinguir_caixa')]
        verbose_name = 'usuário do sistema'
        verbose_name_plural = 'usuários do sistema'

    def __str__(self):
        return self.nome


class Aluno(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.OneToOneField(UsuarioSistema, on_delete=models.CASCADE, related_name='aluno')
    cpf = models.CharField('CPF', max_length=11, unique=True, validators=[validar_cpf])
    rg = models.CharField('RG', max_length=20, unique=True, validators=[validar_rg])
    endereco = models.CharField('endereço', max_length=255)
    instituicao = models.ForeignKey(InstituicaoEnsino, on_delete=models.PROTECT, verbose_name='instituição de ensino')
    curso = models.CharField('curso', max_length=120)

    class Meta:
        ordering = ['usuario__nome', 'id']

    def __str__(self):
        return self.usuario.nome


class EmpresaParceira(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.OneToOneField(UsuarioSistema, on_delete=models.CASCADE, related_name='empresa')

    class Meta:
        ordering = ['usuario__nome', 'id']
        verbose_name = 'empresa parceira'
        verbose_name_plural = 'empresas parceiras'

    def __str__(self):
        return self.usuario.nome


class Professor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.OneToOneField(UsuarioSistema, on_delete=models.CASCADE, related_name='professor')
    cpf = models.CharField('CPF', max_length=11, unique=True, validators=[validar_cpf])
    departamento = models.CharField(max_length=120)
    instituicao = models.ForeignKey(InstituicaoEnsino, on_delete=models.PROTECT)

    class Meta:
        ordering = ['usuario__nome']
        verbose_name_plural = 'professores'

    def __str__(self):
        return self.usuario.nome


class ContaMoeda(models.Model):
    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE, related_name='conta', null=True, blank=True)
    professor = models.OneToOneField(Professor, on_delete=models.CASCADE, related_name='conta', null=True, blank=True)
    saldo = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(saldo__gte=0), name='saldo_nao_negativo'),
            models.CheckConstraint(
                condition=(models.Q(aluno__isnull=False, professor__isnull=True) |
                           models.Q(aluno__isnull=True, professor__isnull=False)),
                name='conta_um_titular',
            ),
        ]
        verbose_name = 'conta de moedas'
        verbose_name_plural = 'contas de moedas'

    def __str__(self):
        return f'{self.aluno or self.professor}: {self.saldo} moedas'


class CreditoSemestral(models.Model):
    professor = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='creditos')
    semestre = models.CharField(max_length=6)
    quantidade = models.PositiveIntegerField(default=1000, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['professor', 'semestre'], name='credito_unico_professor_semestre')]
        ordering = ['-criado_em']


class DistribuicaoMoedas(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professor = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='distribuicoes')
    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name='recebimentos')
    quantidade = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    motivo = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        constraints = [models.CheckConstraint(condition=models.Q(quantidade__gt=0), name='distribuicao_positiva')]


class Vantagem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empresa = models.ForeignKey(EmpresaParceira, on_delete=models.PROTECT, related_name='vantagens')
    descricao = models.CharField(max_length=255)
    foto_url = models.URLField('URL da foto')
    custo_moedas = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        constraints = [models.CheckConstraint(condition=models.Q(custo_moedas__gt=0), name='vantagem_custo_positivo')]

    def __str__(self):
        return self.descricao


class Resgate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT, related_name='resgates')
    vantagem = models.ForeignKey(Vantagem, on_delete=models.PROTECT, related_name='resgates')
    custo_registrado = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    codigo_cupom = models.CharField(max_length=32, unique=True, default=gerar_codigo_cupom)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        constraints = [models.CheckConstraint(condition=models.Q(custo_registrado__gt=0), name='resgate_custo_positivo')]


class NotificacaoEmail(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'pendente', 'Pendente'
        ENVIADA = 'enviada', 'Enviada'
        ERRO = 'erro', 'Erro'

    distribuicao = models.ForeignKey(DistribuicaoMoedas, on_delete=models.PROTECT, null=True, blank=True, related_name='notificacoes')
    resgate = models.ForeignKey(Resgate, on_delete=models.PROTECT, null=True, blank=True, related_name='notificacoes')
    destinatario = models.EmailField()
    assunto = models.CharField(max_length=180)
    corpo = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    tentativas = models.PositiveIntegerField(default=0)
    ultimo_erro = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    enviado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em']
        constraints = [models.CheckConstraint(
            condition=(models.Q(distribuicao__isnull=False, resgate__isnull=True) |
                       models.Q(distribuicao__isnull=True, resgate__isnull=False)),
            name='notificacao_uma_origem',
        )]
