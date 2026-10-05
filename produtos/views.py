from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Q, Sum, Count
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from decimal import Decimal
from datetime import datetime
from .models import (
    Produto, Estoque, Venda, ItemVenda,
    Servico, ServicoRealizado, ItemServico,
    PerfilUsuario, Entrada 
)
from lojas.models import Loja
from django.utils import timezone
from datetime import timedelta, datetime

# ====== IMPORTS PARA REPORTLAB (PDF) ======
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import logging
# ====== IMPORTS ADICIONAIS ======
import io  
import pytz
import json
from django.http import JsonResponse
from .models import ReversaoVenda  # junto com os outros imports


# ====== IMPORTS DO DJANGO (já existentes) ======
from django.contrib.auth import logout
from django.shortcuts import redirect  # (já existe, pode manter ou remover duplicata)


# =============================================
# Funções auxiliares para verificar grupos
# =============================================
def eh_vendedor_ou_dono(user):
    return user.is_superuser or user.groups.filter(name__in=['Vendedor', 'Dono']).exists()

def eh_gerente_ou_dono(user):
    return user.is_superuser or user.groups.filter(name__in=['Gerente', 'Dono']).exists()

def eh_dono(user):
    return user.is_superuser or user.groups.filter(name='Dono').exists()


# =============================================
# LOGIN - Redireciona conforme o grupo do usuário
# =============================================
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Tenta obter a loja associada ao usuário
            loja_slug = None
            try:
                perfil = PerfilUsuario.objects.get(user=user)
                loja_slug = perfil.loja.slug
            except PerfilUsuario.DoesNotExist:
                # Caso use o campo loja diretamente no CustomUser
                if hasattr(user, 'loja') and user.loja:
                    loja_slug = user.loja.slug
            
            if not loja_slug and not user.is_superuser:
                messages.error(request, "Usuário sem loja associada. Contacte o administrador.")
                return redirect('login')

            # Redirecionamento inteligente por grupo
            if user.is_superuser or user.groups.filter(name='Dono').exists():
                return redirect('dono_lista_lojas')
            
            elif user.groups.filter(name='Vendedor').exists():
                if loja_slug:
                    return redirect('dashboard_loja', loja_slug=loja_slug)
                else:
                    messages.error(request, "Vendedor sem loja configurada.")
                    return redirect('login')
            
            elif user.groups.filter(name='Gerente').exists():
                if loja_slug:
                    return redirect('produtos:dashboard_gerente', loja_slug=loja_slug)
                else:
                    messages.error(request, "Gerente sem loja configurada.")
                    return redirect('login')
            
            else:
                messages.error(request, "Seu usuário não tem permissão de acesso definida.")
                return redirect('login')
        else:
            messages.error(request, "Usuário ou senha incorretos.")
    
    return render(request, 'produtos/login.html')


# =============================================
# Dashboard do Vendedor
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def dashboard_loja(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    estoques = Estoque.objects.filter(loja=loja)

    context = {
        'estoques': estoques,
        'loja_atual': loja,
    }
    return render(request, 'produtos/dashboard_vendedor.html', context)


# =============================================
# Dashboard do Gerente (NOVO)
# =============================================
@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def dashboard_gerente(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    
    context = {
        'loja_atual': loja,
    }
    return render(request, 'produtos/dashboard_gerente.html', context)


# =============================================
# PDV - Apenas Vendedor e Dono
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def pdv(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    carrinho = request.session.get('carrinho', {})

    itens = []
    total = Decimal('0')
    for prod_id, dados in carrinho.items():
        try:
            produto = Produto.objects.get(id=prod_id)
            qty = dados['quantidade']
            desconto_item = Decimal(dados.get('desconto', '0'))
            desconto_por_unidade = desconto_item / qty if qty > 0 else Decimal('0')
            preco_com_desconto = produto.preco_venda - desconto_por_unidade
            subtotal = qty * preco_com_desconto
            itens.append({
                'produto': produto,
                'quantidade': qty,
                'desconto': desconto_item,
                'preco_com_desconto': preco_com_desconto,
                'subtotal': subtotal
            })
            total += subtotal
        except Produto.DoesNotExist:
            continue

    busca = request.GET.get('busca')
    produtos_busca = None
    if busca:
        produtos_busca = Produto.objects.filter(
            Q(nome__icontains=busca) | Q(codigo__icontains=busca),
            estoques__loja=loja
        ).distinct()

    context = {
        'loja_atual': loja,
        'itens': itens,
        'total': total,
        'produtos_busca': produtos_busca,
    }
    return render(request, 'produtos/pdv.html', context)


# =============================================
# Adicionar ao carrinho (PDV)
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def adicionar_ao_carrinho(request, loja_slug):
    if request.method == 'POST':
        produto_id = request.POST['produto_id']
        quantidade = int(request.POST.get('quantidade', 1))
        
        # Desconto normal (total)
        desconto_str = request.POST.get('desconto', '0').strip()
        desconto = Decimal(desconto_str if desconto_str else '0')
        
        # 🔥 NOVO: Desconto a Grosso (por unidade)
        desconto_grosso_str = request.POST.get('desconto_grosso', '0').strip()
        desconto_grosso = Decimal(desconto_grosso_str if desconto_grosso_str else '0')
        
        # 🔥 NOVO: Tipo de preço (normal/atacado)
        tipo_preco = request.POST.get('tipo_preco', 'normal')
        
        # 🔥 NOVO: Para onde voltar (normal ou atacado)
        modo = request.POST.get('modo', 'normal')

        carrinho = request.session.get('carrinho', {})
        
        if produto_id in carrinho:
            # Se já existe, soma quantidade e descontos
            carrinho[produto_id]['quantidade'] += quantidade
            carrinho[produto_id]['desconto'] = str(Decimal(carrinho[produto_id].get('desconto', '0')) + desconto)
            # Substitui o desconto a grosso pelo último valor informado
            carrinho[produto_id]['desconto_grosso'] = str(desconto_grosso)
            # Atualiza o tipo de preço (se mudou)
            carrinho[produto_id]['tipo_preco'] = tipo_preco
        else:
            # Novo item no carrinho
            carrinho[produto_id] = {
                'quantidade': quantidade,
                'desconto': str(desconto),
                'desconto_grosso': str(desconto_grosso),
                'tipo_preco': tipo_preco
            }
        
        request.session['carrinho'] = carrinho
        request.session.modified = True

    # 🔥 Redireciona para o PDV correto (normal ou atacado)
    if modo == 'atacado':
        return redirect('produtos:pdv_atacado', loja_slug=loja_slug)
    else:
        return redirect('produtos:pdv', loja_slug=loja_slug)


# =============================================
# Limpar carrinho (PDV)
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def limpar_carrinho(request, loja_slug):
    request.session['carrinho'] = {}
    request.session.modified = True
    messages.success(request, "Carrinho limpo com sucesso.")
    return redirect('produtos:pdv', loja_slug=loja_slug)


# =============================================
# Editar desconto (PDV)
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def editar_desconto(request, loja_slug):
    if request.method == 'POST':
        produto_id = request.POST['produto_id']
        desconto_str = request.POST.get('desconto', '0').strip()
        desconto = Decimal(desconto_str if desconto_str else '0')

        carrinho = request.session.get('carrinho', {})
        if produto_id in carrinho:
            carrinho[produto_id]['desconto'] = str(desconto)
            request.session['carrinho'] = carrinho
            request.session.modified = True

    return redirect('produtos:pdv', loja_slug=loja_slug)


# =============================================
# Finalizar venda
# =============================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def finalizar_venda(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    carrinho = request.session.get('carrinho', {})

    if not carrinho:
        messages.warning(request, "Carrinho vazio.")
        return redirect('produtos:pdv', loja_slug=loja_slug)

    itens = []
    total = Decimal('0')
    
    # 🔥 NOVO: Descobre o modo (normal/atacado) para redirecionamento
    modo = 'normal'
    
    for prod_id, dados in carrinho.items():
        try:
            produto = Produto.objects.get(id=prod_id)
            qty = dados['quantidade']
            desconto_total = Decimal(dados.get('desconto', '0'))
            desconto_grosso = Decimal(dados.get('desconto_grosso', '0'))
            tipo_preco = dados.get('tipo_preco', 'normal')
            
            # 🔥 NOVO: Define qual preço usar (normal ou atacado)
            if tipo_preco == 'atacado' and produto.preco_atacado:
                preco_base = produto.preco_atacado
                modo = 'atacado'  # marca o modo para redirecionamento
            else:
                preco_base = produto.preco_venda
                modo = 'normal'
            
            # Aplica descontos: primeiro o grosso (por unidade), depois o normal (total)
            desconto_por_unidade = desconto_total / qty if qty > 0 else Decimal('0')
            preco_final_unitario = preco_base - desconto_grosso - desconto_por_unidade
            subtotal = preco_final_unitario * qty
            
            itens.append({
                'produto': produto,
                'quantidade': qty,
                'desconto': desconto_total,
                'desconto_grosso': desconto_grosso,
                'tipo_preco': tipo_preco,
                'preco_com_desconto': preco_final_unitario,
                'subtotal': subtotal
            })
            total += subtotal
            
        except Produto.DoesNotExist:
            continue

    if request.method == 'POST':
        cliente_nome = request.POST.get('cliente_nome', '').strip()
        cliente_contacto = request.POST.get('cliente_contacto', '').strip()
        nota = request.POST.get('nota', '').strip()
        metodo_pagamento = request.POST.get('metodo_pagamento')

        if not metodo_pagamento or metodo_pagamento not in dict(Venda.METODOS_PAGAMENTO):
            messages.error(request, "Selecione um método de pagamento válido.")
            return render(request, 'produtos/finalizar_venda.html', {
                'itens': itens, 'total': total, 'loja_atual': loja
            })

        try:
            with transaction.atomic():
                venda = Venda.objects.create(
                    loja=loja,
                    cliente_nome=cliente_nome,
                    cliente_contacto=cliente_contacto,
                    nota=nota,
                    metodo_pagamento=metodo_pagamento,
                )

                total_venda = Decimal('0')
                for item in itens:
                    produto = item['produto']
                    qty = item['quantidade']
                    preco_final = item['preco_com_desconto']
                    tipo_preco = item['tipo_preco']

                    # Verifica estoque
                    stock = get_object_or_404(Estoque, produto=produto, loja=loja)
                    if stock.quantidade < qty:
                        raise ValueError(f"Stock insuficiente para {produto.nome} (disponível: {stock.quantidade})")

                    stock.quantidade -= qty
                    stock.save()

                    # 🔥 NOVO: Salva o tipo_preco no ItemVenda
                    ItemVenda.objects.create(
                        venda=venda,
                        produto=produto,
                        quantidade=qty,
                        preco_unitario=preco_final,
                        tipo_preco=tipo_preco  # 🔥 NOVO
                    )
                    total_venda += qty * preco_final

                venda.total = total_venda
                venda.save()

            request.session['carrinho'] = {}
            request.session.modified = True

            messages.success(request, f"Venda #{venda.id} finalizada com {venda.get_metodo_pagamento_display()}! Total: {total_venda} MT")
            
            # 🔥 NOVO: Redireciona para o PDV correto (normal ou atacado)
            if modo == 'atacado':
                return redirect('produtos:pdv_atacado', loja_slug=loja_slug)
            else:
                return redirect('produtos:pdv', loja_slug=loja_slug)

        except Exception as e:
            messages.error(request, f"Erro ao finalizar: {str(e)}")
            return render(request, 'produtos/finalizar_venda.html', {
                'itens': itens, 'total': total, 'loja_atual': loja
            })

    context = {
        'itens': itens,
        'total': total,
        'loja_atual': loja,
    }
    return render(request, 'produtos/finalizar_venda.html', context)


# =============================================
# Gestão de Stock - Apenas Gerente e Dono
# =============================================
@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def adicionar_stock(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    estoques = Estoque.objects.filter(loja=loja).select_related('produto').order_by('produto__nome')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            produto_id = request.POST['produto']
            quantidade = int(request.POST['quantidade'])
            produto = Produto.objects.get(id=produto_id)
            estoque, created = Estoque.objects.get_or_create(
                produto=produto, loja=loja,
                defaults={'quantidade': quantidade, 'estoque_minimo': 5}
            )
            if not created:
                estoque.quantidade += quantidade
                estoque.save()
            messages.success(request, f"{quantidade} unid. de {produto.nome} adicionadas!")

        elif action == 'edit':
            try:
                estoque_id = request.POST['estoque_id']
                estoque = Estoque.objects.get(id=estoque_id, loja=loja)
                produto = estoque.produto

                # Atualizar campos do produto
                produto.nome = request.POST.get('nome', produto.nome)
                produto.codigo = request.POST.get('codigo', produto.codigo)
                
                if request.POST.get('preco_custo'):
                    produto.preco_custo = Decimal(request.POST['preco_custo'])
                if request.POST.get('preco_venda'):
                    produto.preco_venda = Decimal(request.POST['preco_venda'])
                
                # 🔥 ADICIONAR ESTE BLOCO PARA PREÇO ATACADO
                preco_atacado_str = request.POST.get('preco_atacado', '').strip()
                if preco_atacado_str == '':
                    produto.preco_atacado = None
                else:
                    produto.preco_atacado = Decimal(preco_atacado_str)
                
                produto.save()

                # Atualizar stock
                estoque.quantidade = int(request.POST['quantidade'])
                estoque.estoque_minimo = int(request.POST.get('estoque_minimo', 5))
                estoque.save()

                messages.success(request, f"✅ {produto.nome} atualizado com sucesso!")
            except Exception as e:
                messages.error(request, f"Erro ao salvar: {e}")

        elif action == 'delete':
            estoque_id = request.POST['estoque_id']
            estoque = Estoque.objects.get(id=estoque_id, loja=loja)
            nome = estoque.produto.nome
            estoque.delete()
            messages.success(request, f"🗑️ Stock de {nome} removido desta loja!")

        return redirect('produtos:adicionar_stock', loja_slug=loja_slug)

    context = {
        'produtos': Produto.objects.all(),
        'estoques': estoques,
        'loja_atual': loja,
    }
    return render(request, 'produtos/adicionar_estoque.html', context)

# =============================================
# Cadastrar Produto - Apenas Gerente e Dono
# =============================================
@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def cadastrar_produto(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)

    if request.method == 'POST':
        nome = request.POST['nome']
        codigo = request.POST.get('codigo', '')
        descricao = request.POST.get('descricao', '')
        preco_custo = Decimal(request.POST['preco_custo'])
        preco_venda = Decimal(request.POST['preco_venda'])
        
        # 🔥 NOVO: Captura o Preço a Atacado (opcional)
        preco_atacado_str = request.POST.get('preco_atacado', '').strip()
        preco_atacado = Decimal(preco_atacado_str) if preco_atacado_str else None

        # Captura a quantidade inicial
        quantidade_inicial = int(request.POST.get('quantidade_inicial', 0))

        # 1. Cria o produto com todos os campos
        produto = Produto.objects.create(
            nome=nome,
            codigo=codigo,
            descricao=descricao,
            preco_custo=preco_custo,
            preco_venda=preco_venda,
            preco_atacado=preco_atacado  # 🔥 NOVO
        )

        # 2. Se a quantidade for maior que zero, cria o estoque
        if quantidade_inicial > 0:
            Estoque.objects.create(
                produto=produto,
                loja=loja,
                quantidade=quantidade_inicial,
                estoque_minimo=5
            )
            messages.success(request, f"Produto '{nome}' cadastrado com {quantidade_inicial} unidades em estoque!")
        else:
            messages.success(request, f"Produto '{nome}' cadastrado sem estoque inicial.")

        # 3. Mensagem adicional se preço atacado foi definido
        if preco_atacado:
            messages.info(request, f"Preço a Atacado definido: {preco_atacado} MT.")

        return redirect('produtos:cadastrar_produto', loja_slug=loja_slug)

    context = {
        'loja_atual': loja,
    }
    return render(request, 'produtos/cadastrar_produto.html', context)



# ============================================================
# SERVIÇOS E MANUTENÇÃO – COM PREÇO PERSONALIZÁVEL E NOTAS
# ============================================================

@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def servicos(request, loja_slug):
    from decimal import Decimal
    loja = get_object_or_404(Loja, slug=loja_slug)
    carrinho_servico = request.session.get('carrinho_servico', {})

    # 1. Lista de serviços do catálogo
    servicos_lista = Servico.objects.all().order_by('nome')

    # 2. Carrinho de serviços (sessão)
    itens = []
    total = Decimal('0')
    for serv_id, dados in carrinho_servico.items():
        try:
            servico = Servico.objects.get(id=serv_id)
        except Servico.DoesNotExist:
            continue
        qty = dados['quantidade']
        preco = Decimal(dados.get('preco_unitario', '0'))
        notas = dados.get('notas', '')
        subtotal = qty * preco
        itens.append({
            'servico_id': serv_id,
            'servico': servico,
            'quantidade': qty,
            'preco_unitario': preco,
            'notas': notas,
            'subtotal': subtotal
        })
        total += subtotal

    # 3. Entradas ativas (não concluídas) desta loja
    from django.utils import timezone
    entradas_ativas = Entrada.objects.filter(
        servico_realizado__loja=loja,
        concluida=False
    ).select_related('servico_realizado').order_by('data_hora_levantamento_prevista')

    agora = timezone.now()
    for ent in entradas_ativas:
        if ent.data_hora_levantamento_prevista:
            delta = ent.data_hora_levantamento_prevista - agora
            ent.dias_restantes = delta.days
            ent.atrasado = delta.total_seconds() < 0
            if ent.atrasado:
                ent.multas_calculada = ent.calcular_multa()
            else:
                ent.multas_calculada = Decimal('0.00')
        else:
            ent.dias_restantes = None
            ent.atrasado = False
            ent.multas_calculada = Decimal('0.00')

    # 4. Contexto
    context = {
        'loja_atual': loja,
        'servicos': servicos_lista,
        'itens': itens,
        'total': total,
        'entradas_ativas': entradas_ativas,
    }
    return render(request, 'produtos/servicos.html', context)

@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def adicionar_servico_carrinho(request, loja_slug):
    if request.method == 'POST':
        servico_id = request.POST.get('servico_id')
        quantidade = int(request.POST.get('quantidade', 1))
        preco_personalizado = Decimal(request.POST.get('preco', '0'))
        notas = request.POST.get('notas', '')

        if preco_personalizado <= 0:
            messages.error(request, "O preço deve ser maior que zero.")
            return redirect('produtos:servicos', loja_slug=loja_slug)

        # Verifica se o serviço existe no banco
        if not Servico.objects.filter(id=servico_id).exists():
            messages.error(request, "Serviço inválido.")
            return redirect('produtos:servicos', loja_slug=loja_slug)

        carrinho_servico = request.session.get('carrinho_servico', {})

        if servico_id in carrinho_servico:
            # Atualiza: soma quantidade, substitui preço e notas (ou mantém?)
            # Para este caso, vamos substituir preço e notas pela nova entrada
            carrinho_servico[servico_id]['quantidade'] += quantidade
            carrinho_servico[servico_id]['preco_unitario'] = str(preco_personalizado)
            carrinho_servico[servico_id]['notas'] = notas
        else:
            carrinho_servico[servico_id] = {
                'quantidade': quantidade,
                'preco_unitario': str(preco_personalizado),
                'notas': notas
            }

        request.session['carrinho_servico'] = carrinho_servico
        request.session.modified = True

        messages.success(request, f"Serviço adicionado ao carrinho (preço: {preco_personalizado} MT).")
    return redirect('produtos:servicos', loja_slug=loja_slug)


@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def finalizar_servico(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    carrinho_servico = request.session.get('carrinho_servico', {})

    if not carrinho_servico:
        messages.warning(request, "Nenhum serviço no carrinho.")
        return redirect('produtos:servicos', loja_slug=loja_slug)

    if request.method == 'POST':
        cliente_nome = request.POST.get('cliente_nome', '')
        cliente_contacto = request.POST.get('cliente_contacto', '')
        nota_geral = request.POST.get('nota', '')

        # Cria o registro de serviço realizado
        servico_realizado = ServicoRealizado.objects.create(
            loja=loja,
            cliente_nome=cliente_nome,
            cliente_contacto=cliente_contacto,
            nota=nota_geral,
            total=0  # será atualizado depois
        )

        total = Decimal('0')

        for serv_id, dados in carrinho_servico.items():
            try:
                servico = Servico.objects.get(id=serv_id)
            except Servico.DoesNotExist:
                continue

            qty = dados['quantidade']
            preco = Decimal(dados.get('preco_unitario', '0'))
            notas_item = dados.get('notas', '')

            # Cria o item de serviço
            item = ItemServico.objects.create(
                servico_realizado=servico_realizado,
                servico=servico,
                quantidade=qty,
                preco_unitario=preco,
                notas=notas_item,   # campo novo
                subtotal=qty * preco
            )
            total += item.subtotal

        servico_realizado.total = total
        servico_realizado.save()

        # Limpa o carrinho
        request.session['carrinho_servico'] = {}
        request.session.modified = True

        messages.success(request, f"Serviço #{servico_realizado.id} finalizado com sucesso! Total: {total} MT.")
        return redirect('produtos:servicos', loja_slug=loja_slug)

    # GET – exibe resumo do carrinho
    itens = []
    total = Decimal('0')
    for serv_id, dados in carrinho_servico.items():
        try:
            servico = Servico.objects.get(id=serv_id)
        except Servico.DoesNotExist:
            continue
        qty = dados['quantidade']
        preco = Decimal(dados.get('preco_unitario', '0'))
        notas = dados.get('notas', '')
        subtotal = qty * preco
        itens.append({
            'servico': servico,
            'quantidade': qty,
            'preco_unitario': preco,
            'notas': notas,
            'subtotal': subtotal
        })
        total += subtotal

    context = {
        'itens': itens,
        'total': total,
        'loja_atual': loja,
    }
    return render(request, 'produtos/finalizar_servico.html', context)


@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def remover_servico_carrinho(request, loja_slug):
    if request.method == 'POST':
        servico_id = request.POST.get('servico_id')
        carrinho_servico = request.session.get('carrinho_servico', {})
        if servico_id in carrinho_servico:
            del carrinho_servico[servico_id]
            request.session['carrinho_servico'] = carrinho_servico
            request.session.modified = True
            messages.success(request, "Serviço removido do carrinho.")
    return redirect('produtos:servicos', loja_slug=loja_slug)



# =============================================
# Lista de Clientes - Permitido para Vendedor e Gerente
# =============================================
# =============================================
# Lista de Clientes - Permitido para Vendedor, Gerente e Dono
# =============================================
@login_required
@user_passes_test(lambda u: eh_vendedor_ou_dono(u) or eh_gerente_ou_dono(u), login_url='login')
def lista_clientes(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)

    # Vendas (sempre concluídas)
    vendas = Venda.objects.filter(loja=loja).order_by('-data')

    # Serviços realizados com entrada concluída
    from .models import Entrada
    servicos_concluidos = ServicoRealizado.objects.filter(
        loja=loja,
        entrada__concluida=True
    ).order_by('-data')

    registros = []

    for venda in vendas:
        registros.append({
            'tipo': 'Venda',
            'id': venda.id,
            'data': venda.data,
            'cliente_nome': venda.cliente_nome,
            'cliente_contacto': venda.cliente_contacto,
            'nota': venda.nota,
            'total': venda.total,
        })

    for servico in servicos_concluidos:
        registros.append({
            'tipo': 'Serviço',
            'id': servico.id,
            'data': servico.data,
            'cliente_nome': servico.cliente_nome,
            'cliente_contacto': servico.cliente_contacto,
            'nota': servico.nota,
            'total': servico.total,
        })

    registros.sort(key=lambda x: x['data'], reverse=True)

    context = {
        'registros': registros,
        'loja_atual': loja,
    }
    return render(request, 'produtos/lista_clientes.html', context)


# =============================================
# Relatório da Loja - Apenas Dono
# =============================================
@login_required
@user_passes_test(eh_dono, login_url='login')
def relatorio_loja(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)

    hoje = datetime.today()
    mes = int(request.GET.get('mes', hoje.month))
    ano = int(request.GET.get('ano', hoje.year))

    vendas = Venda.objects.filter(
        loja=loja,
        data__year=ano,
        data__month=mes
    ).order_by('-data')

    vendas_por_dia = {}
    for venda in vendas:
        dia = venda.data.day
        if dia not in vendas_por_dia:
            vendas_por_dia[dia] = Decimal('0')
        vendas_por_dia[dia] += venda.total

    vendas_por_dia_ordenado = dict(sorted(vendas_por_dia.items()))

    total_vendas = Decimal('0')
    total_custo_vendas = Decimal('0')
    total_descontos = Decimal('0')
    total_lucro = Decimal('0')

    detalhes_vendas = []

    for venda in vendas:
        venda_custo = Decimal('0')
        venda_desconto = Decimal('0')
        for item in venda.itens.all():
            produto = item.produto
            qty = item.quantidade
            preco_venda_original = produto.preco_venda * qty
            preco_venda_real = item.preco_unitario * qty
            desconto_item = preco_venda_original - preco_venda_real
            custo_item = produto.preco_custo * qty

            venda_custo += custo_item
            venda_desconto += desconto_item

        lucro_venda = venda.total - venda_custo

        total_vendas += venda.total
        total_custo_vendas += venda_custo
        total_descontos += venda_desconto
        total_lucro += lucro_venda

        detalhes_vendas.append({
            'venda': venda,
            'custo': venda_custo,
            'desconto': venda_desconto,
            'lucro': lucro_venda
        })

    stocks = Estoque.objects.filter(loja=loja)
    total_custo_stock = Decimal('0')
    total_venda_stock = Decimal('0')
    for stock in stocks:
        total_custo_stock += stock.produto.preco_custo * stock.quantidade
        total_venda_stock += stock.produto.preco_venda * stock.quantidade
    lucro_potencial_stock = total_venda_stock - total_custo_stock

    # GERAR PDF
    if request.GET.get('pdf'):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{loja.slug}_{mes}_{ano}.pdf"'

        doc = SimpleDocTemplate(
            response,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()
        story = []

        # Título
        story.append(Paragraph(f"Relatório Financeiro - {loja.nome}", styles['Title']))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"Período: {mes:02d}/{ano}", styles['Heading2']))
        story.append(Spacer(1, 1*cm))

        # Resumo
        resumo_data = [
            ['Descrição', 'Valor (MT)'],
            ['Total de Vendas', f"{total_vendas:,.2f}"],
            ['Custo das Vendas', f"{total_custo_vendas:,.2f}"],
            ['Descontos', f"{total_descontos:,.2f}"],
            ['Lucro', f"{total_lucro:,.2f}"],
        ]

        table_resumo = Table(resumo_data, colWidths=[10*cm, 6*cm])
        table_resumo.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FFD400')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))

        story.append(Paragraph("Resumo Financeiro", styles['Heading3']))
        story.append(table_resumo)
        story.append(Spacer(1, 1*cm))

        # Vendas por dia
        if vendas_por_dia_ordenado:
            dias_data = [['Dia', 'Total Vendido (MT)']]
            for dia, total in vendas_por_dia_ordenado.items():
                dias_data.append([f"{dia}/{mes}/{ano}", f"{total:,.2f}"])

            table_dias = Table(dias_data, colWidths=[8*cm, 8*cm])
            table_dias.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FFD400')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                ('ALIGN', (1,0), (1,-1), 'RIGHT'),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
            ]))

            story.append(Paragraph("Vendas por Dia", styles['Heading3']))
            story.append(table_dias)
            story.append(Spacer(1, 1*cm))

        # Detalhes das vendas
        if detalhes_vendas:
            vendas_data = [['Data', 'ID', 'Cliente', 'Total (MT)', 'Método']]
            for det in detalhes_vendas[:20]:
                venda = det['venda']
                metodo = venda.get_metodo_pagamento_display() or '—'
                vendas_data.append([
                    venda.data.strftime('%d/%m/%Y %H:%M'),
                    f"#{venda.id}",
                    venda.cliente_nome or "Anônimo",
                    f"{venda.total:,.2f}",
                    metodo
                ])

            table_vendas = Table(vendas_data, colWidths=[3.5*cm, 1.5*cm, 4*cm, 3*cm, 3.5*cm])
            table_vendas.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FFD400')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                ('ALIGN', (3,0), (3,-1), 'RIGHT'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ]))

            story.append(Paragraph("Detalhes das Vendas", styles['Heading3']))
            story.append(table_vendas)
        else:
            story.append(Paragraph("Nenhuma venda no período.", styles['Normal']))

        # Stock
        story.append(Spacer(1, 1*cm))
        stock_data = [
            ['Descrição', 'Valor (MT)'],
            ['Custo do Stock', f"{total_custo_stock:,.2f}"],
            ['Valor de Venda Potencial', f"{total_venda_stock:,.2f}"],
            ['Lucro Potencial', f"{lucro_potencial_stock:,.2f}"],
        ]

        table_stock = Table(stock_data, colWidths=[10*cm, 6*cm])
        table_stock.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FFD400')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
        ]))

        story.append(Paragraph("Situação do Stock", styles['Heading3']))
        story.append(table_stock)

        doc = SimpleDocTemplate(response, pagesize=A4)
        doc.build(story)
        return response

    context = {
        'loja': loja,
        'mes': mes,
        'ano': ano,
        'agora': datetime.now(),
        'total_vendas': total_vendas,
        'total_custo_vendas': total_custo_vendas,
        'total_descontos': total_descontos,
        'total_lucro': total_lucro,
        'detalhes_vendas': detalhes_vendas,
        'vendas_por_dia': vendas_por_dia_ordenado,
        'total_custo_stock': total_custo_stock,
        'total_venda_stock': total_venda_stock,
        'lucro_potencial_stock': lucro_potencial_stock,
    }
    return render(request, 'produtos/relatorio_loja.html', context)


# =============================================
# Relatório Financeiro Global - Apenas Dono
# =============================================
@login_required
@user_passes_test(eh_dono, login_url='login')
def relatorio_financeiro(request):
    try:
        loja_teste = Loja.objects.get(nome="Zimpeto 1")
    except Loja.DoesNotExist:
        messages.error(request, "Loja 'Zimpeto 1' não encontrada.")
        return redirect('dono_lista_lojas')

    vendas = Venda.objects.filter(loja=loja_teste).order_by('-data')

    total_vendas = Decimal('0')
    total_custo_vendas = Decimal('0')
    total_descontos = Decimal('0')
    total_lucro = Decimal('0')

    detalhes_vendas = []

    for venda in vendas:
        venda_custo = Decimal('0')
        venda_desconto = Decimal('0')
        for item in venda.itens.all():
            produto = item.produto
            qty = item.quantidade
            preco_venda_original = produto.preco_venda * qty
            preco_venda_real = item.preco_unitario * qty
            desconto_item = preco_venda_original - preco_venda_real
            custo_item = produto.preco_custo * qty

            venda_custo += custo_item
            venda_desconto += desconto_item

        lucro_venda = venda.total - venda_custo

        total_vendas += venda.total
        total_custo_vendas += venda_custo
        total_descontos += venda_desconto
        total_lucro += lucro_venda

        detalhes_vendas.append({
            'venda': venda,
            'custo': venda_custo,
            'desconto': venda_desconto,
            'lucro': lucro_venda
        })

    stocks = Estoque.objects.filter(loja=loja_teste)

    total_custo_stock = Decimal('0')
    total_venda_stock = Decimal('0')

    for stock in stocks:
        total_custo_stock += stock.produto.preco_custo * stock.quantidade
        total_venda_stock += stock.produto.preco_venda * stock.quantidade

    context = {
        'loja_atual': loja_teste,
        'total_vendas': total_vendas,
        'total_custo_vendas': total_custo_vendas,
        'total_descontos': total_descontos,
        'total_lucro': total_lucro,
        'detalhes_vendas': detalhes_vendas,
        'total_custo_stock': total_custo_stock,
        'total_venda_stock': total_venda_stock,
    }
    return render(request, 'produtos/relatorio_financeiro.html', context)


# =============================================
# Páginas iniciais / públicas
# =============================================
def home(request):
    lojas = Loja.objects.all().order_by('nome')
    context = {'lojas': lojas}
    return render(request, 'produtos/home.html', context)


def lista_lojas(request):
    lojas = Loja.objects.all().order_by('nome')
    context = {'lojas': lojas}
    return render(request, 'produtos/lista_lojas.html', context)


@login_required
@user_passes_test(eh_dono, login_url='login')
def dono_lista_lojas(request):
    lojas = Loja.objects.all().order_by('nome')
    context = {'lojas': lojas}
    return render(request, 'produtos/dono_lista_lojas.html', context)


# Função placeholder (mantida caso ainda use)
def nome_da_view(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)
    context = {'loja_atual': loja}
    return render(request, 'produtos/nome_do_template.html', context)


def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def pdv_atacado(request, loja_slug):
    """
    Ponto de Venda com Preço a Atacado
    """
    loja = get_object_or_404(Loja, slug=loja_slug)
    carrinho = request.session.get('carrinho', {})

    itens = []
    total = Decimal('0')
    for prod_id, dados in carrinho.items():
        try:
            produto = Produto.objects.get(id=prod_id)
            qty = dados['quantidade']
            desconto_total = Decimal(dados.get('desconto', '0'))
            desconto_grosso = Decimal(dados.get('desconto_grosso', '0'))

            # 🔥 USA O PREÇO A ATACADO (se existir)
            preco_base = produto.preco_atacado if produto.preco_atacado else produto.preco_venda
            
            # Aplica descontos
            desconto_por_unidade = desconto_total / qty if qty > 0 else Decimal('0')
            preco_final_unitario = preco_base - desconto_grosso - desconto_por_unidade
            subtotal = preco_final_unitario * qty

            itens.append({
                'produto': produto,
                'quantidade': qty,
                'desconto': desconto_total,
                'desconto_grosso': desconto_grosso,
                'preco_com_desconto': preco_final_unitario,
                'subtotal': subtotal
            })
            total += subtotal
        except Produto.DoesNotExist:
            continue

    # Busca de produtos (igual ao PDV normal)
    busca = request.GET.get('busca')
    produtos_busca = None
    if busca:
        produtos_busca = Produto.objects.filter(
            Q(nome__icontains=busca) | Q(codigo__icontains=busca),
            estoques__loja=loja
        ).distinct()
        # ⚠️ Adiciona informação se o produto tem preço atacado
        for p in produtos_busca:
            p.tem_atacado = p.preco_atacado is not None and p.preco_atacado > 0
            p.preco_exibido = p.preco_atacado if p.tem_atacado else p.preco_venda

    context = {
        'loja_atual': loja,
        'itens': itens,
        'total': total,
        'produtos_busca': produtos_busca,
        'modo': 'atacado',  # 🔥 Indica que é modo atacado
    }
    return render(request, 'produtos/pdv_atacado.html', context)

@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def gerar_inventario_pdf(request, loja_slug):
    """
    Gera um relatório PDF com o inventário simplificado da loja.
    """
    loja = get_object_or_404(Loja, slug=loja_slug)
    estoques = Estoque.objects.filter(loja=loja).select_related('produto').order_by('produto__nome')
    
    # Cria a resposta HTTP com PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="inventario_{loja.slug}_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
    
    # Configura o documento
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           rightMargin=2*cm, leftMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    style_title = styles['Title']
    style_title.alignment = TA_CENTER
    
    style_heading = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        alignment=TA_CENTER,
        fontSize=14,
        spaceAfter=12
    )
    
    style_normal = styles['Normal']
    
    style_center = ParagraphStyle(
        'Center',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=6
    )
    
    style_center_bold = ParagraphStyle(
        'CenterBold',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    story = []
    
    # ====== CABEÇALHO ======
    story.append(Paragraph("SISTEMA SRG - GESTÃO DE LOJAS", style_title))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"INVENTÁRIO DA LOJA: <b>{loja.nome.upper()}</b>", style_heading))
    story.append(Spacer(1, 0.3*cm))
    
    tz = pytz.timezone('Africa/Maputo')
    data_atual = datetime.now(tz).strftime('%d/%m/%Y às %H:%M')
    story.append(Paragraph(f"Data de geração: {data_atual}", style_normal))
    story.append(Spacer(1, 0.5*cm))
    
    # ====== TABELA (COM QUANTIDADE) ======
    if estoques:
        table_data = []
        # 🔥 NOVO CABEÇALHO: 5 colunas
        table_data.append([
            '#', 
            'Código', 
            'Produto', 
            'Venda (MT)',
            'Qtd'   # <-- NOVA COLUNA
        ])
        
        for i, estoque in enumerate(estoques, start=1):
            produto = estoque.produto
            table_data.append([
                str(i),
                produto.codigo or '—',
                produto.nome,
                f'{produto.preco_venda:.2f}',
                str(estoque.quantidade)   # <-- ADICIONADO
            ])
        
        # Ajuste das larguras para 5 colunas
        table = Table(table_data, colWidths=[1.2*cm, 2.8*cm, 5.5*cm, 3*cm, 2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FFD400')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (1,0), (1,-1), 'CENTER'),
            ('ALIGN', (3,0), (3,-1), 'RIGHT'),
            ('ALIGN', (4,0), (4,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTSIZE', (0,1), (-1,-1), 9),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 0.5*cm))
        
        # ====== TOTAL DE PRODUTOS (APENAS) ======
        total_produtos = len(estoques)
        story.append(Paragraph(f"<b>Total de Produtos:</b> {total_produtos}", style_normal))
        
    else:
        story.append(Paragraph("Nenhum produto cadastrado no stock desta loja.", style_normal))
    
    # ====== ASSINATURAS ======
    story.append(Spacer(1, 1.5*cm))
    story.append(PageBreak())
    
    story.append(Paragraph("TERMO DE RESPONSABILIDADE DO INVENTÁRIO", style_title))
    story.append(Spacer(1, 0.5*cm))
    
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Declaro que confiro a veracidade das informações contidas neste inventário, assumindo total", style_center))
    story.append(Paragraph("responsabilidade pelos dados apresentados.", style_center))
    story.append(Spacer(1, 1*cm))
    
    story.append(Paragraph("___________________________________________", style_center))
    story.append(Paragraph("<b>Assinatura do Vendedor</b>", style_center_bold))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Nome: ______________________________", style_center))
    story.append(Spacer(1, 0.8*cm))
    
    story.append(Paragraph("___________________________________________", style_center))
    story.append(Paragraph("<b>Assinatura do Gerente</b>", style_center_bold))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Nome: ______________________________", style_center))
    story.append(Spacer(1, 0.8*cm))
    
    story.append(Paragraph("Data: ___/___/_____", style_center))
    story.append(Spacer(1, 1*cm))
    
    # ====== RODAPÉ ======
    story.append(Paragraph("Documento gerado Sistema SRG.", style_center))
    story.append(Paragraph(f"Data de impressão: {data_atual}", style_center))
    
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


# ============================================================
# GESTÃO DE ENTRADAS (com horas e multa)
# ============================================================

# ============================================================
# GESTÃO DE ENTRADAS (com dias e multa)
# ============================================================
@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def registar_entrada(request, loja_slug):
    loja = get_object_or_404(Loja, slug=loja_slug)

    if request.method == 'POST':
        cliente_nome = request.POST.get('cliente_nome', '').strip()
        cliente_contacto = request.POST.get('cliente_contacto', '').strip()
        estado_aparelho = request.POST.get('estado_aparelho', '').strip()
        pecas_substituir = request.POST.get('pecas_substituir', '').strip()
        dias_reparacao = request.POST.get('dias_reparacao', '1')
        observacoes = request.POST.get('observacoes', '').strip()

        # 🔥 Campos de comissão
        comissionado = request.POST.get('comissionado') == 'on'
        tipo_comissao = request.POST.get('tipo_comissao', '').strip()
        origem_pecas = request.POST.get('origem_pecas', '').strip()
        detalhes_comissao = request.POST.get('detalhes_comissao', '').strip()

        # 🔥 NOVOS CAMPOS – valores separados
        valor_pecas_srg_str = request.POST.get('valor_pecas_srg', '0').strip()
        valor_pecas_externa_str = request.POST.get('valor_pecas_externa', '0').strip()

        # Se não for comissionado, limpar campos extras
        if not comissionado:
            tipo_comissao = ''
            origem_pecas = ''
            detalhes_comissao = ''
            valor_pecas_srg_str = '0'
            valor_pecas_externa_str = '0'

        # --- Validações ---
        if not cliente_nome:
            messages.error(request, "O nome do cliente é obrigatório.")
            return redirect('produtos:registar_entrada', loja_slug=loja_slug)

        # 🔥 Origem é obrigatória se comissionado
        if comissionado and not origem_pecas:
            messages.error(request, "Por favor, indique a loja de origem das peças.")
            return redirect('produtos:registar_entrada', loja_slug=loja_slug)

        # Validar valores
        try:
            valor_pecas_srg = Decimal(valor_pecas_srg_str)
            if valor_pecas_srg < 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Valor das peças da SRG inválido. Deve ser um número positivo.")
            return redirect('produtos:registar_entrada', loja_slug=loja_slug)

        try:
            valor_pecas_externa = Decimal(valor_pecas_externa_str)
            if valor_pecas_externa < 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Valor das peças externas inválido. Deve ser um número positivo.")
            return redirect('produtos:registar_entrada', loja_slug=loja_slug)

        # Validar dias
        try:
            dias = int(dias_reparacao)
            if dias < 1:
                raise ValueError
        except ValueError:
            messages.error(request, "Dias de reparação inválidos. Deve ser um número inteiro positivo.")
            return redirect('produtos:registar_entrada', loja_slug=loja_slug)

        # Criar ServicoRealizado
        servico_realizado = ServicoRealizado.objects.create(
            loja=loja,
            cliente_nome=cliente_nome,
            cliente_contacto=cliente_contacto,
            nota=observacoes,
            total=0
        )

        # Criar Entrada (o save() calcula custo_pecas automaticamente)
        entrada = Entrada.objects.create(
            servico_realizado=servico_realizado,
            estado_aparelho=estado_aparelho,
            pecas_substituir=pecas_substituir,
            custo_pecas=Decimal('0.00'),  # será sobrescrito no save()
            margem=Decimal('0.00'),
            dias_reparacao=dias,
            multa_diaria=100.00,
            comissionado=comissionado,
            tipo_comissao=tipo_comissao,
            origem_pecas=origem_pecas,
            detalhes_comissao=detalhes_comissao,
            valor_pecas_srg=valor_pecas_srg,          # 🔥 NOVO
            valor_pecas_externa=valor_pecas_externa   # 🔥 NOVO
        )

        prevista = entrada.data_hora_levantamento_prevista
        prevista_str = prevista.strftime('%d/%m/%Y %H:%M') if prevista else 'não definida'

        messages.success(
            request,
            f"✅ Entrada registada com sucesso!\n"
            f"Cliente: {cliente_nome}\n"
            f"📅 Entrada: {entrada.data_entrada.strftime('%d/%m/%Y %H:%M')}\n"
            f"⏱️ Previsão: {prevista_str}\n"
            f"💰 Custo total: {entrada.custo_pecas} MT\n"
            f"{'🔄 Comissionado' if comissionado else ''}\n"
            f"⚠️ Multa diária após o prazo: {entrada.multa_diaria} MT/dia"
        )
        return redirect('produtos:servicos', loja_slug=loja_slug)

    context = {'loja_atual': loja}
    return render(request, 'produtos/registar_entrada.html', context)

@login_required
@user_passes_test(eh_vendedor_ou_dono, login_url='login')
def finalizar_entrada(request, loja_slug, entrada_id):
    loja = get_object_or_404(Loja, slug=loja_slug)
    entrada = get_object_or_404(Entrada, id=entrada_id, servico_realizado__loja=loja)

    multa_atual = entrada.calcular_multa()

    if request.method == 'POST':
        total_servico = Decimal(request.POST.get('total_servico', '0'))
        nota_conclusao = request.POST.get('nota_conclusao', '').strip()

        # 🔥 Calcular a margem
        margem = total_servico - entrada.custo_pecas

        servico = entrada.servico_realizado
        servico.total = total_servico + multa_atual
        servico.nota = nota_conclusao
        servico.save()

        entrada.concluida = True
        entrada.multa_total = multa_atual
        entrada.nota_conclusao = nota_conclusao
        entrada.margem = margem           # 🔥 Guardar a margem
        entrada.save()

        messages.success(
            request,
            f"✅ Entrada #{entrada.id} finalizada!\n"
            f"Serviço: {total_servico} MT\n"
            f"Custo peças: {entrada.custo_pecas} MT\n"
            f"Margem: {margem} MT\n"
            f"Multa: {multa_atual} MT\n"
            f"Total: {servico.total} MT"
        )
        return redirect('produtos:servicos', loja_slug=loja_slug)

    context = {
        'loja_atual': loja,
        'entrada': entrada,
        'multa_atual': multa_atual,
    }
    return render(request, 'produtos/finalizar_entrada.html', context)


    
@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def relatoriovendas_gerente(request, loja_slug):
    from datetime import datetime
    from decimal import Decimal
    from django.utils import timezone
    from django.db.models import Sum

    loja = get_object_or_404(Loja, slug=loja_slug)

    local_tz = timezone.get_current_timezone()
    hoje_local = timezone.now().astimezone(local_tz).date()

    mes = int(request.GET.get('mes', hoje_local.month))
    ano = int(request.GET.get('ano', hoje_local.year))

    inicio = datetime(ano, mes, 1, 0, 0, 0, tzinfo=local_tz)
    if mes == 12:
        fim = datetime(ano+1, 1, 1, 0, 0, 0, tzinfo=local_tz)
    else:
        fim = datetime(ano, mes+1, 1, 0, 0, 0, tzinfo=local_tz)

    # ---------- Vendas ----------
    vendas = Venda.objects.filter(loja=loja, data__gte=inicio, data__lt=fim).order_by('-data')
    total_vendas = vendas.aggregate(total=Sum('total'))['total'] or Decimal('0')

    vendas_com_itens = []
    for venda in vendas:
        itens = venda.itens.all()
        produtos_nomes = [item.produto.nome for item in itens]
        vendas_com_itens.append({
            'venda': venda,
            'produtos': ', '.join(produtos_nomes) if produtos_nomes else '—'
        })

    # ---------- Serviços ----------
    servicos = ServicoRealizado.objects.filter(
        loja=loja,
        data__gte=inicio,
        data__lt=fim,
        entrada__concluida=True
    ).order_by('-data')

    total_servicos = servicos.aggregate(total=Sum('total'))['total'] or Decimal('0')

    # 🔥 Acumuladores
    total_custo_pecas = Decimal('0')
    total_margem = Decimal('0')

    servicos_com_itens = []
    for servico in servicos:
        itens = servico.itens.all()
        servicos_nomes = [item.servico.nome for item in itens]
        
        # 🔥 Buscar a entrada associada para obter todos os campos
        try:
            entrada = servico.entrada
            custo_pecas = entrada.custo_pecas
            margem = entrada.margem
            comissionado = entrada.comissionado
            tipo_comissao = entrada.tipo_comissao or ''
            origem_pecas = entrada.origem_pecas or ''
            detalhes_comissao = entrada.detalhes_comissao or ''
        except Entrada.DoesNotExist:
            custo_pecas = Decimal('0.00')
            margem = Decimal('0.00')
            comissionado = False
            tipo_comissao = ''
            origem_pecas = ''
            detalhes_comissao = ''

        total_custo_pecas += custo_pecas
        total_margem += margem

        servicos_com_itens.append({
            'servico': servico,
            'servicos_nomes': ', '.join(servicos_nomes) if servicos_nomes else '—',
            'custo_pecas': custo_pecas,
            'margem': margem,
            'comissionado': comissionado,         # 🔥 NOVO
            'tipo_comissao': tipo_comissao,       # 🔥 NOVO
            'origem_pecas': origem_pecas,         # 🔥 NOVO
            'detalhes_comissao': detalhes_comissao # 🔥 NOVO
        })

    total_geral = total_vendas + total_servicos

    meses = list(range(1, 13))
    anos = list(range(2023, hoje_local.year + 1))

    # ---------- PDF ----------
    if request.GET.get('pdf'):
        return gerar_pdf_gerente(
            loja,
            vendas_com_itens,
            servicos_com_itens,
            total_vendas,
            total_servicos,
            total_custo_pecas,
            total_margem,
            total_geral,
            mes,
            ano
        )

    context = {
        'loja_atual': loja,
        'vendas_com_itens': vendas_com_itens,
        'servicos_com_itens': servicos_com_itens,
        'total_vendas': total_vendas,
        'total_servicos': total_servicos,
        'total_custo_pecas': total_custo_pecas,
        'total_margem': total_margem,
        'total_geral': total_geral,
        'mes': mes,
        'ano': ano,
        'meses': meses,
        'anos': anos,
    }
    return render(request, 'produtos/relatoriovendas_gerente.html', context)

def gerar_pdf_gerente(loja, vendas_com_itens, servicos_com_itens, total_vendas, total_servicos, total_custo_pecas, total_margem, total_geral, mes, ano):
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="relatorio_vendas_gerente_{loja.slug}_{mes}_{ano}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('Title', parent=styles['Title'], alignment=TA_CENTER, fontSize=16, spaceAfter=12)
    story.append(Paragraph(f"Relatório de Vendas e Serviços - {loja.nome}", title_style))
    story.append(Paragraph(f"Mês: {mes:02d}/{ano}", styles['Heading2']))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph(f"Total Vendas: {total_vendas:,.2f} MT", styles['Normal']))
    story.append(Paragraph(f"Total Serviços: {total_servicos:,.2f} MT", styles['Normal']))
    story.append(Paragraph(f"Custo Total de Peças: {total_custo_pecas:,.2f} MT", styles['Normal']))
    story.append(Paragraph(f"Margem Total: {total_margem:,.2f} MT", styles['Normal']))
    story.append(Paragraph(f"Total Geral: {total_geral:,.2f} MT", styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    # ---------- Tabela Vendas ----------
    if vendas_com_itens:
        data_v = [['Data', 'Produto(s)', 'Método', 'Valor (MT)']]
        for item in vendas_com_itens[:100]:
            v = item['venda']
            data_v.append([
                v.data.strftime('%d/%m/%Y %H:%M'),
                item['produtos'][:60],
                v.get_metodo_pagamento_display(),
                f"{v.total:,.2f}"
            ])
        table_v = Table(data_v, colWidths=[3.5*cm, 5.5*cm, 2.5*cm, 2.5*cm])
        table_v.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6c63ff')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (3,0), (3,-1), 'RIGHT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(Paragraph("Vendas Realizadas", styles['Heading3']))
        story.append(table_v)
        story.append(Spacer(1, 0.5*cm))

    # ---------- Tabela Serviços (com custo, margem e comissão) ----------
    if servicos_com_itens:
        data_s = [['Data', 'Cliente', 'Serviço(s)', 'Estado', 'Comissão', 'Custo Peças (MT)', 'Valor (MT)', 'Margem (MT)']]
        for item in servicos_com_itens[:100]:
            s = item['servico']
            estado = s.entrada.estado_aparelho if hasattr(s, 'entrada') and s.entrada else '—'
            
            # Construir texto da comissão
            comissao_texto = 'Não'
            if item.get('comissionado'):
                tipo = item.get('tipo_comissao', '')
                origem = item.get('origem_pecas', '')
                if tipo == 'total':
                    comissao_texto = f"Total ({origem})" if origem else "Total"
                elif tipo == 'parcial':
                    comissao_texto = f"Parcial ({origem})" if origem else "Parcial"
                else:
                    comissao_texto = "Sim"
            
            data_s.append([
                s.data.strftime('%d/%m/%Y %H:%M'),
                s.cliente_nome or 'Anónimo',
                item['servicos_nomes'][:60],
                estado[:30],
                comissao_texto,  # 🔥 NOVA COLUNA
                f"{item['custo_pecas']:,.2f}",
                f"{s.total:,.2f}",
                f"{item['margem']:,.2f}"
            ])
        table_s = Table(data_s, colWidths=[2.5*cm, 2.5*cm, 2.8*cm, 2.0*cm, 2.2*cm, 2.0*cm, 2.0*cm, 2.0*cm])
        table_s.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#28a745')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (5,0), (7,-1), 'RIGHT'),  # Alinhar à direita colunas de números
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(Paragraph("Serviços Realizados", styles['Heading3']))
        story.append(table_s)

    doc.build(story)
    return response

@login_required
@user_passes_test(eh_gerente_ou_dono, login_url='login')
def reverter_venda(request, loja_slug, venda_id):
    # Apenas POST
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    try:
        venda = Venda.objects.get(id=venda_id, loja__slug=loja_slug)
    except Venda.DoesNotExist:
        return JsonResponse({'erro': 'Venda não encontrada.'}, status=404)

    # Prazo de 48 horas
    horas_passadas = (timezone.now() - venda.data).total_seconds() / 3600
    if horas_passadas > 48:
        return JsonResponse({
            'erro': f'Prazo de 48 horas expirado. Venda de {venda.data.strftime("%d/%m/%Y %H:%M")}.'
        }, status=400)

    try:
        # Reverter stock
        for item in venda.itens.all():
            estoque, created = Estoque.objects.get_or_create(
                produto=item.produto,
                loja=venda.loja,
                defaults={'quantidade': 0}
            )
            estoque.quantidade += item.quantidade
            estoque.save()

        # Eliminar itens e venda
        venda.itens.all().delete()
        venda.delete()

        return JsonResponse({
            'sucesso': True,
            'mensagem': 'Venda revertida com sucesso! Stock atualizado.'
        })

    except Exception as e:
        return JsonResponse({
            'erro': f'Erro interno: {str(e)}'
        }, status=500)


