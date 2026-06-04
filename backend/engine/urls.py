from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from .api import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/docs/', RedirectView.as_view(url='/api/docs', permanent=True)),
    path('api/', api.urls),
]
