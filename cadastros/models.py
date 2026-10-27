import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from .validators import validar_cpf, validar_rg


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


class ContaMoeda(models.Model):
    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE, related_name='conta')
    saldo = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(saldo__gte=0), name='saldo_nao_negativo')]
        verbose_name = 'conta de moedas'
        verbose_name_plural = 'contas de moedas'

    def __str__(self):
        return f'{self.aluno}: {self.saldo} moedas'
