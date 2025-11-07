from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_id","title","assignee","status","project","priority","created_at","completed_at")
    search_fields = ("task_id","title","assignee","project")
    list_filter = ("status","project","priority")
