from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import operacoes, views


class TipoConverter:
    regex = 'alunos|empresas|professores'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(TipoConverter, 'tipo')

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('entrar/', auth_views.LoginView.as_view(template_name='cadastros/login.html'), name='login'),
    path('sair/', auth_views.LogoutView.as_view(), name='logout'),
    path('extrato/', operacoes.extrato, name='extrato'),
    path('distribuir/', operacoes.distribuir, name='distribuir'),
    path('vantagens/', operacoes.catalogo, name='catalogo'),
    path('minhas-vantagens/', operacoes.minhas_vantagens, name='minhas_vantagens'),
    path('minhas-vantagens/nova/', operacoes.vantagem_formulario, name='vantagem_criar'),
    path('minhas-vantagens/<uuid:pk>/editar/', operacoes.vantagem_formulario, name='vantagem_editar'),
    path('vantagens/<uuid:pk>/resgatar/', operacoes.resgatar, name='resgatar'),
    path('cupons/<uuid:pk>/', operacoes.cupom, name='cupom'),
    path('<tipo:tipo>/', views.lista, name='lista'),
    path('<tipo:tipo>/novo/', views.criar, name='criar'),
    path('<tipo:tipo>/<uuid:pk>/', views.detalhe, name='detalhe'),
    path('<tipo:tipo>/<uuid:pk>/editar/', views.editar, name='editar'),
    path('<tipo:tipo>/<uuid:pk>/excluir/', views.excluir, name='excluir'),
]
