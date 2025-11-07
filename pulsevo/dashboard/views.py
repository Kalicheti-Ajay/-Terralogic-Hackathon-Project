import io
import pandas as pd
from datetime import timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.db import models                     # ✅ ADD THIS LINE
from django.db.models import Count, Q
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import Task


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
STATUS_NORMALIZE = {"open":"Open","in progress":"In Progress","completed":"Completed","blocked":"Blocked"}

def _parse_datetime(s):
    if pd.isna(s) or s == "":
        return None
    return pd.to_datetime(s, errors="coerce")

# --- pages ---
def dashboard(request):
    return render(request, "dashboard.html")

# --- upload (CSV/XLSX) ---
def upload_dataset(request):
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        path = default_storage.save(f"uploads/{f.name}", ContentFile(f.read()))
        file_bytes = default_storage.open(path).read()

        # read with pandas
        if f.name.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif f.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            return HttpResponseBadRequest("Please upload CSV or Excel file.")

        # normalize columns
        df.columns = [c.strip().lower() for c in df.columns]
        df = df.rename(columns={c: COL_MAP.get(c, c) for c in df.columns})

        required = {"task_id","title","assignee","status","created_at"}
        if not required.issubset(df.columns):
            return HttpResponseBadRequest(f"Missing required columns: {required - set(df.columns)}")

        for _, row in df.iterrows():
            status = STATUS_NORMALIZE.get(str(row.get("status","")).strip().lower(), str(row.get("status","")).strip() or "Open")
            created_at = _parse_datetime(row.get("created_at"))
            completed_at = _parse_datetime(row.get("completed_at"))

            Task.objects.update_or_create(
                task_id=str(row.get("task_id")).strip(),
                defaults={
                    "title": str(row.get("title","")).strip()[:200],
                    "assignee": str(row.get("assignee","Unknown")).strip()[:100],
                    "status": status,
                    "created_at": created_at,
                    "completed_at": completed_at,
                    "project": str(row.get("project","General")).strip()[:100],
                    "priority": str(row.get("priority","Medium")).strip().title()[:10],
                    "comments": str(row.get("comments","")).strip(),
                }
            )

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
        status="Completed",
        completed_at__date=today
    ).count()

    closed_last_hour = Task.objects.filter(
        status="Completed",
        completed_at__gte=last_hour
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
