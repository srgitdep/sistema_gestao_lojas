from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from lojas.models import Loja
from produtos.models import PerfilUsuario

User = get_user_model()

# ====== CONFIGURAÇÕES ======
slugs = ['zimpeto1', 'zimpeto2']
senha = 'gerente2025'
# ===========================

# Pega o grupo Gerente
try:
    grupo = Group.objects.get(name='Gerente')
except Group.DoesNotExist:
    print("❌ Grupo 'Gerente' não existe. Execute o script principal primeiro.")
    exit()

for slug in slugs:
    nome_loja = f'Zimpeto {slug[-1]}'  # 'Zimpeto 1', 'Zimpeto 2'

    # 1. Verifica se já existe uma loja com esse nome (evita duplicidade)
    loja = Loja.objects.filter(nome=nome_loja).first()
    if loja:
        # Se existe, atualiza o slug se necessário
        if loja.slug != slug:
            loja.slug = slug
            loja.save()
            print(f"🔄 Loja '{loja.nome}' atualizada para slug '{slug}'")
        else:
            print(f"ℹ️ Loja '{loja.nome}' já existe com slug correto.")
    else:
        # Se não existe, cria
        loja = Loja.objects.create(
            slug=slug,
            nome=nome_loja,
            cidade='Maputo'
        )
        print(f"🏪 Loja '{loja.nome}' criada com slug '{slug}'")

    username = f'gerente_{slug}'

    # 2. Cria ou obtém o usuário
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': 'Gerente',
            'last_name': loja.nome,
            'email': f'{username}@srg.com',
        }
    )

    # 3. Define a senha
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

    status = "CRIADO 🆕" if created else "ATUALIZADO 🔄"
    print(f"✅ {status} -> {username} | Loja: {loja.nome} | Senha: {senha}")

print("\n" + "="*60)
print("🎉 PROCESSO CONCLUÍDO! Agora tente fazer login com:")
print("   gerente_zimpeto1 / gerente2025")
print("   gerente_zimpeto2 / gerente2025")
print("="*60)

# Lista final para conferência
print("\n📋 CONFERÊNCIA RÁPIDA:")
for slug in slugs:
    username = f'gerente_{slug}'
    try:
        user = User.objects.get(username=username)
        grupos = ", ".join([g.name for g in user.groups.all()])
        loja = PerfilUsuario.objects.get(user=user).loja.nome
        print(f"👤 {username} | Grupos: {grupos} | Loja: {loja}")
    except User.DoesNotExist:
        print(f"❌ {username} não encontrado!")