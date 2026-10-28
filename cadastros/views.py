from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AlunoForm, EmpresaForm
from .models import Aluno, EmpresaParceira
from .services import excluir_cadastro, salvar_cadastro


CONFIG = {
    'alunos': {'model': Aluno, 'form': AlunoForm, 'singular': 'aluno', 'plural': 'Alunos'},
    'empresas': {'model': EmpresaParceira, 'form': EmpresaForm, 'singular': 'empresa', 'plural': 'Empresas parceiras'},
}


def contexto(tipo):
    return dict(CONFIG[tipo], tipo=tipo)


def registros(tipo):
    query = CONFIG[tipo]['model'].objects.select_related('usuario__user')
    if tipo == 'alunos':
        query = query.select_related('instituicao', 'conta')
    return query


def verificar_acesso(request, registro):
    if not request.user.is_staff and registro.usuario.user_id != request.user.pk:
        raise PermissionDenied('Você não tem acesso a este cadastro.')


def inicio(request):
    cadastro = None
    if request.user.is_authenticated and not request.user.is_staff:
        cadastro = Aluno.objects.filter(usuario__user=request.user).first()
        tipo = 'alunos'
        if cadastro is None:
            cadastro = EmpresaParceira.objects.filter(usuario__user=request.user).first()
            tipo = 'empresas'
        if cadastro:
            return redirect('detalhe', tipo=tipo, pk=cadastro.pk)
    return render(request, 'cadastros/inicio.html', {
        'total_alunos': Aluno.objects.count() if request.user.is_staff else None,
        'total_empresas': EmpresaParceira.objects.count() if request.user.is_staff else None,
    })


@login_required
def lista(request, tipo):
    if not request.user.is_staff:
        raise PermissionDenied('A listagem é restrita à administração.')
    query = registros(tipo)
    busca = request.GET.get('q', '').strip()
    if busca:
        filtro = Q(usuario__nome__icontains=busca) | Q(usuario__email__icontains=busca) | Q(usuario__user__username__icontains=busca)
        if tipo == 'alunos':
            filtro |= Q(cpf__icontains=busca) | Q(curso__icontains=busca) | Q(instituicao__nome__icontains=busca)
        query = query.filter(filtro)
    pagina = Paginator(query, 10).get_page(request.GET.get('page'))
    return render(request, 'cadastros/lista.html', {**contexto(tipo), 'pagina': pagina, 'busca': busca})


@login_required
def detalhe(request, tipo, pk):
    registro = get_object_or_404(registros(tipo), pk=pk)
    verificar_acesso(request, registro)
    return render(request, 'cadastros/detalhe.html', {**contexto(tipo), 'registro': registro})


@require_http_methods(['GET', 'POST'])
def criar(request, tipo):
    if request.user.is_authenticated and not request.user.is_staff:
        raise PermissionDenied('Você já possui um cadastro. Edite seu perfil.')
    return formulario(request, tipo)


@login_required
@require_http_methods(['GET', 'POST'])
def editar(request, tipo, pk):
    registro = get_object_or_404(registros(tipo), pk=pk)
    verificar_acesso(request, registro)
    return formulario(request, tipo, registro)


def formulario(request, tipo, registro=None):
    form = CONFIG[tipo]['form'](request.POST if request.method == 'POST' else None, instance=registro)
    if request.method == 'POST' and form.is_valid():
        try:
            salvo = salvar_cadastro(form)
        except (IntegrityError, ValidationError):
            form.add_error(None, 'Não foi possível salvar. Verifique se os dados já estão cadastrados e tente novamente.')
        else:
            messages.success(request, 'Cadastro atualizado com sucesso.' if registro else 'Cadastro criado com sucesso.')
            if request.user.is_authenticated:
                if salvo.usuario.user_id == request.user.pk:
                    update_session_auth_hash(request, salvo.usuario.user)
                return redirect('detalhe', tipo=tipo, pk=salvo.pk)
            messages.info(request, 'Entre com seu login e senha para acessar o perfil.')
            return redirect('login')
    return render(request, 'cadastros/formulario.html', {**contexto(tipo), 'form': form, 'registro': registro})


@login_required
@require_http_methods(['GET', 'POST'])
def excluir(request, tipo, pk):
    registro = get_object_or_404(registros(tipo), pk=pk)
    verificar_acesso(request, registro)
    if request.method == 'POST':
        staff = request.user.is_staff
        excluir_cadastro(registro)
        messages.success(request, 'Cadastro e credenciais excluídos com sucesso.')
        if staff:
            return redirect('lista', tipo=tipo)
        return redirect('inicio')
    return render(request, 'cadastros/excluir.html', {**contexto(tipo), 'registro': registro})
