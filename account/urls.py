
from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    path('login_fa', views.user_login_fa, name="login_fa"),
    path('logout_fa', views.user_logout_fa, name="logout_fa"),
    path('register_fa', views.user_register_fa, name="register_fa"),
    path('verify_email_fa', views.verify_email_fa, name="verify_email_fa"),
    path('profile_account_fa', views.profile_account_fa, name="profile_account_fa"),
    path('profile_dataset_fa', views.profile_dataset_fa, name="profile_dataset_fa"),
    path('profile_product_fa', views.profile_product_fa, name="profile_product_fa"),
    path('profile_marketplace_fa', views.profile_marketplace_fa, name="profile_marketplace_fa"),
    path("403_fa", views.custom_permission_denied, {"exception": None}),
    path("404_fa", views.custom_page_not_found, {"exception": None}),
]

