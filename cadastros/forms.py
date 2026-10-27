from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from .models import Aluno, EmpresaParceira, UsuarioSistema
from .validators import normalizar_cpf, normalizar_rg, validar_cpf, validar_rg

User = get_user_model()


class CadastroForm(forms.ModelForm):
    nome = forms.CharField(label='Nome', max_length=180)
    email = forms.EmailField(label='E-mail', max_length=254)
    username = forms.CharField(label='Login', max_length=150, validators=User._meta.get_field('username').validators)
    senha = forms.CharField(label='Senha', widget=forms.PasswordInput, strip=False,
                           help_text='Use pelo menos 8 caracteres. Evite senhas comuns ou apenas números.')
    confirmar_senha = forms.CharField(label='Confirme a senha', widget=forms.PasswordInput, strip=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = self.instance.usuario if not self.instance._state.adding else None
        if self.usuario:
            self.initial.update(nome=self.usuario.nome, email=self.usuario.email, username=self.usuario.user.username)
            self.fields['senha'].required = False
            self.fields['confirmar_senha'].required = False
            self.fields['senha'].help_text = 'Deixe os dois campos de senha vazios para manter a senha atual.'
        self.order_fields(['nome', 'email', 'cpf', 'rg', 'endereco', 'instituicao', 'curso', 'username', 'senha', 'confirmar_senha'])
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'input'
            if name in ('senha', 'confirmar_senha'):
                field.widget.attrs['autocomplete'] = 'new-password'
            elif name == 'username':
                field.widget.attrs['autocomplete'] = 'username'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        perfis = UsuarioSistema.objects.filter(email__iexact=email)
        users = User.objects.filter(email__iexact=email)
        if self.usuario:
            perfis = perfis.exclude(pk=self.usuario.pk)
            users = users.exclude(pk=self.usuario.user_id)
        if perfis.exists() or users.exists():
            raise ValidationError('Este e-mail já está cadastrado.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip().lower()
        users = User.objects.filter(username__iexact=username)
        if self.usuario:
            users = users.exclude(pk=self.usuario.user_id)
        if users.exists():
            raise ValidationError('Este login já está em uso.')
        return username

    def clean(self):
        data = super().clean()
        senha = data.get('senha')
        confirmacao = data.get('confirmar_senha')
        if senha != confirmacao:
            self.add_error('confirmar_senha', 'As senhas não conferem.')
        if senha:
            user = User(username=data.get('username', ''), email=data.get('email', ''), first_name=data.get('nome', ''))
            try:
                password_validation.validate_password(senha, user)
            except ValidationError as error:
                self.add_error('senha', error)
        return data


class AlunoForm(CadastroForm):
    # Campos declarados permitem aceitar pontuação antes de validar e salvar normalizado.
    cpf = forms.CharField(label='CPF', max_length=14, help_text='Aceita CPF com ou sem pontuação.')
    rg = forms.CharField(label='RG', max_length=30, help_text='Informe o RG; pontuação e espaços serão removidos.')

    class Meta:
        model = Aluno
        fields = ['cpf', 'rg', 'endereco', 'instituicao', 'curso']

    def clean_cpf(self):
        value = normalizar_cpf(self.cleaned_data['cpf'])
        validar_cpf(value)
        return value

    def clean_rg(self):
        value = normalizar_rg(self.cleaned_data['rg'])
        validar_rg(value)
        return value


class EmpresaForm(CadastroForm):
    class Meta:
        model = EmpresaParceira
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nome'].label = 'Nome da empresa'
