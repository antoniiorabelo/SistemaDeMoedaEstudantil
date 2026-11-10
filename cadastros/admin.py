from django.contrib import admin

from .models import (Aluno, ContaMoeda, CreditoSemestral, DistribuicaoMoedas,
                     EmpresaParceira, InstituicaoEnsino, NotificacaoEmail, Professor, Resgate,
                     UsuarioSistema, Vantagem)


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
admin.site.register(Professor, ConsultaAdmin)
admin.site.register(CreditoSemestral, ConsultaAdmin)
admin.site.register(DistribuicaoMoedas, ConsultaAdmin)
admin.site.register(Vantagem, ConsultaAdmin)
admin.site.register(Resgate, ConsultaAdmin)
admin.site.register(NotificacaoEmail, ConsultaAdmin)
admin.site.site_header = 'Moeda Estudantil · Administração'
