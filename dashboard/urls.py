from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('datasets/', views.datasets, name='datasets'),
    path('datasets/<int:dataset_id>/status/', views.dataset_status, name='dataset_status'),
    path('users/', views.users, name='users'),
    path('users/<int:user_id>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),
    path('orders/', views.orders, name='orders'),
    path('imports/', views.imports, name='imports'),
    path('imports/<uuid:request_id>/status/', views.import_status, name='import_status'),
]
