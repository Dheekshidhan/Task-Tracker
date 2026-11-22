"""
All the scoring math lives here, separate from the Flask routes, so it
can be read (and defended in an interview) on its own.

The idea:
  1. A task only "counts" toward stats once its due date has passed --
     you can't judge a task that isn't due yet.
  2. For that set of due tasks, we compute two percentages:
       CR  (Completion Rate) - did you finish it at all?
       OTR (On-Time Rate)    - of what you finished, was it on time?
  3. A third factor, Momentum, compares this week's completed points
     against your OWN historical weekly average -- not a fixed ceiling.
     This avoids punishing anyone whose honest point scale runs low
     (e.g. mostly 3-6 point tasks): matching your own normal pace = 100%.
  4. Those three combine into one 0-100 Performance Score:
       score = CR*0.4 + OTR*0.2 + Momentum*0.4  (Momentum capped at 100)
  5. The score maps to one label: Perfectionist / Hustler / Steady / Needs Reset.
"""

from datetime import date, timedelta

# score cutoffs -> label. Checked top to bottom, first match wins.
LABEL_THRESHOLDS = [
    (85, "🎯 Perfectionist"),
    (70, "🔥 Hustler"),
    (50, "⚖️ Steady"),
    (0, "🔄 Needs Reset"),
]


def label_for_score(score):
    for cutoff, label in LABEL_THRESHOLDS:
        if score >= cutoff:
            return label
    return "🔄 Needs Reset"


def _due_tasks(tasks, today=None):
    """Tasks whose due date has already arrived -- the only ones we can judge."""
    today = today or date.today()
    return [t for t in tasks if t.due_date <= today]


def _completion_metrics(task_subset):
    """Given a list of 'due' tasks, compute Completion Rate and On-Time Rate."""
    total_due = len(task_subset)
    completed = [t for t in task_subset if t.completed]
    total_completed = len(completed)

    cr = (total_completed / total_due * 100) if total_due else 0

    on_time = [t for t in completed if t.completed_date and t.completed_date <= t.due_date]
    otr = (len(on_time) / total_completed * 100) if total_completed else 0

    return {
        "total_due": total_due,
        "total_completed": total_completed,
        "cr": round(cr, 1),
        "otr": round(otr, 1),
    }


def compute_weekly_points(tasks):
    """
    Bucket due tasks by the ISO week of their due date, and sum the
    points of whichever ones got completed. This is the raw material
    for Momentum, Weekly Best, and the weekly trend graph.
    """
    today = date.today()
    due = _due_tasks(tasks, today)
    if not due:
        return []

    buckets = {}
    for t in due:
        year, week, _ = t.due_date.isocalendar()
        buckets.setdefault((year, week), []).append(t)

    result = []
    for (year, week), bucket_tasks in sorted(buckets.items()):
        points = sum(t.points for t in bucket_tasks if t.completed)
        monday = date.fromisocalendar(year, week, 1)
        result.append({
            "year": year,
            "week": week,
            "label": monday.strftime("%b %d"),
            "points": points,
        })
    return result


def compute_momentum(tasks):
    """
    This week's completed points, as a percentage of your average
    weekly points from every prior week. 100% = matching your own
    normal pace. Returns None if there isn't at least one full prior
    week of history yet -- there's no baseline to compare against.
    """
    weekly = compute_weekly_points(tasks)
    if len(weekly) < 2:
        return None

    *history, current = weekly
    if not history:
        return None

    baseline = sum(w["points"] for w in history) / len(history)
    if baseline == 0:
        return None

    return {
        "pct": round(current["points"] / baseline * 100, 1),
        "baseline": round(baseline, 1),
        "current_points": current["points"],
    }


def compute_best_week(tasks):
    """Your highest-ever weekly point total -- a permanent personal record."""
    weekly = [w for w in compute_weekly_points(tasks) if w["points"] > 0]
    if not weekly:
        return None
    return max(weekly, key=lambda w: w["points"])


def compute_overall(tasks):
    """
    All-time Completion Rate and On-Time Rate, combined with Momentum,
    into the single 0-100 score and its label.
    """
    due = _due_tasks(tasks)
    metrics = _completion_metrics(due)

    momentum = compute_momentum(tasks)
    # No baseline yet (still building history) -> treat as neutral (100),
    # so early use isn't penalized before there's enough data to compare.
    momentum_component = min(momentum["pct"], 100) if momentum else 100

    score = round(metrics["cr"] * 0.4 + metrics["otr"] * 0.2 + momentum_component * 0.4, 1)
    metrics["score"] = score
    metrics["label"] = label_for_score(score)
    metrics["momentum"] = momentum
    return metrics


def compute_streak(tasks):
    """
    Consecutive days with at least one task completed, counting
    backwards from today. If nothing is done today yet, we start
    counting from yesterday instead -- so an existing streak doesn't
    look broken before you've had a chance to finish today's tasks.
    """
    completed_dates = {t.completed_date for t in tasks if t.completed and t.completed_date}
    if not completed_dates:
        return 0

    today = date.today()
    day = today if today in completed_dates else today - timedelta(days=1)

    streak = 0
    while day in completed_dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


STREAK_MILESTONES = {3, 7, 14, 30, 60, 100}


def compute_weekly_trend(tasks):
    """
    Discipline trend per due-date week: CR and OTR blended.
    Zero-fills inactive weeks so the graph accurately reflects breaks in activity.
    """
    today = date.today()
    due = _due_tasks(tasks, today)
    if not due:
        return []

    # 1. Group existing tasks by year and week
    buckets = {}
    for t in due:
        year, week, _ = t.due_date.isocalendar()
        buckets.setdefault((year, week), []).append(t)

    # 2. Find the earliest active week to start our continuous timeline
    earliest_date = min(t.due_date for t in due)
    start_year, start_week, _ = earliest_date.isocalendar()
    current_monday = date.fromisocalendar(start_year, start_week, 1)

    # 3. Define the end point (this week's Monday)
    this_year, this_week, _ = today.isocalendar()
    end_monday = date.fromisocalendar(this_year, this_week, 1)

    trend = []

    # 4. Loop week-by-week, zero-filling if no tasks exist
    while current_monday <= end_monday:
        y, w, _ = current_monday.isocalendar()
        bucket_tasks = buckets.get((y, w), [])

        if bucket_tasks:
            metrics = _completion_metrics(bucket_tasks)
            weekly_score = round(metrics["cr"] * 0.6 + metrics["otr"] * 0.4, 1)
        else:
            weekly_score = 0.0  # The crucial fix for inactive weeks

        trend.append({
            "label": current_monday.strftime("%b %d"),
            "score": weekly_score,
        })
        current_monday += timedelta(days=7)

    return trend


# points -> difficulty tier, used for the Easy/Medium/Hard breakdown
DIFFICULTY_BANDS = [
    (1, 3, "Easy"),
    (4, 7, "Medium"),
    (8, 10, "Hard"),
]


def tier_for_points(points):
    for low, high, label in DIFFICULTY_BANDS:
        if low <= points <= high:
            return label
    return "Hard"  # anything above 10 still counts as the top tier


def compute_difficulty_breakdown(tasks):
    """How many completed tasks fall into each difficulty tier -- shows
    what kind of work you actually finish, not just how much."""
    counts = {"Easy": 0, "Medium": 0, "Hard": 0}
    for t in tasks:
        if t.completed:
            counts[tier_for_points(t.points)] += 1
    return counts


def compute_avg_completion_days(tasks):
    """
    Average number of days between logging a task and finishing it.
    A different angle from On-Time Rate: OTR asks 'did you beat the
    deadline', this asks 'how long do things typically sit before
    you clear them', regardless of when they were due.
    Returns None if nothing has been completed yet.
    """
    completed = [t for t in tasks if t.completed and t.completed_date and t.created_date]
    if not completed:
        return None
    days = [(t.completed_date - t.created_date).days for t in completed]
    return round(sum(days) / len(days), 1)


def compute_monthly_totals_for_year(tasks, year):
    """
    All 12 months of a given year, zero-filled where nothing was
    completed -- so the chart always shows a consistent Jan-Dec shape
    instead of a single bar stretching to fill the space.
    """
    totals = {m: {"points": 0, "count": 0} for m in range(1, 13)}
    for t in tasks:
        if t.completed and t.completed_date and t.completed_date.year == year:
            totals[t.completed_date.month]["points"] += t.points
            totals[t.completed_date.month]["count"] += 1

    return [
        {
            "label": date(year, m, 1).strftime("%b"),
            "points": totals[m]["points"],
            "count": totals[m]["count"],
        }
        for m in range(1, 13)
    ]


def available_years(tasks):
    """Years with at least one completed task, most recent first."""
    years = {t.completed_date.year for t in tasks if t.completed and t.completed_date}
    return sorted(years, reverse=True)


def compute_month_stats(tasks, year, month):
    """Points and task count completed within one specific calendar month."""
    completed = [
        t for t in tasks
        if t.completed and t.completed_date
        and t.completed_date.year == year and t.completed_date.month == month
    ]
    return {
        "points": sum(t.points for t in completed),
        "count": len(completed),
        "label": date(year, month, 1).strftime("%B %Y"),
    }


def available_months(tasks):
    """(year, month) tuples with at least one completed task, most recent first."""
    months = {
        (t.completed_date.year, t.completed_date.month)
        for t in tasks if t.completed and t.completed_date
    }
    return sorted(months, reverse=True)