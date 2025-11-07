from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload_dataset, name="upload_dataset"),
    path("api/stats/", views.stats_api, name="stats_api"),
    path("api/trends/", views.trends_api, name="trends_api"),
    path("api/team/", views.team_api, name="team_api"),
]
