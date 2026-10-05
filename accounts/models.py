from django.contrib.auth.models import AbstractUser
from django.db import models
from lojas.models import Loja

class CustomUser(AbstractUser):
    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Loja Pertencente",
        help_text="Deixe vazio para ver todas as lojas (administrador)"
    )
    telefone = models.CharField("Telefone", max_length=20, blank=True)

    def __str__(self):
        if self.loja:
            return f"{self.username} - {self.loja.nome}"
        return f"{self.username} (Todas as lojas)"

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        ordering = ['username']