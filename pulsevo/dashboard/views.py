import os
import io
import openai
from django.views.decorators.csrf import csrf_exempt
import pandas as pd
from datetime import timedelta
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.db import models
from django.db.models import Count, Q
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import Task
from django.contrib.auth.decorators import login_required



# --- helpers ---
COL_MAP = {
    "task id": "task_id",
    "title": "title",
    "assignee": "assignee",
    "status": "status",
    "created at": "created_at",
    "completed at": "completed_at",
    "project": "project",
    "priority": "priority",
    "comments": "comments",
}
STATUS_NORMALIZE = {
    "open": "Open",
    "in progress": "In Progress",
    "completed": "Completed",
    "blocked": "Blocked"
}


def _parse_datetime(s):
    if pd.isna(s) or s == "":
        return None
    return pd.to_datetime(s, errors="coerce")


# --- pages ---
@login_required
def dashboard(request):
    return render(request, "dashboard.html")


# --- upload (CSV/XLSX) ---
def upload_dataset(request):
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]

        # ✅ Ensure upload directory exists
        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        # ✅ Save uploaded file to media/uploads/
        path = default_storage.save(f"uploads/{f.name}", ContentFile(f.read()))
        file_bytes = default_storage.open(path).read()

        # ✅ Read with pandas
        if f.name.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif f.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            return HttpResponseBadRequest("Please upload a CSV or Excel file.")

        # ✅ Normalize columns
        df.columns = [c.strip().lower() for c in df.columns]
        df = df.rename(columns={c: COL_MAP.get(c, c) for c in df.columns})

        required = {"task_id", "title", "assignee", "status", "created_at"}
        if not required.issubset(df.columns):
            return HttpResponseBadRequest(
                f"Missing required columns: {required - set(df.columns)}"
            )

        # ✅ Insert or update tasks
        for _, row in df.iterrows():
            status = STATUS_NORMALIZE.get(
                str(row.get("status", "")).strip().lower(),
                str(row.get("status", "")).strip() or "Open"
            )
            created_at = _parse_datetime(row.get("created_at"))
            completed_at = _parse_datetime(row.get("completed_at"))

            Task.objects.update_or_create(
                task_id=str(row.get("task_id")).strip(),
                defaults={
                    "title": str(row.get("title", "")).strip()[:200],
                    "assignee": str(row.get("assignee", "Unknown")).strip()[:100],
                    "status": status,
                    "created_at": created_at,
                    "completed_at": completed_at,
                    "project": str(row.get("project", "General")).strip()[:100],
                    "priority": str(row.get("priority", "Medium")).strip().title()[:10],
                    "comments": str(row.get("comments", "")).strip(),
                }
            )

        # ✅ Redirect to dashboard
        return redirect("dashboard")

    return render(request, "upload.html")


# --- JSON APIs for charts/cards ---
def stats_api(request):
    now = timezone.now()
    today = now.date()
    last_hour = now - timedelta(hours=1)

    total = Task.objects.count()
    open_count = Task.objects.filter(status="Open").count()
    inprog = Task.objects.filter(status="In Progress").count()
    completed = Task.objects.filter(status="Completed").count()
    blocked = Task.objects.filter(status="Blocked").count()

    closed_today = Task.objects.filter(
        status="Completed", completed_at__date=today
    ).count()

    closed_last_hour = Task.objects.filter(
        status="Completed", completed_at__gte=last_hour
    ).count()

    completion_rate = round((completed / total * 100), 1) if total else 0.0

    return JsonResponse({
        "total": total,
        "open": open_count,
        "in_progress": inprog,
        "completed": completed,
        "blocked": blocked,
        "closed_today": closed_today,
        "closed_last_hour": closed_last_hour,
        "completion_rate": completion_rate,
        "server_time": now.isoformat(),
    })


def trends_api(request):
    # last 7 days: created vs completed
    now = timezone.now().date()
    days = [now - timedelta(days=i) for i in range(6, -1, -1)]

    by_created = (
        Task.objects
        .filter(created_at__date__in=days)
        .annotate(day=models.functions.TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )
    by_completed = (
        Task.objects
        .filter(status="Completed", completed_at__isnull=False, completed_at__date__in=days)
        .annotate(day=models.functions.TruncDate("completed_at"))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )

    created_map = {x["day"].isoformat(): x["n"] for x in by_created}
    completed_map = {x["day"].isoformat(): x["n"] for x in by_completed}

    labels = [d.isoformat() for d in days]
    created = [created_map.get(lbl, 0) for lbl in labels]
    completed = [completed_map.get(lbl, 0) for lbl in labels]

    return JsonResponse({"labels": labels, "created": created, "completed": completed})


def team_api(request):
    # per-assignee distribution
    qs = Task.objects.values("assignee").annotate(
        open=Count("id", filter=Q(status="Open")),
        in_progress=Count("id", filter=Q(status="In Progress")),
        completed=Count("id", filter=Q(status="Completed")),
    ).order_by("assignee")
    return JsonResponse({"teams": list(qs)})


@csrf_exempt
def ai_insights(request):
    stats = stats_api(request).content.decode()
    prompt = f"""
    You are a productivity analyst AI. Based on these metrics, generate a short summary of the team's performance, 
    highlighting task completion rate, bottlenecks, and improvement suggestions.
    Metrics: {stats}
    """
    openai.api_key = os.getenv("OPENAI_API_KEY", "your-key-here")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}]
        )
        summary = response.choices[0].message.content
    except Exception as e:
        summary = f"AI module error: {e}"
    return JsonResponse({"summary": summary})

@csrf_exempt
def ai_query(request):
    if request.method == "POST":
        user_query = request.POST.get("query", "")
        metrics = stats_api(request).content.decode()
        context = f"Team metrics: {metrics}"
        prompt = f"Answer this query about team productivity: {user_query}. Context: {context}"
        openai.api_key = os.getenv("OPENAI_API_KEY", "your-key-here")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}]
            )
            answer = response.choices[0].message.content
        except Exception as e:
            answer = f"Error: {e}"
        return JsonResponse({"response": answer})

def predictive_stats(request):
    days = 7
    now = timezone.now().date()
    recent = Task.objects.filter(
        completed_at__isnull=False,
        completed_at__gte=now - timedelta(days=days)
    ).count()
    next_week_forecast = round(recent * 1.1)  # +10% trend assumption
    return JsonResponse({
        "recent_completions": recent,
        "forecast_next_week": next_week_forecast
    })

@login_required
def tasks_view(request):
    # Fetch all tasks
    tasks = Task.objects.all().order_by("assignee")

    # Group by assignee
    grouped = {}
    for t in tasks:
        if t.assignee not in grouped:
            grouped[t.assignee] = {"assigned": 0, "completed": 0, "ongoing": 0}
        grouped[t.assignee]["assigned"] += 1
        if t.status == "Completed":
            grouped[t.assignee]["completed"] += 1
        else:
            grouped[t.assignee]["ongoing"] += 1

    # Compute project distribution
    projects = (
        Task.objects.values("project")
        .annotate(
            total=Count("id"),
            open_issues=Count("id", filter=Q(status="Open")),
        )
        .order_by("project")
    )

    return render(request, "tasks.html", {
        "tasks_summary": grouped,
        "projects": list(projects),
    })
