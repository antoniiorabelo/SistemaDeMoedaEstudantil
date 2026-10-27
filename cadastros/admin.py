from django.contrib import admin

from .models import Aluno, ContaMoeda, EmpresaParceira, InstituicaoEnsino, UsuarioSistema


@admin.register(InstituicaoEnsino)
class InstituicaoAdmin(admin.ModelAdmin):
    search_fields = ['nome']


# Cadastros são escritos pelas telas e serviços, preservando a transação de User/perfil/conta.
class ConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Aluno)
class AlunoAdmin(ConsultaAdmin):
    list_display = ['usuario', 'cpf', 'instituicao', 'curso']
    search_fields = ['usuario__nome', 'cpf']
    list_filter = ['instituicao']


@admin.register(EmpresaParceira)
class EmpresaAdmin(ConsultaAdmin):
    list_display = ['usuario']
    search_fields = ['usuario__nome', 'usuario__email']


admin.site.register(UsuarioSistema, ConsultaAdmin)
admin.site.register(ContaMoeda, ConsultaAdmin)
admin.site.site_header = 'Moeda Estudantil · Administração'
