from django.db import models
from lojas.models import Loja
from django.conf import settings

class Produto(models.Model):
    codigo = models.CharField("Código/Barcode", max_length=50, unique=True, blank=True, null=True)
    nome = models.CharField("Nome do Produto", max_length=200)
    descricao = models.TextField("Descrição", blank=True)
    preco_custo = models.DecimalField("Preço de Custo", max_digits=10, decimal_places=2, default=0)
    preco_venda = models.DecimalField("Preço de Venda", max_digits=10, decimal_places=2, default=0)
    
    # Preço a Atacado (opcional)
    preco_atacado = models.DecimalField(
        "Preço a Atacado",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Deixe em branco se o produto não tiver preço de atacado."
    )
    
    imagem = models.ImageField("Imagem", upload_to='produtos/', blank=True, null=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['nome']


class EstoqueQuerySet(models.QuerySet):
    def para_usuario_loja(self, loja):
        if loja is None:
            return self.all()
        return self.filter(loja=loja)


class Estoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='estoques')
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField("Quantidade", default=0)
    estoque_minimo = models.PositiveIntegerField("Estoque Mínimo", default=5)

    objects = EstoqueQuerySet.as_manager()

    class Meta:
        unique_together = ('produto', 'loja')
        verbose_name = "Estoque"
        verbose_name_plural = "Estoque"

    def __str__(self):
        return f"{self.produto.nome} - {self.loja.nome} ({self.quantidade} un)"

    def abaixo_minimo(self):
        return self.quantidade < self.estoque_minimo
    abaixo_minimo.boolean = True
    abaixo_minimo.short_description = "Abaixo do mínimo"


class Venda(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT)
    data = models.DateTimeField(auto_now_add=True)
    cliente_nome = models.CharField("Nome do Cliente", max_length=100, blank=True)
    cliente_contacto = models.CharField("Contacto", max_length=20, blank=True)
    nota = models.TextField("Nota", blank=True)
    total = models.DecimalField("Total", max_digits=10, decimal_places=2, default=0)

    METODOS_PAGAMENTO = [
        ('numerario', 'Numerário'),
        ('mpesa', 'M-Pesa'),
        ('emola', 'Emola'),
        ('pos', 'POS / Cartão'),
    ]
    metodo_pagamento = models.CharField(
        max_length=20,
        choices=METODOS_PAGAMENTO,
        default='numerario',
        verbose_name="Método de Pagamento"
    )

    def __str__(self):
        return f"Venda {self.id} - {self.loja.nome} - {self.data.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        ordering = ['-data']
        verbose_name = "Venda"
        verbose_name_plural = "Vendas"


class ItemVenda(models.Model):
    TIPO_PRECO_CHOICES = [
        ('normal', 'Normal'),
        ('atacado', 'Atacado'),
    ]
    tipo_preco = models.CharField(
        max_length=10,
        choices=TIPO_PRECO_CHOICES,
        default='normal',
        verbose_name="Tipo de Preço"
    )
    
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantidade * self.preco_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantidade} x {self.produto.nome} ({self.get_tipo_preco_display()})"


# ------------------------------------------------------------
# SERVIÇOS – AGORA COM PREÇO PERSONALIZÁVEL PELO VENDEDOR
# ------------------------------------------------------------

class Servico(models.Model):
    """
    Catálogo de serviços disponíveis.
    O preço aqui é apenas uma sugestão (opcional).
    O valor real será definido no ItemServico pelo vendedor.
    """
    nome = models.CharField("Nome do Serviço", max_length=200)
    preco_sugerido = models.DecimalField(
        "Preço Sugerido",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor opcional apenas como referência. O vendedor definirá o preço final."
    )
    descricao = models.TextField("Descrição", blank=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"


class ServicoRealizado(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT)
    data = models.DateTimeField(auto_now_add=True)
    cliente_nome = models.CharField("Nome do Cliente", max_length=100, blank=True)
    cliente_contacto = models.CharField("Contacto", max_length=20, blank=True)
    nota = models.TextField("Nota", blank=True)
    total = models.DecimalField("Total", max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Serviço {self.id} - {self.loja.nome} - {self.data.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        ordering = ['-data']
        verbose_name = "Serviço Realizado"
        verbose_name_plural = "Serviços Realizados"


class ItemServico(models.Model):
    """
    Cada item de um serviço realizado.
    O preço_unitario é definido pelo vendedor no momento da venda.
    O campo notas guarda detalhes específicos (ex: modelo do telemóvel, peça trocada, etc.)
    """
    servico_realizado = models.ForeignKey(ServicoRealizado, on_delete=models.CASCADE, related_name='itens')
    servico = models.ForeignKey(Servico, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Valor cobrado por este serviço (definido pelo vendedor)."
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    # 🔥 NOVO CAMPO – Notas específicas do serviço prestado
    notas = models.TextField(
        "Notas do serviço",
        blank=True,
        help_text="Ex: modelo do aparelho, peça substituída, observações importantes."
    )

    def save(self, *args, **kwargs):
        self.subtotal = self.quantidade * self.preco_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantidade} x {self.servico.nome} - {self.preco_unitario} MT"


class PerfilUsuario(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.user.username} - {self.loja.nome}"


class Entrada(models.Model):
    servico_realizado = models.OneToOneField(
        'ServicoRealizado',
        on_delete=models.CASCADE,
        related_name='entrada',
        verbose_name="Serviço Realizado"
    )
    estado_aparelho = models.TextField(
        "Estado do Aparelho",
        blank=True,
        help_text="Descreva o estado do aparelho (ex: ecrã partido, bateria inchada, etc.)"
    )
    # 🔥 Campo – Peças/Acessórios a substituir (descrição)
    pecas_substituir = models.TextField(
        "Peças/Acessórios a substituir",
        blank=True,
        help_text="Liste as peças ou acessórios que precisam ser trocados (ex: bateria, ecrã, conector)."
    )
    # 🔥 NOVO CAMPO – Custo total das peças utilizadas (calculado automaticamente)
    custo_pecas = models.DecimalField(
        "Custo total das peças (MT)",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Valor total gasto com as peças para esta reparação (calculado automaticamente)."
    )
    # 🔥 NOVO CAMPO – Margem (calculada automaticamente na finalização)
    margem = models.DecimalField(
        "Margem (MT)",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Diferença entre o valor cobrado e o custo das peças (calculado automaticamente)."
    )
    # 🔥 NOVO CAMPO – Serviço comissionado (booleano)
    comissionado = models.BooleanField(
        "Serviço comissionado",
        default=False,
        help_text="Marque se este serviço foi realizado com peças adquiridas noutra loja."
    )

    # 🔥 NOVOS CAMPOS PARA COMISSÃO (detalhada)
    TIPO_COMISSAO_CHOICES = [
        ('total', 'Total – todas as peças foram buscadas'),
        ('parcial', 'Parcial – algumas peças buscadas'),
    ]

    tipo_comissao = models.CharField(
        "Tipo de Comissão",
        max_length=10,
        choices=TIPO_COMISSAO_CHOICES,
        blank=True,
        null=True,
        help_text="Preencher apenas se o serviço for comissionado."
    )
    origem_pecas = models.CharField(
        "Loja de Origem",
        max_length=200,
        blank=True,
        help_text="Ex: Loja do Ivan, Armazém Central, etc."
    )
    detalhes_comissao = models.TextField(
        "Detalhes da Comissão",
        blank=True,
        help_text="Ex: ecrã já existia, bateria buscada fora."
    )

    # 🔥 NOVOS CAMPOS PARA VALORES SEPARADOS
    valor_pecas_srg = models.DecimalField(
        "Valor das peças da SRG (MT)",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Valor das peças que já existiam na SRG (preencher apenas se comissão parcial)."
    )
    valor_pecas_externa = models.DecimalField(
        "Valor das peças compradas fora (MT)",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Valor das peças compradas noutra loja (preencher se comissão total ou parcial)."
    )

    data_entrada = models.DateTimeField(
        "Data de Entrada",
        auto_now_add=True
    )
    dias_reparacao = models.PositiveIntegerField(
        "Dias estimados para reparação",
        default=1,
        help_text="Número de dias que o equipamento ficará em reparação."
    )
    data_hora_levantamento_prevista = models.DateTimeField(
        "Data/Hora prevista de levantamento",
        blank=True,
        null=True,
        help_text="Calculado automaticamente com base nos dias de reparação."
    )
    multa_diaria = models.DecimalField(
        "Multa diária por atraso (MT)",
        max_digits=10,
        decimal_places=2,
        default=100.00
    )
    multa_total = models.DecimalField(
        "Multa total acumulada",
        max_digits=10,
        decimal_places=2,
        default=0.00
    )
    concluida = models.BooleanField(
        "Concluída",
        default=False,
        help_text="Marque como True quando a reparação for finalizada."
    )
    nota_conclusao = models.TextField(
        "Nota de Conclusão",
        blank=True,
        help_text="Observações sobre a conclusão do serviço."
    )

    def save(self, *args, **kwargs):
        from django.utils import timezone

        # 🔥 LÓGICA DE CÁLCULO DO CUSTO TOTAL DAS PEÇAS
        if self.comissionado:
            if self.tipo_comissao == 'total':
                # Comissão total: custo = valor externo
                self.custo_pecas = self.valor_pecas_externa
            elif self.tipo_comissao == 'parcial':
                # Comissão parcial: custo = SRG + externo
                self.custo_pecas = self.valor_pecas_srg + self.valor_pecas_externa
            else:
                # Caso raro: comissionado sem tipo definido -> usa externo
                self.custo_pecas = self.valor_pecas_externa
        else:
            # Não comissionado: custo = valor das peças da SRG (campo manual)
            # Mantém o valor que o utilizador inseriu (já está em self.custo_pecas)
            pass

        # 🔥 CÁLCULO DA DATA/HORA PREVISTA (já existente)
        if not self.data_hora_levantamento_prevista and self.dias_reparacao:
            if not self.data_entrada:
                self.data_entrada = timezone.now()
            self.data_hora_levantamento_prevista = self.data_entrada + timezone.timedelta(days=self.dias_reparacao)

        super().save(*args, **kwargs)

    def calcular_multa(self):
        from django.utils import timezone
        from decimal import Decimal
        if not self.data_hora_levantamento_prevista or self.concluida:
            return Decimal('0.00')
        agora = timezone.now()
        if agora <= self.data_hora_levantamento_prevista:
            return Decimal('0.00')
        delta = agora - self.data_hora_levantamento_prevista
        dias_atraso = delta.days
        if delta.seconds > 0:
            dias_atraso += 1
        return Decimal(dias_atraso) * self.multa_diaria

    def __str__(self):
        return f"Entrada #{self.id} - {self.servico_realizado.cliente_nome}"

    class Meta:
        verbose_name = "Entrada"
        verbose_name_plural = "Entradas"
        ordering = ['-data_entrada']

class ReversaoVenda(models.Model):
    venda_id = models.IntegerField("ID da Venda Original")
    data_reversao = models.DateTimeField(auto_now_add=True)
    utilizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    motivo = models.TextField("Motivo da Reversão", blank=True)
    itens = models.JSONField("Itens Revertidos", default=dict)
    total_revertido = models.DecimalField("Total Revertido", max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Reversão da Venda #{self.venda_id} - {self.data_reversao.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        verbose_name = "Reversão de Venda"
        verbose_name_plural = "Reversões de Vendas"
        ordering = ['-data_reversao']