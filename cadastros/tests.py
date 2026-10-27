from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .forms import AlunoForm
from .models import Aluno, ContaMoeda, EmpresaParceira, InstituicaoEnsino, UsuarioSistema
from .services import salvar_cadastro

User = get_user_model()
SENHA = 'UmaSenha!Academica2026'


class CadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instituicao = InstituicaoEnsino.objects.create(nome='Instituição de teste')
        cls.admin = User.objects.create_superuser('gestor', 'gestor@example.com', SENHA)

    def dados(self, tipo='alunos', **extras):
        dados = dict(nome='Ana Acadêmica', email='ana@example.com', username='ana', senha=SENHA, confirmar_senha=SENHA)
        if tipo == 'alunos':
            dados.update(cpf='529.982.247-25', rg='12.345.678-9', endereco='Rua Um, 10',
                         instituicao=self.instituicao.pk, curso='Computação')
        dados.update(extras)
        return dados

    def criar(self, tipo='alunos', **extras):
        return self.client.post(reverse('criar', args=[tipo]), self.dados(tipo, **extras))

    def test_aluno_cadastro_completo_normaliza_documentos_e_inicia_conta_zero(self):
        response = self.criar()
        self.assertRedirects(response, reverse('login'))
        aluno = Aluno.objects.get()
        self.assertEqual(aluno.cpf, '52998224725')
        self.assertEqual(aluno.rg, '123456789')
        self.assertEqual(aluno.conta.saldo, 0)
        self.assertNotEqual(aluno.usuario.user.password, SENHA)
        self.assertTrue(aluno.usuario.user.check_password(SENHA))
        self.assertTrue(self.client.login(username='ana', password=SENHA))
        self.assertRedirects(self.client.get(reverse('inicio')), reverse('detalhe', args=['alunos', aluno.pk]))

    def test_empresa_pode_cadastrar_autenticar_consultar_editar_e_excluir(self):
        self.assertRedirects(self.criar('empresas'), reverse('login'))
        empresa = EmpresaParceira.objects.get()
        self.assertEqual(ContaMoeda.objects.count(), 0)
        self.client.login(username='ana', password=SENHA)
        detalhe = reverse('detalhe', args=['empresas', empresa.pk])
        self.assertContains(self.client.get(detalhe), 'Ana Acadêmica')
        dados = self.dados('empresas', nome='Empresa atualizada', senha='', confirmar_senha='')
        self.assertRedirects(self.client.post(reverse('editar', args=['empresas', empresa.pk]), dados), detalhe)
        empresa.refresh_from_db()
        self.assertEqual(empresa.usuario.nome, 'Empresa atualizada')
        self.assertTrue(empresa.usuario.user.check_password(SENHA))
        url = reverse('excluir', args=['empresas', empresa.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(EmpresaParceira.objects.exists())
        self.assertRedirects(self.client.post(url), reverse('inicio'))
        self.assertFalse(EmpresaParceira.objects.exists())
        self.assertFalse(UsuarioSistema.objects.exists())
        self.assertFalse(User.objects.filter(username='ana').exists())

    def test_admin_crud_aluno_busca_e_exclusao_em_cascata(self):
        self.client.force_login(self.admin)
        self.criar()
        aluno = Aluno.objects.get()
        self.assertContains(self.client.get(reverse('lista', args=['alunos']), {'q': 'Computação'}), 'Ana Acadêmica')
        self.assertNotContains(self.client.get(reverse('lista', args=['alunos']), {'q': 'inexistente'}), 'Ana Acadêmica')
        dados = self.dados(nome='Ana Atualizada', curso='Engenharia', senha='', confirmar_senha='')
        response = self.client.post(reverse('editar', args=['alunos', aluno.pk]), dados)
        self.assertRedirects(response, reverse('detalhe', args=['alunos', aluno.pk]))
        aluno.refresh_from_db()
        self.assertEqual(aluno.curso, 'Engenharia')
        self.assertEqual(aluno.usuario.nome, 'Ana Atualizada')
        self.assertEqual(aluno.conta.saldo, 0)
        self.client.post(reverse('excluir', args=['alunos', aluno.pk]))
        self.assertEqual(Aluno.objects.count(), 0)
        self.assertEqual(ContaMoeda.objects.count(), 0)
        self.assertFalse(User.objects.filter(username='ana').exists())

    def test_duplicidades_nao_criam_dados_parciais(self):
        self.criar()
        casos = [dict(email='outra@example.com', username='outra'),
                 dict(cpf='11144477735', email='ANA@EXAMPLE.COM', username='outra'),
                 dict(cpf='11144477735', email='outra@example.com', username='ANA'),
                 dict(cpf='11144477735', email='outra@example.com', username='outra')]
        for dados in casos:
            with self.subTest(dados=dados):
                self.assertEqual(self.criar(**dados).status_code, 200)
                self.assertEqual(Aluno.objects.count(), 1)
                self.assertEqual(UsuarioSistema.objects.count(), 1)
                self.assertEqual(User.objects.count(), 2)
        self.assertContains(self.criar('empresas', email='ANA@example.com', username='parceira'), 'Este e-mail já está cadastrado.')
        self.assertContains(self.criar('empresas', email='parceira@example.com', username='ANA'), 'Este login já está em uso.')

    def test_campos_obrigatorios_documentos_senha_e_instituicao_invalidos(self):
        for extras in [dict(nome=''), dict(email='email-invalido'), dict(cpf='11111111111'),
                       dict(cpf='52998224726'), dict(rg='!!!'), dict(instituicao=99999),
                       dict(curso=''), dict(endereco=''), dict(senha='12345678', confirmar_senha='12345678'),
                       dict(confirmar_senha='diferente')]:
            with self.subTest(extras=extras):
                self.assertEqual(self.criar(**extras).status_code, 200)
                self.assertFalse(Aluno.objects.exists())
                self.assertFalse(UsuarioSistema.objects.exists())

    def test_transacao_desfaz_user_e_perfil_se_conta_falhar(self):
        form = AlunoForm(data=self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        with patch('cadastros.services.ContaMoeda.objects.get_or_create', side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                salvar_cadastro(form)
        self.assertFalse(Aluno.objects.exists())
        self.assertFalse(UsuarioSistema.objects.exists())
        self.assertFalse(User.objects.filter(username='ana').exists())

    def test_sem_login_e_sem_propriedade_nao_acessa_cadastros(self):
        self.criar()
        aluno = Aluno.objects.get()
        for nome in ['detalhe', 'editar', 'excluir']:
            self.assertEqual(self.client.get(reverse(nome, args=['alunos', aluno.pk])).status_code, 302)
        self.criar('empresas', nome='Parceira', email='parceira@example.com', username='parceira')
        self.client.login(username='parceira', password=SENHA)
        for nome in ['detalhe', 'editar', 'excluir']:
            url = reverse(nome, args=['alunos', aluno.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.dados()).status_code, 403)
        for tipo in ['alunos', 'empresas']:
            self.assertEqual(self.client.get(reverse('lista', args=[tipo])).status_code, 403)
            self.assertEqual(self.client.post(reverse('criar', args=[tipo]), self.dados(tipo)).status_code, 403)

    def test_troca_de_senha_mantem_sessao_e_saldo_nao_e_editavel(self):
        self.criar()
        aluno = Aluno.objects.get()
        ContaMoeda.objects.filter(aluno=aluno).update(saldo=25)
        self.client.login(username='ana', password=SENHA)
        nova_senha = 'NovaSenha!Academica2027'
        dados = self.dados(senha=nova_senha, confirmar_senha=nova_senha, saldo=-100)
        response = self.client.post(reverse('editar', args=['alunos', aluno.pk]), dados)
        self.assertRedirects(response, reverse('detalhe', args=['alunos', aluno.pk]))
        aluno.refresh_from_db()
        self.assertTrue(aluno.usuario.user.check_password(nova_senha))
        self.assertEqual(aluno.conta.saldo, 25)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_incorreto_inativo_e_logout_post(self):
        self.criar()
        response = self.client.post(reverse('login'), {'username': 'ana', 'password': 'errada'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        User.objects.filter(username='ana').update(is_active=False)
        self.assertFalse(self.client.login(username='ana', password=SENHA))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('inicio'))

    def test_csrf_obrigatorio_para_criar_e_excluir(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('criar', args=['alunos']), self.dados()).status_code, 403)
        self.criar()
        aluno = Aluno.objects.get()
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('excluir', args=['alunos', aluno.pk])).status_code, 403)
        self.assertTrue(Aluno.objects.exists())

    def test_restricoes_do_banco_e_instituicao_protegida(self):
        self.criar()
        aluno = Aluno.objects.get()
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.instituicao.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContaMoeda.objects.filter(aluno=aluno).update(saldo=-1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsuarioSistema.objects.create(user=self.admin, nome='Duplicado', email='ANA@EXAMPLE.COM', tipo='empresa')

    def test_paginas_publicas_e_administrativas_renderizam(self):
        for url in [reverse('inicio'), reverse('login'), reverse('criar', args=['alunos']), reverse('criar', args=['empresas'])]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        for url in [reverse('inicio'), reverse('lista', args=['alunos']), reverse('lista', args=['empresas'])]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_demo_e_idempotente_e_preserva_senha_existente(self):
        call_command('preparar_demo', senha=SENHA, stdout=StringIO())
        call_command('preparar_demo', senha='OutraSenha!Academica2027', stdout=StringIO())
        self.assertEqual(Aluno.objects.count(), 1)
        self.assertEqual(EmpresaParceira.objects.count(), 1)
        self.assertTrue(User.objects.get(username='admin_demo').check_password(SENHA))
        self.assertTrue(User.objects.get(username='aluno_demo').check_password(SENHA))
