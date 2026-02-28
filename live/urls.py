from django.urls import path
from . import views

app_name = 'live'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/race/', views.api_race, name='api_race'),
    path('api/ranking/', views.api_ranking, name='api_ranking'),
    path('api/laptimes/', views.api_laptimes, name='api_laptimes'),
    path('api/telemetry/<str:abbreviation>/', views.api_telemetry, name='api_telemetry'),
    path('api/incidents/', views.api_incidents, name='api_incidents'),
    path('api/drivers/', views.api_drivers, name='api_drivers'),
]
