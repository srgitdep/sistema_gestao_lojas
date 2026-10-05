import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from lojas.models import Loja
from produtos.models import PerfilUsuario

User = get_user_model()

# ====== CONFIGURACOES ======
slugs = ['malhampsene', 'shoprite', 'shoupal', 'zimpeto1', 'zimpeto2']
senha = 'gerente2025'  # Pode mudar se quiser
# ===========================

# Garante que o grupo Vendedor existe
grupo, created = Group.objects.get_or_create(name='Vendedor')
if created:
    print("[INFO] Grupo 'Vendedor' criado.")
else:
    print("[INFO] Grupo 'Vendedor' ja existe.")

for slug in slugs:
    # Pega a loja pelo slug
    try:
        loja = Loja.objects.get(slug=slug)
    except Loja.DoesNotExist:
        print(f"[ERRO] Loja com slug '{slug}' nao encontrada. Pulando...")
        continue

    username = f'vendedor_{slug}'

    # Cria ou obtem o usuario
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': 'Vendedor',
            'last_name': loja.nome,
            'email': f'{username}@srg.com',
        }
    )

    # Define a senha (sempre atualiza)
    user.set_password(senha)
    user.save()

    # Adiciona ao grupo Vendedor
    user.groups.add(grupo)

    # Cria/atualiza o PerfilUsuario
    perfil, perfil_created = PerfilUsuario.objects.get_or_create(
        user=user,
        defaults={'loja': loja}
    )
    if not perfil_created:
        perfil.loja = loja
        perfil.save()

    status = "CRIADO" if created else "ATUALIZADO"
    print(f"[OK] {status} -> {username} | Loja: {loja.nome} | Senha: {senha}")

print("\n" + "="*60)
print("PROCESSO CONCLUIDO! Agora tente fazer login com um vendedor:")
for slug in slugs:
    print(f"   vendedor_{slug} / {senha}")
print("="*60)

# Lista final para conferir
print("\nCONFERENCIA RAPIDA:")
for slug in slugs:
    username = f'vendedor_{slug}'
    try:
        user = User.objects.get(username=username)
        grupos = ", ".join([g.name for g in user.groups.all()])
        loja = PerfilUsuario.objects.get(user=user).loja.nome
        print(f"  {username} | Grupos: {grupos} | Loja: {loja}")
    except User.DoesNotExist:
        print(f"  ERRO: {username} nao encontrado!")