
from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    # path('', views.home, name="home"),
    path('', views.home_fa, name="home"),
    # Legacy URL name retained while resolving to the same canonical home path.
    path('', views.home_fa, name="home_fa"),

]

