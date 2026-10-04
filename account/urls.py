
from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    path('login', views.user_login_fa, name="login"),
    path('logout', views.user_logout_fa, name="logout"),
    path('register', views.user_register_fa, name="register"),
    path('verify-email/<uidb64>/<token>/', views.verify_email_fa, name="verify_email"),
    path('profile_account', views.profile_account_fa, name="profile_account"),
    path('profile_dataset', views.profile_dataset_fa, name="profile_dataset"),
    path('profile_product', views.profile_product_fa, name="profile_product"),
    path('profile_marketplace', views.profile_marketplace_fa, name="profile_marketplace"),
    path("403", views.custom_permission_denied, {"exception": None}, name="403"),
    path("404", views.custom_page_not_found, {"exception": None}, name="404"),

    # Legacy account URLs.
    path('login_fa', views.user_login_fa, name="login_fa"),
    path('logout_fa', views.user_logout_fa, name="logout_fa"),
    path('register_fa', views.user_register_fa, name="register_fa"),
    path('verify-email/<uidb64>/<token>/', views.verify_email_fa, name="verify_email_fa"),
    path('profile_account_fa', views.profile_account_fa, name="profile_account_fa"),
    path('profile_dataset_fa', views.profile_dataset_fa, name="profile_dataset_fa"),
    path('profile_product_fa', views.profile_product_fa, name="profile_product_fa"),
    path('profile_marketplace_fa', views.profile_marketplace_fa, name="profile_marketplace_fa"),
    path("403_fa", views.custom_permission_denied, {"exception": None}),
    path("404_fa", views.custom_page_not_found, {"exception": None}),
]

