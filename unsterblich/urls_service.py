from django.urls import path, include
from .views import upbit

urlpatterns = [
    path('upbit/', include(upbit.urlpatterns))
]