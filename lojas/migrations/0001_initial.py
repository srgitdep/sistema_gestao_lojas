from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Loja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True, verbose_name='Nome da Loja')),
                ('slug', models.SlugField(blank=True, max_length=100, unique=True, verbose_name='Slug')),
                ('endereco', models.CharField(blank=True, max_length=200, verbose_name='Endereço')),
                ('telefone', models.CharField(blank=True, max_length=20, verbose_name='Telefone')),
                ('cidade', models.CharField(default='Maputo', max_length=100, verbose_name='Cidade')),
                ('data_criacao', models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')),
            ],
            options={
                'verbose_name': 'Loja',
                'verbose_name_plural': 'Lojas',
                'ordering': ['nome'],
            },
        ),
    ]