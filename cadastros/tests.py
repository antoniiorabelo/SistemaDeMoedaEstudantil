from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import AlunoForm
from .models import (Aluno, ContaMoeda, CreditoSemestral, DistribuicaoMoedas,
                     EmpresaParceira, InstituicaoEnsino, NotificacaoEmail, Professor, Resgate,
                     UsuarioSistema, Vantagem)
from .services import (SaldoInsuficiente, creditar_semestre, distribuir_moedas,
                       resgatar_vantagem, salvar_cadastro)

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


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OperacoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instituicao = InstituicaoEnsino.objects.create(nome='Campus')
        cls.admin = User.objects.create_superuser('admin', 'admin@example.com', SENHA)
        cls.aluno_user = User.objects.create_user('aluno', 'aluno@example.com', SENHA)
        cls.prof_user = User.objects.create_user('prof', 'prof@example.com', SENHA)
        cls.empresa_user = User.objects.create_user('empresa', 'empresa@example.com', SENHA)
        cls.outro_user = User.objects.create_user('outra', 'outra@example.com', SENHA)
        cls.aluno = Aluno.objects.create(
            usuario=UsuarioSistema.objects.create(user=cls.aluno_user, nome='Aluno', email='aluno@example.com', tipo='aluno'),
            cpf='52998224725', rg='123456789', endereco='Rua A', instituicao=cls.instituicao, curso='Computação')
        cls.outro = Aluno.objects.create(
            usuario=UsuarioSistema.objects.create(user=cls.outro_user, nome='Outra', email='outra@example.com', tipo='aluno'),
            cpf='11144477735', rg='987654321', endereco='Rua B', instituicao=cls.instituicao, curso='Engenharia')
        cls.professor = Professor.objects.create(
            usuario=UsuarioSistema.objects.create(user=cls.prof_user, nome='Professor', email='prof@example.com', tipo='professor'),
            cpf='39053344705', departamento='Computação', instituicao=cls.instituicao)
        cls.empresa = EmpresaParceira.objects.create(
            usuario=UsuarioSistema.objects.create(user=cls.empresa_user, nome='Empresa', email='empresa@example.com', tipo='empresa'))
        ContaMoeda.objects.create(aluno=cls.aluno)
        ContaMoeda.objects.create(aluno=cls.outro)
        ContaMoeda.objects.create(professor=cls.professor)
        cls.vantagem = Vantagem.objects.create(
            empresa=cls.empresa, descricao='Livro', foto_url='https://example.com/livro.jpg', custo_moedas=120)

    def test_pre_cadastro_professor_restrito_ao_admin(self):
        url = reverse('criar', args=['professores'])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        data = dict(nome='Novo professor', email='novo@example.com', username='novo', senha=SENHA,
                    confirmar_senha=SENHA, cpf='123.456.789-09', departamento='Matemática', instituicao=self.instituicao.pk)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        novo = Professor.objects.get(usuario__user__username='novo')
        self.assertEqual(novo.conta.saldo, 0)
        self.assertEqual(novo.instituicao, self.instituicao)

    def test_credito_semestral_acumula_e_nao_duplica(self):
        self.assertEqual(creditar_semestre('2026.2'), 1)
        self.assertEqual(creditar_semestre('2026.2'), 0)
        self.assertEqual(creditar_semestre('2027.1'), 1)
        self.professor.conta.refresh_from_db()
        self.assertEqual(self.professor.conta.saldo, 2000)
        self.assertEqual(CreditoSemestral.objects.count(), 2)

    def test_distribuicao_atomica_e_email_apos_commit(self):
        creditar_semestre('2026.2')
        with self.captureOnCommitCallbacks(execute=True):
            distribuicao = distribuir_moedas(self.professor, self.aluno, 150, 'Mérito acadêmico')
        self.professor.conta.refresh_from_db()
        self.aluno.conta.refresh_from_db()
        self.assertEqual((self.professor.conta.saldo, self.aluno.conta.saldo), (850, 150))
        self.assertEqual(distribuicao.motivo, 'Mérito acadêmico')
        self.assertEqual(mail.outbox[-1].to, ['aluno@example.com'])
        with self.assertRaises(SaldoInsuficiente):
            distribuir_moedas(self.professor, self.aluno, 9999, 'Mais moedas')
        self.assertEqual(DistribuicaoMoedas.objects.count(), 1)

    def test_resgate_debita_uma_vez_gera_cupom_e_notifica_ambos(self):
        ContaMoeda.objects.filter(aluno=self.aluno).update(saldo=200)
        with self.captureOnCommitCallbacks(execute=True):
            resgate = resgatar_vantagem(self.aluno, self.vantagem)
        self.aluno.conta.refresh_from_db()
        self.assertEqual(self.aluno.conta.saldo, 80)
        self.assertEqual(resgate.custo_registrado, 120)
        self.assertEqual(len(resgate.codigo_cupom), 32)
        self.assertCountEqual([item.to[0] for item in mail.outbox[-2:]], ['aluno@example.com', 'empresa@example.com'])
        self.assertTrue(all(resgate.codigo_cupom in item.body for item in mail.outbox[-2:]))
        self.assertEqual(resgate.notificacoes.filter(status=NotificacaoEmail.Status.ENVIADA).count(), 2)
        with self.assertRaises(SaldoInsuficiente):
            resgatar_vantagem(self.aluno, self.vantagem)
        self.assertEqual(Resgate.objects.count(), 1)

    def test_permissoes_e_telas_dos_perfis(self):
        self.client.force_login(self.prof_user)
        self.assertEqual(self.client.get(reverse('distribuir')).status_code, 200)
        self.assertEqual(self.client.get(reverse('extrato')).status_code, 200)
        self.assertEqual(self.client.get(reverse('catalogo')).status_code, 403)
        self.client.force_login(self.empresa_user)
        self.assertEqual(self.client.get(reverse('minhas_vantagens')).status_code, 200)
        self.assertEqual(self.client.get(reverse('distribuir')).status_code, 403)
        self.client.force_login(self.aluno_user)
        self.assertEqual(self.client.get(reverse('catalogo')).status_code, 200)
        self.assertEqual(self.client.get(reverse('extrato')).status_code, 200)
        self.assertEqual(self.client.get(reverse('minhas_vantagens')).status_code, 403)

    def test_vantagem_pertence_a_empresa_e_resgate_so_por_post(self):
        self.client.force_login(self.aluno_user)
        url = reverse('resgatar', args=[self.vantagem.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(Resgate.objects.exists())
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(Resgate.objects.exists())
        self.client.force_login(self.empresa_user)
        self.assertEqual(self.client.get(reverse('vantagem_editar', args=[self.vantagem.pk])).status_code, 200)
        self.client.force_login(self.outro_user)
        self.assertEqual(self.client.get(reverse('vantagem_editar', args=[self.vantagem.pk])).status_code, 403)

    def test_email_com_falha_fica_registrado_para_reenvio(self):
        creditar_semestre('2026.2')
        with patch('cadastros.services.send_mail', side_effect=OSError('servidor indisponível')):
            with patch('cadastros.services.logger.exception'):
                with self.captureOnCommitCallbacks(execute=True):
                    distribuir_moedas(self.professor, self.aluno, 10, 'Participação')
        aviso = NotificacaoEmail.objects.get()
        self.assertEqual(aviso.status, NotificacaoEmail.Status.ERRO)
        self.assertEqual(aviso.tentativas, 1)
        call_command('reenviar_emails', stdout=StringIO())
        aviso.refresh_from_db()
        self.assertEqual(aviso.status, NotificacaoEmail.Status.ENVIADA)
        self.assertEqual(aviso.tentativas, 2)
        self.assertEqual(mail.outbox[-1].to, ['aluno@example.com'])

    def test_empresa_cadastra_vantagem_e_aluno_resgata_pela_interface(self):
        self.client.force_login(self.empresa_user)
        response = self.client.post(reverse('vantagem_criar'), {
            'descricao': 'Ingresso', 'foto_url': 'https://example.com/ingresso.jpg',
            'custo_moedas': 90, 'ativa': 'on',
        })
        self.assertRedirects(response, reverse('minhas_vantagens'))
        item = Vantagem.objects.get(descricao='Ingresso')
        self.assertEqual(item.empresa, self.empresa)
        ContaMoeda.objects.filter(aluno=self.aluno).update(saldo=100)
        self.client.force_login(self.aluno_user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('resgatar', args=[item.pk]))
        resgate = Resgate.objects.get(vantagem=item)
        self.assertRedirects(response, reverse('cupom', args=[resgate.pk]))
        self.assertContains(self.client.get(reverse('cupom', args=[resgate.pk])), resgate.codigo_cupom)
        self.aluno.conta.refresh_from_db()
        self.assertEqual(self.aluno.conta.saldo, 10)
        self.client.force_login(self.outro_user)
        self.assertEqual(self.client.get(reverse('cupom', args=[resgate.pk])).status_code, 404)

    def test_vantagem_inativa_fica_fora_do_catalogo_e_nao_resgata(self):
        self.vantagem.ativa = False
        self.vantagem.save(update_fields=['ativa'])
        self.client.force_login(self.aluno_user)
        self.assertNotContains(self.client.get(reverse('catalogo')), 'Livro')
        self.assertEqual(self.client.post(reverse('resgatar', args=[self.vantagem.pk])).status_code, 404)
        self.assertFalse(Resgate.objects.exists())
