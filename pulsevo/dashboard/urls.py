from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload_dataset, name="upload_dataset"),
    path("api/stats/", views.stats_api, name="stats_api"),
    path("api/trends/", views.trends_api, name="trends_api"),
    path("api/team/", views.team_api, name="team_api"),
    path("api/ai-insights/", views.ai_insights, name="ai_insights"),
    path("api/query/", views.gemini_query, name="ai_query"),
    path("api/predict/", views.predictive_stats, name="predictive_stats"),
    path("tasks/", views.tasks_view, name="tasks_view"),
    path("api/gemini-query/", views.gemini_query, name="gemini_query"),
]
