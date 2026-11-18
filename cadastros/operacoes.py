from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import DistribuicaoForm, VantagemForm
from .models import Aluno, EmpresaParceira, Professor, Resgate, Vantagem
from .services import distribuir_moedas, resgatar_vantagem


def perfil(request, model):
    registro = model.objects.filter(usuario__user=request.user).first()
    if registro is None:
        raise PermissionDenied('Esta função não está disponível para seu perfil.')
    return registro


@login_required
def extrato(request):
    aluno = Aluno.objects.filter(usuario__user=request.user).select_related('conta').first()
    professor = Professor.objects.filter(usuario__user=request.user).select_related('conta').first()
    titular = aluno or professor
    if titular is None:
        raise PermissionDenied('Extrato disponível para alunos e professores.')
    movimentos = []
    if aluno:
        for item in aluno.recebimentos.select_related('professor__usuario'):
            movimentos.append((item.criado_em, item.quantidade, f'Recebido de {item.professor.usuario.nome}: {item.motivo}'))
        for item in aluno.resgates.select_related('vantagem'):
            movimentos.append((item.criado_em, -item.custo_registrado, f'Resgate: {item.vantagem.descricao}'))
    else:
        for item in professor.creditos.all():
            movimentos.append((item.criado_em, item.quantidade, f'Crédito semestral {item.semestre}'))
        for item in professor.distribuicoes.select_related('aluno__usuario'):
            movimentos.append((item.criado_em, -item.quantidade, f'Enviado a {item.aluno.usuario.nome}: {item.motivo}'))
    movimentos.sort(key=lambda item: item[0], reverse=True)
    return render(request, 'cadastros/extrato.html', {'titular': titular, 'movimentos': movimentos})


@login_required
@require_http_methods(['GET', 'POST'])
def distribuir(request):
    professor = perfil(request, Professor)
    form = DistribuicaoForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            distribuir_moedas(professor, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Moedas enviadas ao aluno.')
            return redirect('extrato')
    return render(request, 'cadastros/distribuir.html', {'form': form, 'saldo': professor.conta.saldo})


@login_required
def minhas_vantagens(request):
    empresa = perfil(request, EmpresaParceira)
    vantagens = empresa.vantagens.all()
    resgates = Resgate.objects.filter(vantagem__empresa=empresa).select_related('aluno__usuario', 'vantagem')
    return render(request, 'cadastros/minhas_vantagens.html', {'vantagens': vantagens, 'resgates': resgates})


@login_required
@require_http_methods(['GET', 'POST'])
def vantagem_formulario(request, pk=None):
    empresa = perfil(request, EmpresaParceira)
    vantagem = get_object_or_404(Vantagem, pk=pk, empresa=empresa) if pk else None
    form = VantagemForm(request.POST if request.method == 'POST' else None, instance=vantagem)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.empresa = empresa
        item.save()
        messages.success(request, 'Vantagem salva com sucesso.')
        return redirect('minhas_vantagens')
    return render(request, 'cadastros/vantagem_formulario.html', {'form': form, 'vantagem': vantagem})


@login_required
def catalogo(request):
    aluno = perfil(request, Aluno)
    vantagens = Vantagem.objects.filter(ativa=True).select_related('empresa__usuario')
    return render(request, 'cadastros/catalogo.html', {'vantagens': vantagens, 'saldo': aluno.conta.saldo})


@login_required
@require_http_methods(['GET', 'POST'])
def resgatar(request, pk):
    aluno = perfil(request, Aluno)
    vantagem = get_object_or_404(Vantagem.objects.select_related('empresa__usuario'), pk=pk, ativa=True)
    if request.method == 'POST':
        try:
            resgate = resgatar_vantagem(aluno, vantagem)
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(request, 'Resgate concluído. O cupom está disponível e o aviso por e-mail foi solicitado.')
            return redirect('cupom', pk=resgate.pk)
    return render(request, 'cadastros/resgatar.html', {'vantagem': vantagem, 'saldo': aluno.conta.saldo})


@login_required
def cupom(request, pk):
    aluno = perfil(request, Aluno)
    resgate = get_object_or_404(Resgate.objects.select_related('vantagem__empresa__usuario'), pk=pk, aluno=aluno)
    return render(request, 'cadastros/cupom.html', {'resgate': resgate})
