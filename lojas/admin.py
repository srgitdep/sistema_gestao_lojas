from django.contrib import admin
from .models import Loja

@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cidade', 'telefone', 'data_criacao']
    search_fields = ['nome', 'cidade']
    list_filter = ['cidade']