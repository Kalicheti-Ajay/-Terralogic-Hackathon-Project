import os
import io
#import openai
from dotenv import load_dotenv
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

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from .models import Task
from datetime import timedelta

#from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
#from google_genai import client as genai_client
import google.generativeai as genai

load_dotenv()

# ✅ Configure Gemini with API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


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



# Load environment variables and configure Gemini
#load_dotenv()
#genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

@csrf_exempt
@login_required
def ai_insights(request):
    """
    Generates AI-driven natural language insights using Gemini.
    Combines task data from the database with generative analysis.
    """
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    total = Task.objects.count()
    completed = Task.objects.filter(status="Completed").count()
    open_tasks = Task.objects.filter(status="Open").count()
    in_progress = Task.objects.filter(status="In Progress").count()
    blocked = Task.objects.filter(status="Blocked").count()

    recent_completions = Task.objects.filter(
        status="Completed", completed_at__gte=week_ago
    ).count()

    top_performers = (
        Task.objects.filter(status="Completed")
        .values("assignee")
        .annotate(done=Count("id"))
        .order_by("-done")[:3]
    )

    completion_rate = round((completed / total) * 100, 1) if total else 0.0

    # Convert key stats to text context for Gemini
    context = f"""
    Team productivity summary for this week:
    - Total tasks: {total}
    - Completed: {completed}
    - Open: {open_tasks}
    - In Progress: {in_progress}
    - Blocked: {blocked}
    - Recent completions: {recent_completions}
    - Completion rate: {completion_rate}%
    - Top performers: {', '.join([t['assignee'] for t in top_performers]) if top_performers else 'None'}
    """

    # Build a prompt for Gemini
    prompt = f"""
    You are an AI productivity analyst for the Pulsevo dashboard.
    Using the data below, summarize team performance in 2–3 sentences.
    Focus on trends, strengths, and possible bottlenecks.

    {context}
    """

    # Call Gemini to generate the insight summary
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        summary_text = response.text.strip() if response.text else "No AI summary generated."
    except Exception as e:
        summary_text = f"Error generating AI summary: {str(e)}"

    # Combine numeric + AI text output
    summary = {
        "total_tasks": total,
        "completed": completed,
        "open": open_tasks,
        "in_progress": in_progress,
        "blocked": blocked,
        "completion_rate": completion_rate,
        "recent_completions": recent_completions,
        "top_performers": list(top_performers),
        "ai_summary": summary_text,
    }

    return JsonResponse(summary)





@csrf_exempt
@login_required
def gemini_query(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    user_query = request.POST.get("query", "").strip()
    if not user_query:
        return JsonResponse({"error": "Empty query"}, status=400)

    # ✅ 1️⃣ Global summary from database
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    total = Task.objects.count()
    completed = Task.objects.filter(status="Completed").count()
    open_tasks = Task.objects.filter(status="Open").count()
    in_progress = Task.objects.filter(status="In Progress").count()
    blocked = Task.objects.filter(status="Blocked").count()

    top_assignee = (
        Task.objects.filter(status="Completed")
        .values("assignee")
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )

    # ✅ 2️⃣ User-specific stats
    user_name = request.user.username
    print(user_name)
    user_open = Task.objects.filter(assignee__iexact=user_name, status="Open").count()
    user_blocked = Task.objects.filter(assignee__iexact=user_name, status="Blocked").count()
    user_completed = Task.objects.filter(assignee__iexact=user_name, status="Completed").count()
    user_total = Task.objects.filter(assignee__iexact=user_name).count()

    # Avoid division by zero
    user_completion_rate = round((user_completed / user_total) * 100, 1) if user_total else 0

    # ✅ 3️⃣ Build AI context
    context = f"""
    🔹 Global Summary:
    Total Tasks: {total}
    Completed: {completed}
    Open: {open_tasks}
    In Progress: {in_progress}
    Blocked: {blocked}
    Top Performer: {top_assignee['assignee'] if top_assignee else 'N/A'}

    🔸 Your Personal Summary ({user_name}):
    Total Assigned Tasks: {user_total}
    Completed: {user_completed}
    Open: {user_open}
    Blocked: {user_blocked}
    Completion Rate: {user_completion_rate}%
    """

    # ✅ 4️⃣ Build prompt for Gemini
    prompt = f"""
    You are Pulsevo's AI Productivity Assistant.
    Use the following project statistics and user-specific task data to answer questions
    clearly, helpfully, and concisely. Offer insights, suggestions, or summaries based on this data.

    Context:
    {context}

    User question:
    {user_query}
    """

    # ✅ 5️⃣ Call Gemini API
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))  # Set in your .env
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        answer = response.text.strip() if response.text else "No response from Gemini."
    except Exception as e:
        answer = f"⚠️ Gemini API error: {str(e)}"

    return JsonResponse({"response": answer})
