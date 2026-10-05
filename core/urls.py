from django.contrib import admin
from django.urls import path, include
from produtos.views import home, login_view, dashboard_loja, dono_lista_lojas, relatorio_loja
from django.contrib.auth import views as auth_views
from produtos import views 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('loja/<slug:loja_slug>/', dashboard_loja, name='dashboard_loja'),
    path('loja/<slug:loja_slug>/relatorio/', relatorio_loja, name='relatorio_loja'),
    path('dono_lista/', dono_lista_lojas, name='dono_lista_lojas'),
    path('pdv/', include('produtos.urls')),  # <-- aqui
     path('logout/', views.logout_view, name='logout'), 
]