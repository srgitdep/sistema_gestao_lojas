from django.urls import path
from . import views

app_name = 'produtos'

urlpatterns = [
    # 🔥 NOVO: PDV Atacado (deve vir ANTES da rota genérica)
    path('<slug:loja_slug>/atacado/', views.pdv_atacado, name='pdv_atacado'),
    
    # PDV Normal
    path('<slug:loja_slug>/', views.pdv, name='pdv'),
    
    # Carrinho
    path('<slug:loja_slug>/adicionar/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('<slug:loja_slug>/limpar/', views.limpar_carrinho, name='limpar_carrinho'),
    path('<slug:loja_slug>/finalizar/', views.finalizar_venda, name='finalizar_venda'),
    path('<slug:loja_slug>/editar_desconto/', views.editar_desconto, name='editar_desconto'),

    # Gestão de Stock e Produtos
    path('<slug:loja_slug>/adicionar_stock/', views.adicionar_stock, name='adicionar_stock'),
    path('<slug:loja_slug>/cadastrar_produto/', views.cadastrar_produto, name='cadastrar_produto'),

    # Clientes
    path('<slug:loja_slug>/clientes/', views.lista_clientes, name='lista_clientes'),

    # Serviços
    path('<slug:loja_slug>/servicos/', views.servicos, name='servicos'),
    path('<slug:loja_slug>/servicos/adicionar/', views.adicionar_servico_carrinho, name='adicionar_servico_carrinho'),
    path('<slug:loja_slug>/servicos/finalizar/', views.finalizar_servico, name='finalizar_servico'),
    path('<slug:loja_slug>/servicos/remover/', views.remover_servico_carrinho, name='remover_servico_carrinho'),
    
    # (rota redundante, pode ser removida se não for usada)
    path('adicionar_stock/<slug:loja_slug>/', views.adicionar_stock, name='adicionar_stock'),
    
    # Dashboard Gerente
    path('<slug:loja_slug>/dashboard_gerente/', views.dashboard_gerente, name='dashboard_gerente'),
    path('<slug:loja_slug>/inventario/', views.gerar_inventario_pdf, name='gerar_inventario_pdf'),


    path('<slug:loja_slug>/entradas/registar/', views.registar_entrada, name='registar_entrada'),
    path('<slug:loja_slug>/entradas/finalizar/<int:entrada_id>/', views.finalizar_entrada, name='finalizar_entrada'),

    path('<slug:loja_slug>/relatorio-vendas/', views.relatoriovendas_gerente, name='relatoriovendas_gerente'),

    path('<slug:loja_slug>/reverter-venda/<int:venda_id>/', views.reverter_venda, name='reverter_venda'),

    

    
]