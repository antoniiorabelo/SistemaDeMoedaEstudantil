from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import re
import logging

from .models import (Aluno, ContaMoeda, CreditoSemestral, DistribuicaoMoedas,
                     NotificacaoEmail, Professor, Resgate, UsuarioSistema, Vantagem)

logger = logging.getLogger(__name__)


class SaldoInsuficiente(ValidationError):
    pass


def enviar_notificacao(notificacao_id):
    """Envia uma notificação persistida; falhas ficam disponíveis para nova tentativa."""
    aviso = NotificacaoEmail.objects.get(pk=notificacao_id)
    if aviso.status == NotificacaoEmail.Status.ENVIADA:
        return
    try:
        enviados = send_mail(aviso.assunto, aviso.corpo, settings.DEFAULT_FROM_EMAIL, [aviso.destinatario], fail_silently=False)
        if enviados != 1:
            raise RuntimeError('O backend de e-mail não confirmou o envio.')
    except Exception as error:
        logger.exception('Falha no envio da notificação %s', aviso.pk)
        NotificacaoEmail.objects.filter(pk=aviso.pk).update(
            status=NotificacaoEmail.Status.ERRO, tentativas=F('tentativas') + 1, ultimo_erro=str(error)[:1000])
    else:
        NotificacaoEmail.objects.filter(pk=aviso.pk).update(
            status=NotificacaoEmail.Status.ENVIADA, tentativas=F('tentativas') + 1,
            ultimo_erro='', enviado_em=timezone.now())


def _agendar_notificacao(destinatario, assunto, corpo, **origem):
    aviso = NotificacaoEmail.objects.create(
        destinatario=destinatario, assunto=assunto, corpo=corpo, **origem)
    transaction.on_commit(lambda: enviar_notificacao(aviso.pk), robust=True)


@transaction.atomic
def salvar_cadastro(form):
    """Persiste credenciais, perfil e conta como uma única operação."""
    registro = form.save(commit=False)
    data = form.cleaned_data
    if registro.pk and form.usuario:
        usuario = UsuarioSistema.objects.select_for_update().select_related('user').get(pk=form.usuario.pk)
        user = usuario.user
    else:
        user = get_user_model()()
        tipo = (UsuarioSistema.Tipo.ALUNO if isinstance(registro, Aluno) else
                UsuarioSistema.Tipo.PROFESSOR if isinstance(registro, Professor) else
                UsuarioSistema.Tipo.EMPRESA)
        usuario = UsuarioSistema(tipo=tipo)
    user.username = data['username']
    user.email = data['email']
    if data.get('senha'):
        user.set_password(data['senha'])
    user.save()
    usuario.user = user
    usuario.nome = data['nome']
    usuario.email = data['email']
    usuario.full_clean()
    usuario.save()
    registro.usuario = usuario
    registro.full_clean()
    registro.save()
    if isinstance(registro, (Aluno, Professor)):
        titular = 'aluno' if isinstance(registro, Aluno) else 'professor'
        ContaMoeda.objects.get_or_create(**{titular: registro})
    return registro


@transaction.atomic
def excluir_cadastro(registro):
    # Excluir somente o perfil deixaria credenciais órfãs. A cascata começa no User.
    registro.usuario.user.delete()


@transaction.atomic
def creditar_semestre(semestre):
    """Crédito cumulativo, uma vez por professor ativo e semestre."""
    if not re.fullmatch(r'\d{4}\.[12]', semestre):
        raise ValidationError('Use o semestre no formato AAAA.1 ou AAAA.2.')
    quantidade = 0
    for professor in Professor.objects.filter(usuario__user__is_active=True):
        _, criado = CreditoSemestral.objects.get_or_create(professor=professor, semestre=semestre)
        if criado:
            ContaMoeda.objects.filter(professor=professor).update(saldo=F('saldo') + 1000)
            quantidade += 1
    return quantidade


@transaction.atomic
def distribuir_moedas(professor, aluno, quantidade, motivo):
    if quantidade <= 0 or not motivo or not motivo.strip():
        raise ValidationError('Informe uma quantidade positiva e um motivo.')
    if not professor.usuario.user.is_active:
        raise ValidationError('Professor inativo.')
    debitado = ContaMoeda.objects.filter(professor=professor, saldo__gte=quantidade).update(saldo=F('saldo') - quantidade)
    if not debitado:
        raise SaldoInsuficiente('Saldo insuficiente para distribuir moedas.')
    ContaMoeda.objects.filter(aluno=aluno).update(saldo=F('saldo') + quantidade)
    distribuicao = DistribuicaoMoedas.objects.create(
        professor=professor, aluno=aluno, quantidade=quantidade, motivo=motivo.strip())
    _agendar_notificacao(
        aluno.usuario.email, 'Você recebeu moedas estudantis',
        f'{professor.usuario.nome} enviou {quantidade} moedas para você. Motivo: {motivo.strip()}',
        distribuicao=distribuicao)
    return distribuicao


@transaction.atomic
def resgatar_vantagem(aluno, vantagem):
    vantagem = Vantagem.objects.select_for_update().select_related('empresa__usuario').get(pk=vantagem.pk)
    if not vantagem.ativa:
        raise ValidationError('Esta vantagem não está disponível.')
    custo = vantagem.custo_moedas
    debitado = ContaMoeda.objects.filter(aluno=aluno, saldo__gte=custo).update(saldo=F('saldo') - custo)
    if not debitado:
        raise SaldoInsuficiente('Saldo insuficiente para o resgate.')
    resgate = Resgate.objects.create(aluno=aluno, vantagem=vantagem, custo_registrado=custo)
    mensagem = f'Cupom {resgate.codigo_cupom} para {vantagem.descricao}. Custo: {custo} moedas.'
    for destinatario in (aluno.usuario.email, vantagem.empresa.usuario.email):
        _agendar_notificacao(destinatario, 'Cupom de vantagem estudantil', mensagem, resgate=resgate)
    return resgate
