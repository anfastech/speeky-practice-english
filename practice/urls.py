from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('practice/<str:scenario_id>/', views.session, name='session'),
    path('api/chat/<str:scenario_id>/', views.chat_api, name='chat_api'),
    path('api/reset/<str:scenario_id>/', views.reset_session, name='reset_session'),
]
