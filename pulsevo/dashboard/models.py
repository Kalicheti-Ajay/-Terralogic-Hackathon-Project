from django.db import models

class Task(models.Model):
    STATUS_CHOICES = [
        ("Open", "Open"),
        ("In Progress", "In Progress"),
        ("Completed", "Completed"),
        ("Blocked", "Blocked"),
    ]
    PRIORITY_CHOICES = [("High","High"),("Medium","Medium"),("Low","Low")]

    task_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    assignee = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    project = models.CharField(max_length=100, default="General")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="Medium")
    comments = models.TextField(blank=True)

    def __str__(self):
        return f"{self.task_id} • {self.title}"
