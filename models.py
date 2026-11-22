"""
Database model for the task tracker.

One table, one class -- deliberately kept flat. A task has a title,
a points value (1-10, its "weightage"), a due date, and a completed
flag the user sets themselves.
"""

from datetime import date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False)          # weightage, 1-10
    due_date = db.Column(db.Date, nullable=False)
    created_date = db.Column(db.Date, nullable=False, default=date.today)

    completed = db.Column(db.Boolean, default=False)
    completed_date = db.Column(db.Date, nullable=True)      # set when marked done

    def is_overdue(self):
        """Still pending, and the due date has already passed."""
        return (not self.completed) and self.due_date < date.today()

    def is_on_time(self):
        """
        Whether this task was finished on or before its due date.
        Returns None if it hasn't been completed yet -- there's
        nothing to judge until then.
        """
        if not self.completed or not self.completed_date:
            return None
        return self.completed_date <= self.due_date
