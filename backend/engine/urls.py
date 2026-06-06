from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from django.http import JsonResponse
from .api import api

def home_view(request):
    return JsonResponse({
        "message": "<img width=\"50\" height=\"50\" src=\"https://img.icons8.com/ios/50/swift-payment-system.png\" alt=\"swift-payment-system\"/> Welcome to the Swift API Base!",
        "status": "online",
    })

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('api/docs/', RedirectView.as_view(url='/api/docs', permanent=True)),
    path('api/', api.urls),
]
