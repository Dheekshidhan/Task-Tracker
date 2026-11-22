from datetime import datetime, date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash

from models import db, Task
from scoring import (
    compute_overall,
    compute_weekly_trend,
    compute_streak,
    compute_avg_completion_days,
    compute_difficulty_breakdown,
    compute_monthly_totals_for_year,
    available_years,
    compute_best_week,
    compute_month_stats,
    available_months,
    STREAK_MILESTONES,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tasks.db"
app.secret_key = "dev-only-key-change-if-deploying"  # only needed for flash() toasts
db.init_app(app)

with app.app_context():
    db.create_all()


@app.context_processor
def inject_globals():
    # Makes {{ today }} and {{ streak }} available in every template
    # (the title-block stamp shows both) without passing them per route.
    streak = compute_streak(Task.query.all())
    return {"today": date.today(), "streak": streak}


@app.route("/")
@app.route("/")
def index():
    pending = Task.query.filter_by(completed=False).order_by(Task.due_date.asc()).all()
    completed = Task.query.filter_by(completed=True).order_by(Task.completed_date.desc()).all()
    just_completed = request.args.get("done", type=int)
    milestone_hit = request.args.get("milestone", type=int)

    # NEW: Calculate Today's Progress Bar Data
    today_date = date.today()
    today_tasks = Task.query.filter_by(due_date=today_date).all()
    today_target = sum(t.points for t in today_tasks)
    today_done = sum(t.points for t in today_tasks if t.completed)
    progress_pct = (today_done / today_target * 100) if today_target else 0

    return render_template(
        "index.html",
        pending=pending,
        completed=completed,
        just_completed=just_completed,
        milestone_hit=milestone_hit,
        today_target=today_target,
        today_done=today_done,
        progress_pct=round(progress_pct)
    )
@app.route("/rollover/<int:task_id>", methods=["POST"])
def rollover_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.due_date = date.today()
    db.session.commit()
    flash(f'⏭️ "{task.title}" rolled over to today!', "info")
    return redirect(url_for("index"))


@app.route("/add", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    points = int(request.form.get("points", 5))
    due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date()

    if title:
        db.session.add(Task(title=title, points=points, due_date=due_date))
        db.session.commit()
        flash(f'📌 Logged "{title}"', "success")
    else:
        flash("❌ Task needs a title.", "error")

    return redirect(url_for("index"))


@app.route("/complete/<int:task_id>", methods=["POST"])
def complete_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.completed = not task.completed
    task.completed_date = date.today() if task.completed else None
    db.session.commit()

    if not task.completed:
        flash(f'⏳ "{task.title}" moved back to pending', "info")
        return redirect(url_for("index"))

    new_streak = compute_streak(Task.query.all())
    flash(f'✅ "{task.title}" done!', "success")

    if new_streak in STREAK_MILESTONES:
        return redirect(url_for("index", done=task.id, milestone=new_streak))
    return redirect(url_for("index", done=task.id))


@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            task.title = title
        task.points = int(request.form.get("points", task.points))
        task.due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date()
        db.session.commit()
        flash(f'✏️ "{task.title}" updated', "success")
        return redirect(url_for("index"))

    return render_template("edit.html", task=task)


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash(f'🗑️ "{task.title}" removed', "info")
    return redirect(url_for("index"))


@app.route("/stats")
def stats():
    all_tasks = Task.query.all()
    overall = compute_overall(all_tasks)
    trend = compute_weekly_trend(all_tasks)
    difficulty = compute_difficulty_breakdown(all_tasks)
    avg_completion_days = compute_avg_completion_days(all_tasks)
    best_week = compute_best_week(all_tasks)

    years = available_years(all_tasks)
    requested_year = request.args.get("year", type=int)
    if requested_year and requested_year in years:
        selected_year = requested_year
    else:
        selected_year = years[0] if years else date.today().year
    monthly = compute_monthly_totals_for_year(all_tasks, selected_year)

    return render_template(
        "stats.html",
        overall=overall,
        trend=trend,
        difficulty=difficulty,
        avg_completion_days=avg_completion_days,
        monthly=monthly,
        best_week=best_week,
        years=years,
        selected_year=selected_year,
    )


@app.route("/compare")
def compare():
    all_tasks = Task.query.all()
    months = available_months(all_tasks)  # [(year, month), ...] most recent first
    month_options = [
        {"value": f"{y}-{m}", "label": date(y, m, 1).strftime("%b %Y")}
        for (y, m) in months
    ]

    today = date.today()
    this_month = (today.year, today.month)
    last_month_date = date(today.year, today.month, 1) - timedelta(days=1)
    last_month = (last_month_date.year, last_month_date.month)

    def parse_param(value, fallback):
        if value:
            try:
                y, m = value.split("-")
                return (int(y), int(m))
            except ValueError:
                pass
        return fallback

    a = parse_param(request.args.get("a"), this_month)
    b = parse_param(request.args.get("b"), last_month)

    stats_a = compute_month_stats(all_tasks, *a)
    stats_b = compute_month_stats(all_tasks, *b)

    return render_template(
        "compare.html",
        month_options=month_options,
        selected_a=f"{a[0]}-{a[1]}",
        selected_b=f"{b[0]}-{b[1]}",
        stats_a=stats_a,
        stats_b=stats_b,
    )


if __name__ == "__main__":
    app.run(debug=True)