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
slugs = ['zimpeto1', 'zimpeto2']
senha = 'gerente2025'
# ===========================

# Garante que o grupo Gerente existe
grupo, created = Group.objects.get_or_create(name='Gerente')
if created:
    print("[INFO] Grupo 'Gerente' criado.")
else:
    print("[INFO] Grupo 'Gerente' ja existe.")

for slug in slugs:
    nome_loja = f'Zimpeto {slug[-1]}'  # 'Zimpeto 1' ou 'Zimpeto 2'

    # 1. Verifica se ja existe uma loja com esse nome (evita duplicidade)
    loja = Loja.objects.filter(nome=nome_loja).first()
    if loja:
        # Se existe, atualiza o slug se necessario
        if loja.slug != slug:
            loja.slug = slug
            loja.save()
            print(f"[OK] Loja '{loja.nome}' atualizada para slug '{slug}'")
        else:
            print(f"[OK] Loja '{loja.nome}' ja existe com slug correto.")
    else:
        # Se nao existe, cria
        loja = Loja.objects.create(
            slug=slug,
            nome=nome_loja,
            cidade='Maputo'
        )
        print(f"[OK] Loja '{loja.nome}' criada com slug '{slug}'")

    username = f'gerente_{slug}'

    # 2. Cria ou obtem o usuario
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': 'Gerente',
            'last_name': loja.nome,
            'email': f'{username}@srg.com',
        }
    )

    # 3. Define a senha (sempre atualiza)
    user.set_password(senha)
    user.save()

    # 4. Adiciona ao grupo Gerente
    user.groups.add(grupo)

    # 5. Cria/atualiza o PerfilUsuario
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
print("PROCESSO CONCLUIDO! Agora tente fazer login com:")
print("   gerente_zimpeto1 / gerente2025")
print("   gerente_zimpeto2 / gerente2025")
print("="*60)

# Lista final para conferir essas duas contas
print("\nCONFERENCIA RAPIDA:")
for slug in slugs:
    username = f'gerente_{slug}'
    try:
        user = User.objects.get(username=username)
        grupos = ", ".join([g.name for g in user.groups.all()])
        loja = PerfilUsuario.objects.get(user=user).loja.nome
        print(f"  {username} | Grupos: {grupos} | Loja: {loja}")
    except User.DoesNotExist:
        print(f"  ERRO: {username} nao encontrado!")