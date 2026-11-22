# Ops Log — Task & Performance Tracker

A daily task tracker with weighted points, target dates, and a
composite performance score that classifies you as a Perfectionist,
Hustler, Steady, or Needs Reset based on your own history.

## Stack

- **Flask** — routes and templating
- **Flask-SQLAlchemy** — one table (`Task`), stored in `tasks.db` (SQLite, created automatically on first run)
- **Jinja templates** — server-rendered HTML, no frontend framework
- **Chart.js** (via CDN) — the one line graph on the Stats page; everything else is plain CSS

No auth, no migrations, no JS framework — deliberately minimal so every
part of the stack is something you can explain end to end.

## Running it

```bash
cd task-tracker
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
```

Visit `http://127.0.0.1:5000`.

## How the scoring works (`scoring.py`)

A task only counts toward your stats once its target date has passed —
you can't be judged on something not due yet.

For that set of "due" tasks, three percentages are computed:

- **Completion Rate (CR)** — of tasks due, how many did you finish at all?
- **On-Time Rate (OTR)** — of what you finished, how much was on or before the target date?
- **Avg. Weight Cleared (AWC)** — of what you finished, how heavy (points-wise) were those tasks on average, out of the 10-point scale?

These combine into one **Performance Score**:

```
score = CR * 0.4 + OTR * 0.2 + AWC * 0.4
```

The score then maps to a label:

| Score    | Label         |
|----------|---------------|
| 85–100   | Perfectionist |
| 70–84    | Hustler       |
| 50–69    | Steady        |
| 0–49     | Needs Reset   |

`compute_overall()` runs this across your entire history for the
current label. `compute_weekly_trend()` runs the same formula per
ISO week (grouped by each task's target date) to produce the points
plotted on the line graph — so the graph shows the trend, and the
gauge shows where you stand right now.

## Project structure

```
task-tracker/
├── app.py              routes
├── models.py            Task model
├── scoring.py           all scoring math, framework-independent
├── templates/
│   ├── base.html        shared layout + title-block header
│   ├── index.html        task log + add form
│   └── stats.html        gauge + weekly trend chart
└── static/css/style.css  styling
```
