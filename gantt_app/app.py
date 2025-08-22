# -*- coding: utf-8 -*-
"""
Gantt App — Flask single-file demo (Render-friendly & sandbox-safe)
-------------------------------------------------------------------
- Local **serve**:     `python3 app.py --serve` → http://127.0.0.1:8001/gantt
- Local **self-tests**: `python3 app.py` (default; does NOT open a port)
- Minimal dependencies: Flask, Flask-SQLAlchemy, gunicorn
- Purpose: simple people × date Gantt-like view with per-item memo

Seed staff (new project dataset):
  WXP, LJH, TLF, LXY, MAMA, BABA, RCD, SCL, JSP

Environment (optional):
  SECRET_KEY=...
  DATABASE_URL=sqlite:///gantt_demo.db  (default)
  DATA_DIR=/tmp/gntdata               (where sqlite file will be created)

Render settings for a separate service:
  Root Directory: gantt_app
  Build Command:  pip install -r requirements.txt
  Start Command:  gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

Why this rewrite?
  Some sandboxes cannot bind to a TCP port → Flask's dev server would exit with
  `SystemExit: 1`. Also, calling DB APIs without an app context raises
  `RuntimeError: Working outside of application context`. This version runs
  **self-tests by default** (no socket) and wraps DB access in `app.app_context()`
  during tests. Additionally, `ensure_db_seed()` now opens its own application
  context so it is safe to call from anywhere.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict

from flask import Flask, request, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader

# ------------------------------
# Helpers: safe SQLite URI for cloud hosts
# ------------------------------
def _prepare_sqlite_uri(raw: str) -> str:
    """Coerce sqlite:/// URIs to a writeable location on hosts like Render.
    - sqlite:////abs/path.db → keep absolute and ensure parent exists
    - sqlite:///rel.db      → place under DATA_DIR (default /tmp/gntdata)
    Other schemes (postgres:// etc.) are returned as-is.
    """
    try:
        if not raw or not raw.startswith('sqlite'):
            return raw
        safe_base = os.environ.get('DATA_DIR') or '/tmp/gntdata'
        base = Path(safe_base)
        base.mkdir(parents=True, exist_ok=True)
        if raw.startswith('sqlite:////'):
            abs_path = Path(raw.replace('sqlite:////', '/', 1))
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                abs_path.touch(exist_ok=True)
            except Exception:
                pass
            return 'sqlite:////' + str(abs_path).lstrip('/')
        if raw.startswith('sqlite:///'):
            rel = raw[len('sqlite:///'):]
            dbf = base / rel
            try:
                dbf.parent.mkdir(parents=True, exist_ok=True)
                dbf.touch(exist_ok=True)
            except Exception:
                pass
            return 'sqlite:////' + str(dbf).lstrip('/')
        return raw
    except Exception:
        pf = Path('/tmp/gntdata/panic.db')
        pf.parent.mkdir(parents=True, exist_ok=True)
        try:
            pf.touch(exist_ok=True)
        except Exception:
            pass
        return 'sqlite:////' + str(pf).lstrip('/')

# ------------------------------
# App & DB
# ------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-gantt')
raw_db = os.environ.get('DATABASE_URL', 'sqlite:///gantt_demo.db')
app.config['SQLALCHEMY_DATABASE_URI'] = _prepare_sqlite_uri(raw_db)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if str(app.config['SQLALCHEMY_DATABASE_URI']).startswith('sqlite'):
    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].setdefault('connect_args', {
        'check_same_thread': False,
        'timeout': 30,
    })

db = SQLAlchemy(app)

# ------------------------------
# Models
# ------------------------------
class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    color = db.Column(db.String(20), nullable=True)  # optional CSS color

class Assign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    staff = db.relationship('Staff')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    memo = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------------------
# Bootstrapping
# ------------------------------
# New project seed names (as requested earlier)
SEED_STAFF = [
    ('WXP',  '#8ecae6'),
    ('LJH',  '#90be6d'),
    ('TLF',  '#f9c74f'),
    ('LXY',  '#f8961e'),
    ('MAMA', '#f28482'),
    ('BABA', '#b388eb'),
    ('RCD',  '#f72585'),
    ('SCL',  '#4cc9f0'),
    ('JSP',  '#43aa8b'),
]

def ensure_db_seed() -> None:
    """Create tables and seed staff names.
    Safe to call from anywhere (opens its own app context).
    """
    with app.app_context():
        db.create_all()
        if Staff.query.count() == 0:
            for n, c in SEED_STAFF:
                db.session.add(Staff(name=n, color=c))
            db.session.commit()

# ------------------------------
# Date helpers
# ------------------------------
@dataclass
class Timeline:
    start: date
    end: date
    days: List[date]


def parse_date(s: str) -> date:
    return datetime.strptime(s, '%Y-%m-%d').date()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_timeline(start: date | None = None, weeks: int = 4) -> Timeline:
    start = monday_of(start or date.today())
    total_days = weeks * 7
    days = [start + timedelta(days=i) for i in range(total_days)]
    end = days[-1]
    return Timeline(start=start, end=end, days=days)


def overlap(a1: date, a2: date, b1: date, b2: date) -> bool:
    return not (a2 < b1 or b2 < a1)

# ------------------------------
# Templates (inline via DictLoader)
# ------------------------------
BASE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gantt App</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding-top: 2rem; }
    .grid { display: grid; gap: 6px; }
    .daycell { font-size: .8rem; text-align: center; color: #666; }
    .lane { display: grid; gap: 4px; }
    .bar {
      border-radius: .5rem; padding: 4px 8px; font-size: .85rem; line-height: 1.2; color:#111;
      background: #d0e6ff; border: 1px solid rgba(0,0,0,.08);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .memo { font-size: .75rem; opacity: .8; }
    .sticky-header { position: sticky; top: 0; background: #fff; z-index: 2; }
    .label { font-weight: 600; }
    .date-col { min-width: 40px; }
  </style>
</head>
<body>
<div class="container">
  {% block body %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
  // enable tooltips if present
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
  tooltipTriggerList.map(function (el) { return new bootstrap.Tooltip(el) })
</script>
</body>
</html>
"""

GANTT = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h3 class="m-0">People × Dates (Gantt-like)</h3>
  <form class="d-flex gap-2" method="get">
    <input class="form-control" type="date" name="start" value="{{ tl.start }}">
    <select class="form-select" name="weeks" style="width:120px">
      {% for w in [2,4,6,8,12] %}
      <option value="{{w}}" {% if weeks==w %}selected{% endif %}>{{w}} weeks</option>
      {% endfor %}
    </select>
    <button class="btn btn-primary">Go</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('new_assign', start=tl.start, weeks=weeks) }}">+ New</a>
  </form>
</div>

<div class="grid" style="grid-template-columns: 180px repeat({{ tl.days|length }}, minmax(40px, 1fr)); align-items: start;">
  <!-- Header row -->
  <div class="sticky-header"></div>
  {% for d in tl.days %}
    <div class="daycell sticky-header date-col">{{ d.strftime('%m/%d') }}<br><span class="text-muted">{{ ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d.weekday()] }}</span></div>
  {% endfor %}

  <!-- Lanes per staff -->
  {% for s in staff_list %}
    <div class="label pt-2">{{ s.name }}</div>
    <div class="lane" style="grid-column: 2 / span {{ tl.days|length }}; grid-template-columns: repeat({{ tl.days|length }}, 1fr);">
      {% for it in grouped.get(s.id, []) %}
        {% set start = (it.start_date - tl.start).days + 1 %}
        {% set span  = (it.end_date - it.start_date).days + 1 %}
        {% if start < 1 %}{% set start = 1 %}{% endif %}
        {% if start > tl.days|length %}{% set start = tl.days|length %}{% endif %}
        {% set maxspan = tl.days|length - start + 1 %}
        {% if span > maxspan %}{% set span = maxspan %}{% endif %}
        <div class="bar" style="grid-column: {{ start }} / span {{ span }}; background: {{ s.color or '#d0e6ff' }};" data-bs-toggle="tooltip" title="{{ it.memo or '' }}">
          <strong>{{ it.title }}</strong>
        </div>
      {% else %}
        <div class="text-muted" style="grid-column: 1 / -1; font-size:.85rem;">—</div>
      {% endfor %}
    </div>
  {% endfor %}
</div>
{% endblock %}
"""

FORM = """
{% extends 'BASE' %}
{% block body %}
<h4 class="mb-3">New Assignment</h4>
<form method="post">
  <div class="row g-3">
    <div class="col-md-6">
      <label class="form-label">Title</label>
      <input class="form-control" name="title" required>
    </div>
    <div class="col-md-6">
      <label class="form-label">Staff</label>
      <select class="form-select" name="staff_id" required>
        {% for s in staff_list %}
          <option value="{{ s.id }}">{{ s.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label">Start</label>
      <input type="date" class="form-control" name="start" value="{{ request.args.get('start', '') }}" required>
    </div>
    <div class="col-md-3">
      <label class="form-label">End</label>
      <input type="date" class="form-control" name="end" required>
    </div>
    <div class="col-12">
      <label class="form-label">Memo</label>
      <textarea class="form-control" name="memo" rows="3" placeholder="Notes, details, context..."></textarea>
    </div>
  </div>
  <div class="mt-3 d-flex gap-2">
    <button class="btn btn-primary">Save</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('gantt', start=request.args.get('start'), weeks=request.args.get('weeks')) }}">Back</a>
  </div>
</form>
{% endblock %}
"""

# Register templates into Flask/Jinja so `{% extends 'BASE' %}` works even without files
app.jinja_loader = DictLoader({'BASE': BASE, 'GANTT': GANTT, 'FORM': FORM})

# ------------------------------
# Routes
# ------------------------------
@app.route('/')
def index():
    return redirect(url_for('gantt'))

@app.route('/gantt')
def gantt():
    ensure_db_seed()
    # read window
    qs_start = request.args.get('start')
    weeks = int(request.args.get('weeks', '4'))
    start = parse_date(qs_start) if qs_start else monday_of(date.today())
    tl = build_timeline(start, weeks)

    # fetch staff & overlapping assignments
    staff_list = Staff.query.order_by(Staff.name.asc()).all()
    grouped: Dict[int, List[dict]] = {s.id: [] for s in staff_list}

    q = Assign.query.filter(Assign.end_date >= tl.start, Assign.start_date <= tl.end)
    q = q.order_by(Assign.start_date.asc(), Assign.id.asc())
    items = q.all()

    # bucket by staff and clamp to window for rendering (without mutating DB rows)
    for it in items:
        if it.staff_id in grouped:
            start_clamped = max(it.start_date, tl.start)
            end_clamped = min(it.end_date, tl.end)
            grouped[it.staff_id].append({
                'title': it.title,
                'start_date': start_clamped,
                'end_date': end_clamped,
                'memo': it.memo or '',
            })

    return render_template('GANTT', tl=tl, staff_list=staff_list, grouped=grouped, weeks=weeks)

@app.route('/assign/new', methods=['GET','POST'])
def new_assign():
    ensure_db_seed()
    staff_list = Staff.query.order_by(Staff.name.asc()).all()
    if request.method == 'POST':
        title = request.form['title']
        staff_id = int(request.form['staff_id'])
        start = parse_date(request.form['start'])
        end = parse_date(request.form['end'])
        if end < start:
            start, end = end, start  # swap
        memo = request.form.get('memo', '')
        db.session.add(Assign(title=title, staff_id=staff_id, start_date=start, end_date=end, memo=memo))
        db.session.commit()
        return redirect(url_for('gantt', start=request.args.get('start'), weeks=request.args.get('weeks')))
    return render_template('FORM', staff_list=staff_list)

@app.route('/health')
def health():
    return 'ok', 200

# ------------------------------
# Self-tests (run when not serving)
# ------------------------------
def run_self_tests() -> None:
    """Basic smoke tests for sandbox/CI execution.
    Ensures endpoints respond and DB writes work, without binding to any port.
    All DB access is wrapped in app.app_context().
    """
    with app.app_context():
        ensure_db_seed()  # still fine to call inside context
        with app.test_client() as c:
            # 1) healthcheck
            r = c.get('/health')
            assert r.status_code == 200 and b'ok' in r.data, 'health endpoint failed'

            # 2) render gantt
            r = c.get('/gantt?weeks=2')
            assert r.status_code == 200 and b'Gantt-like' in r.data, 'gantt view failed'

            # 3) create an assignment and see it on gantt
            first_staff = Staff.query.order_by(Staff.id.asc()).first()
            assert first_staff is not None, 'seed staff missing'
            today = date.today()
            payload = {
                'title': 'Unit Test Task',
                'staff_id': str(first_staff.id),
                'start': today.strftime('%Y-%m-%d'),
                'end':   (today + timedelta(days=3)).strftime('%Y-%m-%d'),
                'memo':  'added by self-test',
            }
            r = c.post('/assign/new?weeks=2', data=payload, follow_redirects=True)
            assert r.status_code == 200, 'POST /assign/new did not redirect correctly'
            created = Assign.query.filter_by(title='Unit Test Task', staff_id=first_staff.id).first()
            assert created is not None, 'assignment not persisted'
            # Check it renders back
            r = c.get('/gantt?weeks=2')
            assert b'Unit Test Task' in r.data, 'created task not visible in gantt'

            # 4) reversed dates should be auto-swapped
            payload2 = {
                'title': 'Swap Dates',
                'staff_id': str(first_staff.id),
                'start': (today + timedelta(days=5)).strftime('%Y-%m-%d'),
                'end':   (today + timedelta(days=2)).strftime('%Y-%m-%d'),
                'memo':  'reversed dates',
            }
            r = c.post('/assign/new?weeks=2', data=payload2, follow_redirects=True)
            assert r.status_code == 200
            rec = Assign.query.filter_by(title='Swap Dates', staff_id=first_staff.id).first()
            assert rec and rec.start_date <= rec.end_date, 'date swap normalization failed'

            # 5) long-span task should not mutate stored dates when rendering
            long_title = 'Very Long Task'
            long_start = today - timedelta(days=30)
            long_end   = today + timedelta(days=30)
            db.session.add(Assign(title=long_title, staff_id=first_staff.id, start_date=long_start, end_date=long_end, memo='long'))
            db.session.commit()
            # Render a short window
            r = c.get('/gantt?weeks=2')
            assert r.status_code == 200 and long_title.encode() in r.data
            # Verify DB still has original dates
            rec2 = Assign.query.filter_by(title=long_title, staff_id=first_staff.id).first()
            assert rec2 and rec2.start_date == long_start and rec2.end_date == long_end, 'rendering mutated DB row!'

    # 6) BONUS test: ensure ensure_db_seed() can be called without an active app context
    # (It opens its own context now; this would have raised RuntimeError before.)
    ensure_db_seed()

    print('[self-tests] OK — health, gantt render, create/swap/long-span, seed-anywhere ✓')

# ------------------------------
# Main
# ------------------------------
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Gantt App runner')
    parser.add_argument('--serve', action='store_true', help='Run development server')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8001)))
    args = parser.parse_args()

    if args.serve:
        # Different default port to avoid clash if you run alongside your other app locally
        app.run(host='0.0.0.0', port=args.port, debug=(os.environ.get('FLASK_DEBUG','0')=='1'))
    else:
        # Default path for sandboxes/CI: run tests, no sockets → avoids SystemExit:1
        run_self_tests()
        # Do NOT call sys.exit(); some environments treat any SystemExit as a failure.
