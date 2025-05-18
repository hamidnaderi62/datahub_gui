from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from . import settings

app_name = "datahub_gui"
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include("home.urls")),
    path('account/', include('account.urls', namespace='account')),
    path('dataset/', include('dataset.urls', namespace='dataset')),

    path("pygwalker/", include("djangoaddicts.pygwalker.urls"), ),



]
handler404 = "account.views.custom_page_not_found"
handler403 = "account.views.custom_permission_denied"

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

