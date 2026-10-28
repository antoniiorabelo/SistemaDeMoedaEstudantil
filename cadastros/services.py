from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Aluno, ContaMoeda, UsuarioSistema


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
        usuario = UsuarioSistema(tipo=UsuarioSistema.Tipo.ALUNO if isinstance(registro, Aluno) else UsuarioSistema.Tipo.EMPRESA)
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
    if isinstance(registro, Aluno):
        ContaMoeda.objects.get_or_create(aluno=registro)
    return registro


@transaction.atomic
def excluir_cadastro(registro):
    # Excluir somente o perfil deixaria credenciais órfãs. A cascata começa no User.
    registro.usuario.user.delete()
