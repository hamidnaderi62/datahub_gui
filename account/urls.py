
from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    path('login_fa', views.user_login_fa, name="login_fa"),
    path('logout_fa', views.user_logout_fa, name="logout_fa"),
    path('register_fa', views.user_register_fa, name="register_fa"),
    path('profile_account_fa', views.profile_account_fa, name="profile_account_fa"),
    path('profile_dataset_fa', views.profile_dataset_fa, name="profile_dataset_fa")
]

