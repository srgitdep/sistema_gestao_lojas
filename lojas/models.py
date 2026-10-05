from django.db import models
from django.utils.text import slugify

class Loja(models.Model):
    nome = models.CharField("Nome da Loja", max_length=100, unique=True)
    slug = models.SlugField("Slug", max_length=100, unique=True, blank=True)
    endereco = models.CharField("Endereço", max_length=200, blank=True)
    telefone = models.CharField("Telefone", max_length=20, blank=True)
    cidade = models.CharField("Cidade", max_length=100, default="Maputo")
    data_criacao = models.DateTimeField("Data de Criação", auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.nome)
            slug = base_slug
            counter = 1
            while Loja.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"
        ordering = ['nome']