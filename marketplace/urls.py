from django.urls import path

from . import views

app_name = 'marketplace'

urlpatterns = [
    path('webhooks/<str:provider>', views.payment_webhook, name='payment_webhook'),
]
