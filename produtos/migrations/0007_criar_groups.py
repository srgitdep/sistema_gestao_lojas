
from django.db import migrations
from django.contrib.auth.models import Group

def criar_grupos(apps, schema_editor):
    Group.objects.get_or_create(name='Vendedor')
    Group.objects.get_or_create(name='Gerente')
    Group.objects.get_or_create(name='Dono')

class Migration(migrations.Migration):
    dependencies = [
        ('produtos', '0006_venda_metodo_pagamento'),  # ajuste para sua última migração
    ]

    operations = [
        migrations.RunPython(criar_grupos),
    ]
