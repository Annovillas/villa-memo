"""
Villa Staff Memo Web App — No-Login Demo (auto staff)
-----------------------------------------------------
Quickstart (macOS):
1) pip3 install flask flask-login flask_sqlalchemy
2) python3 app.py
3) Open http://127.0.0.1:8000

Changes vs. previous:
- Login page removed. System auto-signs in a default Staff user on each request.
- You can use all pages (Dashboard / SOP / Tasks / Checks) without credentials.

Demo seed:
- Admin: admin@example.com / 9910
- Staff: staff@example.com / 9910  (auto login as this account)

Notes:
- Single-file app. Templates inline with Bootstrap 5.
- Images saved to ./uploads. Basic i18n via ?lang=zh|ja|en (cookie persisted).
- Villa names are configurable via env var `VILLA_NAMES` (comma or newline separated). On Render, use **Secret Files** `.env`.
- Password hashing uses pbkdf2:sha256 to avoid scrypt dependency.
"""

from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict
import re

from flask import (
    Flask, request, redirect, url_for, flash, send_from_directory,
    abort, g
)
from flask import render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Optional: load env vars from .env or secret files (Render) ---
try:
    from dotenv import load_dotenv, find_dotenv
    # Load .env from project root if present
    load_dotenv(find_dotenv(), override=True)
    # Load secret file if Render Secret Files mounted at this path
    if os.path.exists('/etc/secrets/.env'):
        load_dotenv('/etc/secrets/.env', override=True)
except Exception:
    pass

# ------------------------------
# App & Config
# ------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///memo_demo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = str(Path('uploads').absolute())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Allow env overrides for cloud deploy (Render, etc.)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', app.config['SQLALCHEMY_DATABASE_URI'])
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', app.config['UPLOAD_FOLDER'])

Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Jinja DictLoader for inline templates
from jinja2 import DictLoader

# ------------------------------
# Simple i18n
# ------------------------------
I18N: Dict[str, Dict[str, str]] = {
    'zh': {
        'app_title': 'Villa Staff Memo',
        'login': '登入',
        'email': '郵箱',
        'password': '密碼',
        'logout': '登出',
        'dashboard': '控制台',
        'sops': 'SOP 標準作業',
        'tasks': '任務工單',
        'checks': '每日檢查',
        'create': '新增',
        'edit': '編輯',
        'delete': '刪除',
        'save': '保存',
        'status': '狀態',
        'pending': '待處理',
        'in_progress': '處理中',
        'done': '已完成',
        'assigned_to': '指派給',
        'due_date': '到期日',
        'title': '標題',
        'content': '內容',
        'category': '分類',
        'submit': '提交',
        'new_task': '新增任務',
        'new_sop': '新增 SOP',
        'new_check': '新增檢查',
        'villa': '別墅',
        'area': '區域',
        'notes': '備註',
        'photo': '照片',
        'actions': '操作',
        'hello': '您好',
        'role_admin': '管理員',
        'role_staff': '員工',
        'switch_lang': '語言',
        'welcome_msg': '今日待辦與提醒',
        'upload_ok': '已上傳',
        'sop_by_villa': '各別墅 SOP 快捷',
        'all_villas': '全部別墅',
        'access_title': '訪問驗證',
        'access_code': '入口口令',
        'access_hint': '請輸入口令以進入系統',
        'access_submit': '確認',
        'access_denied': '口令錯誤',
        'filter_villa': '別墅篩選',
    },
    'ja': {
        'app_title': 'ヴィラ・スタッフ・メモ',
        'login': 'ログイン',
        'email': 'メール',
        'password': 'パスワード',
        'logout': 'ログアウト',
        'dashboard': 'ダッシュボード',
        'sops': 'SOP 標準作業',
        'tasks': 'タスク',
        'checks': '日次点検',
        'create': '新規',
        'edit': '編集',
        'delete': '削除',
        'save': '保存',
        'status': 'ステータス',
        'pending': '未対応',
        'in_progress': '対応中',
        'done': '完了',
        'assigned_to': '担当者',
        'due_date': '期限',
        'title': 'タイトル',
        'content': '内容',
        'category': 'カテゴリ',
        'submit': '送信',
        'new_task': 'タスク追加',
        'new_sop': 'SOP追加',
        'new_check': '点検記録',
        'villa': 'ヴィラ',
        'area': 'エリア',
        'notes': 'メモ',
        'photo': '写真',
        'actions': '操作',
        'hello': 'こんにちは',
        'role_admin': '管理者',
        'role_staff': 'スタッフ',
        'switch_lang': '言語',
        'welcome_msg': '本日のタスクとリマインド',
        'upload_ok': 'アップロードしました',
        'sop_by_villa': 'ヴィラ別 SOP ショートカット',
        'all_villas': 'すべてのヴィラ',
        'access_title': 'アクセス認証',
        'access_code': 'アクセスコード',
        'access_hint': 'コードを入力してください',
        'access_submit': '送信',
        'access_denied': 'コードが間違っています',
        'filter_villa': 'ヴィラ絞り込み',
    },
    'en': {
        'app_title': 'Villa Staff Memo',
        'login': 'Login',
        'email': 'Email',
        'password': 'Password',
        'logout': 'Logout',
        'dashboard': 'Dashboard',
        'sops': 'SOPs',
        'tasks': 'Tasks',
        'checks': 'Daily Checks',
        'create': 'Create',
        'edit': 'Edit',
        'delete': 'Delete',
        'save': 'Save',
        'status': 'Status',
        'pending': 'Pending',
        'in_progress': 'In Progress',
        'done': 'Done',
        'assigned_to': 'Assigned To',
        'due_date': 'Due Date',
        'title': 'Title',
        'content': 'Content',
        'category': 'Category',
        'submit': 'Submit',
        'new_task': 'New Task',
        'new_sop': 'New SOP',
        'new_check': 'New Check',
        'villa': 'Villa',
        'area': 'Area',
        'notes': 'Notes',
        'photo': 'Photo',
        'actions': 'Actions',
        'hello': 'Hello',
        'role_admin': 'Admin',
        'role_staff': 'Staff',
        'switch_lang': 'Language',
        'welcome_msg': "Today's todos & reminders",
        'upload_ok': 'Uploaded',
        'sop_by_villa': 'SOP by Villa',
        'all_villas': 'All Villas',
        'access_title': 'Access Required',
        'access_code': 'Access Code',
        'access_hint': 'Enter the code to continue',
        'access_submit': 'Confirm',
        'access_denied': 'Invalid access code',
        'filter_villa': 'Filter by Villa',
    }
}


def _get_lang() -> str:
    try:
        raw = (request.args.get('lang') or request.cookies.get('lang') or 'zh').lower()
    except Exception:
        raw = 'zh'
    return raw if raw in I18N else 'zh'

def t(key: str) -> str:
    lang = _get_lang()
    return I18N.get(lang, I18N['zh']).get(key, key)


def with_lang(url: str) -> str:
    lang = _get_lang()
    sep = '&' if ('?' in url) else '?'
    return f"{url}{sep}lang={lang}" if lang else url


# Villas list (24) — configurable via env var VILLA_NAMES (comma or newline separated)
# Example in .env / Secret File:
# VILLA_NAMES=Sunset,Aqua,Coral,Emerald,...(24 names)

def _load_villas() -> list:
    """Return 24 villa names.
    Priority: env var VILLA_NAMES (comma/newline separated) →
    fallback to the custom default list below (your provided names),
    then pad/truncate to exactly 24.
    """
    raw = os.environ.get('VILLA_NAMES', '').strip()
    if raw:
        # Split by commas and/or newlines safely using escaped literals
        tmp = raw.replace('\r', '\n').replace(',', '\n')
        names = [n.strip() for n in tmp.split('\n') if n.strip()]
    else:
        # ← Default list from your request (22 names)
        names = [
            "Grand Villa",
            "Villa A",
            "Villa B",
            "Villa C",
            "Panorama Villa",
            "Sankando Office",
            "Glamping Office",
            "MOKA",
            "KOKO",
            "MARU",
            "RUNA",
            "MEI",
            "RIN",
            "LEO",
            "MOMO",
            "New DOME",
            "CUBE",
            "Gekkouen",
            "Villa D",
            "Villa E",
            "Villa F",
            "Villa G",
        ]
    # normalize to exactly 24 entries: trim extra or pad with placeholders
    names = names[:24]
    if len(names) < 24:
        start = len(names) + 1
        names += [f"Villa {i:02d}" for i in range(start, 25)]
    return names

VILLAS = _load_villas()






# ------------------------------
# Models
# ------------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), default='staff')  # 'admin' or 'staff'
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, pw: str):
        # Explicitly use pbkdf2:sha256 to avoid scrypt dependency
        self.password_hash = generate_password_hash(pw, method='pbkdf2:sha256')

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)


class SOP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    villa = db.Column(db.String(80), nullable=True, index=True)  # NEW: per-villa routing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/in_progress/done
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    due_date = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Check(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    villa = db.Column(db.String(80), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_by = db.relationship('User')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------------
# Templates (inline)
# ------------------------------
BASE = """
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{{ t('app_title') }}</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\">
  <style>
    body { padding-top: 4.5rem; }
    .navbar-brand { font-weight: 700; }
    .card { border-radius: 1rem; }
    .btn { border-radius: .75rem; }
    .form-control, .form-select { border-radius: .75rem; }
  </style>
</head>
<body>
<nav class=\"navbar navbar-expand-lg navbar-dark bg-dark fixed-top\">
  <div class=\"container-fluid\">
    <a class=\"navbar-brand\" href=\"{{ with_lang(url_for('dashboard')) }}\">{{ t('app_title') }}</a>
    <button class=\"navbar-toggler\" type=\"button\" data-bs-toggle=\"collapse\" data-bs-target=\"#nav\" aria-controls=\"nav\" aria-expanded=\"false\" aria-label=\"Toggle navigation\">
      <span class=\"navbar-toggler-icon\"></span>
    </button>
    <div class=\"collapse navbar-collapse\" id=\"nav\">
      <ul class=\"navbar-nav me-auto mb-2 mb-lg-0\">
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"{{ with_lang(url_for('dashboard')) }}\">{{ t('dashboard') }}</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"{{ with_lang(url_for('list_sops')) }}\">{{ t('sops') }}</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"{{ with_lang(url_for('list_tasks')) }}\">{{ t('tasks') }}</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"{{ with_lang(url_for('list_checks')) }}\">{{ t('checks') }}</a></li>
      </ul>
      <form class=\"d-flex\" method=\"get\" action=\"{{ request.path }}\">
        <select class=\"form-select\" name=\"lang\" onchange=\"this.form.submit()\">
          {% set cur = request.args.get('lang') or request.cookies.get('lang') or 'zh' %}
          <option value=\"zh\" {% if cur=='zh' %}selected{% endif %}>中文</option>
          <option value=\"ja\" {% if cur=='ja' %}selected{% endif %}>日本語</option>
          <option value=\"en\" {% if cur=='en' %}selected{% endif %}>English</option>
        </select>
      </form>
      <span class=\"navbar-text text-light ms-3\">{{ t('hello') }}，{{ (current_user.name if current_user.is_authenticated else 'Staff') }} ({{ t('role_staff') }})</span>
    </div>
  </div>
</nav>
<div class=\"container py-3\">
  {% block body %}{% endblock %}
</div>
<script src=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js\"></script>
</body>
</html>
"""

LOGIN = """
{% extends 'BASE' %}
{% block body %}
<div class=\"alert alert-info mt-3\">Login is disabled. Redirecting to dashboard...</div>
<meta http-equiv=\"refresh\" content=\"0; url={{ with_lang(url_for('dashboard')) }}\">
{% endblock %}
"""

DASH = """
{% extends 'BASE' %}
{% block body %}
  <div class="row g-3">
    <div class="col-12">
      <div class="card shadow-sm">
        <div class="card-body">
          <h5 class="card-title">{{ t('sop_by_villa') }}</h5>
          <div class="row row-cols-2 row-cols-sm-3 row-cols-md-4 row-cols-lg-6 g-2">
            <div class="col">
              <a class="btn btn-outline-secondary w-100" href="{{ with_lang(url_for('list_sops')) }}">{{ t('all_villas') }}</a>
            </div>
            {% for v in villas %}
            <div class="col">
              <a class="btn btn-outline-primary w-100" href="{{ with_lang(url_for('list_sops', villa=v)) }}">{{ v }}</a>
            </div>
            {% endfor %}
          </div>
        </div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card shadow-sm">
        <div class="card-body">
          <h5 class="card-title">{{ t('tasks') }}</h5>
          <a class="btn btn-sm btn-primary mb-2" href="{{ with_lang(url_for('new_task')) }}">＋ {{ t('new_task') }}</a>
          <ul class="list-group">
            {% for task in tasks %}
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>{{ task.title }}</strong>
                <div class="small text-muted">{{ t('status') }}: {{ t(task.status) }}{% if task.assigned_to %}｜{{ t('assigned_to') }}: {{ task.assigned_to.name }}{% endif %}
                {% if task.due_date %}｜{{ t('due_date') }}: {{ task.due_date.date() }}{% endif %}</div>
              </div>
              <div>
                <a class="btn btn-sm btn-outline-secondary" href="{{ with_lang(url_for('edit_task', task_id=task.id)) }}">{{ t('edit') }}</a>
              </div>
            </li>
            {% else %}
            <li class="list-group-item">—</li>
            {% endfor %}
          </ul>
        </div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card shadow-sm">
        <div class="card-body">
          <h5 class="card-title">{{ t('checks') }}</h5>
          <a class="btn btn-sm btn-primary mb-2" href="{{ with_lang(url_for('new_check')) }}">＋ {{ t('new_check') }}</a>
          <ul class="list-group">
            {% for c in checks %}
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>{{ c.villa }} / {{ c.area }}</strong>
                <div class="small text-muted">{{ c.created_at.strftime('%Y-%m-%d %H:%M') }}｜{{ t('status') }}: {{ t(c.status) }}</div>
              </div>
              <a class="btn btn-sm btn-outline-secondary" href="{{ with_lang(url_for('edit_check', check_id=c.id)) }}">{{ t('edit') }}</a>
            </li>
            {% else %}
            <li class="list-group-item">—</li>
            {% endfor %}
          </ul>
        </div>
      </div>
      <div class="card shadow-sm mt-3">
        <div class="card-body">
          <h6 class="mb-1">{{ t('welcome_msg') }}</h6>
          <div class="text-muted small">Lang = {{ request.args.get('lang') or request.cookies.get('lang') or 'zh' }}</div>
        </div>
      </div>
    </div>
  </div>
{% endblock %}
"""

SOPS = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4>{{ t('sops') }}{% if villa %} — {{ villa }}{% endif %}</h4>
  <div class="d-flex gap-2">
    <form class="d-flex" method="get" action="{{ url_for('list_sops') }}">
      <input type="hidden" name="lang" value="{{ request.args.get('lang') or request.cookies.get('lang') or 'zh' }}">
      <select class="form-select me-2" name="villa" onchange="this.form.submit()">
        <option value="">{{ t('all_villas') }}</option>
        {% for v in villas %}
        <option value="{{ v }}" {% if villa==v %}selected{% endif %}>{{ v }}</option>
        {% endfor %}
      </select>
    </form>
    <a class="btn btn-primary" href="{{ with_lang(url_for('new_sop', villa=villa)) }}">＋ {{ t('new_sop') }}</a>
  </div>
</div>
<div class="list-group">
  {% for s in sops %}
  <a class="list-group-item list-group-item-action" href="{{ with_lang(url_for('edit_sop', sop_id=s.id)) }}">
    <div class="d-flex w-100 justify-content-between">
      <h5 class="mb-1">{{ s.title }}</h5>
      <small class="text-muted">{{ s.category }}{% if s.villa %} ｜ {{ s.villa }}{% endif %}</small>
    </div>
    <p class="mb-1 text-muted">{{ s.content[:120] }}{% if s.content|length>120 %}...{% endif %}</p>
  </a>
  {% else %}
  <div class="text-muted">—</div>
  {% endfor %}
</div>
{% endblock %}
"""

SOP_FORM = """
{% extends 'BASE' %}
{% block body %}
<h4>{{ 'Edit' if sop else 'Create' }} SOP</h4>
<form method="post">
  <div class="mb-3">
    <label class="form-label">{{ t('title') }}</label>
    <input name="title" class="form-control" value="{{ sop.title if sop else '' }}" required>

TASKS = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4>{{ t('tasks') }}</h4>
  <a class="btn btn-primary" href="{{ with_lang(url_for('new_task')) }}">＋ {{ t('new_task') }}</a>
</div>
<ul class="list-group">
{% for task in tasks %}
  <li class="list-group-item d-flex justify-content-between align-items-center">
    <div>
      <strong>{{ task.title }}</strong>
      <div class="small text-muted">{{ t('status') }}: {{ t(task.status) }}{% if task.assigned_to %}｜{{ t('assigned_to') }}: {{ task.assigned_to.name }}{% endif %}
      {% if task.due_date %}｜{{ t('due_date') }}: {{ task.due_date.date() }}{% endif %}</div>
    </div>
    <a class="btn btn-sm btn-outline-secondary" href="{{ with_lang(url_for('edit_task', task_id=task.id)) }}">{{ t('edit') }}</a>
  </li>
{% else %}
  <li class="list-group-item">—</li>
{% endfor %}
</ul>
{% endblock %}
"""

TASK_FORM = """
{% extends 'BASE' %}
{% block body %}
<h4>{{ 'Edit' if task else 'Create' }} {{ t('tasks') }}</h4>
<form method="post">
  <div class="mb-3">
    <label class="form-label">{{ t('title') }}</label>
    <input name="title" class="form-control" value="{{ task.title if task else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('status') }}</label>
    <select name="status" class="form-select">
      {% for s in ['pending','in_progress','done'] %}
      <option value="{{ s }}" {% if task and task.status==s %}selected{% endif %}>{{ t(s) }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('assigned_to') }}</label>
    <select name="assigned_to" class="form-select">
      <option value="">—</option>
      {% for u in users %}
      <option value="{{ u.id }}" {% if task and task.assigned_to and task.assigned_to.id==u.id %}selected{% endif %}>{{ u.name }} ({{ u.role }})</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('due_date') }}</label>
    <input type="date" name="due_date" class="form-control" value="{{ task.due_date.date() if task and task.due_date else '' }}">
  </div>
  <button class="btn btn-primary">{{ t('save') }}</button>
</form>
{% endblock %}
"""

CHECKS = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4>{{ t('checks') }}</h4>
  <div class="d-flex gap-2">
    <form class="d-flex" method="get" action="{{ url_for('list_checks') }}">
      <input type="hidden" name="lang" value="{{ request.args.get('lang') or request.cookies.get('lang') or 'zh' }}">
      <select class="form-select me-2" name="villa" onchange="this.form.submit()">
        <option value="">{{ t('all_villas') }}</option>
        {% for v in villas %}
        <option value="{{ v }}" {% if request.args.get('villa')==v %}selected{% endif %}>{{ v }}</option>
        {% endfor %}
      </select>
    </form>
    <a class="btn btn-primary" href="{{ with_lang(url_for('new_check', villa=request.args.get('villa'))) }}">＋ {{ t('new_check') }}</a>
  </div>
</div>
<ul class="list-group">
{% for c in checks %}
  <li class="list-group-item d-flex justify-content-between align-items-center">
    <div>
      <strong>{{ c.villa }} / {{ c.area }}</strong>
      <div class="small text-muted">{{ c.created_at.strftime('%Y-%m-%d %H:%M') }}｜{{ t('status') }}: {{ t(c.status) }}</div>
      {% if c.notes %}<div class="text-muted small">{{ c.notes }}</div>{% endif %}
      {% if c.photo_path %}<a href="{{ url_for('uploaded_file', filename=c.photo_path.split('/')[-1]) }}" target="_blank">{{ t('photo') }}</a>{% endif %}
    </div>
    <a class="btn btn-sm btn-outline-secondary" href="{{ with_lang(url_for('edit_check', check_id=c.id)) }}">{{ t('edit') }}</a>
  </li>
{% else %}
  <li class="list-group-item">—</li>
{% endfor %}
</ul>
{% endblock %}
"""

CHECK_FORM = """
{% extends 'BASE' %}
{% block body %}
<h4>{{ 'Edit' if check else 'Create' }} {{ t('checks') }}</h4>
<form method="post" enctype="multipart/form-data">
  <div class="mb-3">
    <label class="form-label">{{ t('villa') }}</label>
    <select name="villa" class="form-select" required>
      <option value="">—</option>
      {% for v in villas %}
      <option value="{{ v }}" {% if (check and check.villa==v) or (not check and request.args.get('villa')==v) %}selected{% endif %}>{{ v }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('area') }}</label>
    <input name="area" class="form-control" value="{{ check.area if check else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('notes') }}</label>
    <textarea name="notes" class="form-control" rows="4">{{ check.notes if check else '' }}</textarea>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('photo') }}</label>
    <input type="file" name="photo" class="form-control" accept="image/*">
    {% if check and check.photo_path %}
      <div class="form-text"><a href="{{ url_for('uploaded_file', filename=check.photo_path.split('/')[-1]) }}" target="_blank">{{ t('photo') }}</a></div>
    {% endif %}
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('status') }}</label>
    <select name="status" class="form-select">
      {% for s in ['pending','in_progress','done'] %}
      <option value="{{ s }}" {% if check and check.status==s %}selected{% endif %}>{{ t(s) }}</option>
      {% endfor %}
    </select>
  </div>
  <button class="btn btn-primary">{{ t('save') }}</button>
</form>
{% endblock %}
"""
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('area') }}</label>
    <input name="area" class="form-control" value="{{ check.area if check else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('notes') }}</label>
    <textarea name="notes" class="form-control" rows="4">{{ check.notes if check else '' }}</textarea>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('photo') }}</label>
    <input type="file" name="photo" class="form-control" accept="image/*">
    {% if check and check.photo_path %}
      <div class="form-text"><a href="{{ url_for('uploaded_file', filename=check.photo_path.split('/')[-1]) }}" target="_blank">{{ t('photo') }}</a></div>
    {% endif %}
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('status') }}</label>
    <select name="status" class="form-select">
      {% for s in ['pending','in_progress','done'] %}
      <option value="{{ s }}" {% if check and check.status==s %}selected{% endif %}>{{ t(s) }}</option>
      {% endfor %}
    </select>
  </div>
  <button class="btn btn-primary">{{ t('save') }}</button>
</form>
{% endblock %}
"""

# Register templates into Jinja env
app.jinja_env.globals.update(t=t, with_lang=with_lang)
ACCESS = """
{% extends 'BASE' %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <div class="card shadow-sm">
      <div class="card-body">
        <h4 class="mb-3">{{ t('access_title') }}</h4>
        <p class="text-muted">{{ t('access_hint') }}</p>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">{{ t('access_code') }}</label>
            <input type="password" class="form-control" name="access" required>
          </div>
          <button class="btn btn-primary">{{ t('access_submit') }}</button>
        </form>
      </div>
    </div>
  </div>
</div>
{% endblock %}
"""

app.jinja_loader = DictLoader({
    'BASE': BASE,
    'LOGIN': LOGIN,
    'DASH': DASH,
    'SOPS': SOPS,
    'SOP_FORM': SOP_FORM,
    'TASKS': TASKS,
    'TASK_FORM': TASK_FORM,
    'CHECKS': CHECKS,
    'CHECK_FORM': CHECK_FORM,
    'ACCESS': ACCESS,
})

# ------------------------------
# Routes
# ------------------------------
@app.route('/health')
def health():
    return 'ok', 200

@app.before_request
def persist_lang_cookie_and_auto_login():
    # 1) Access gate (optional via ACCESS_CODE)
    g.lang_to_set = None
    lang = request.args.get('lang')
    if lang:
        g.lang_to_set = lang

    access_code = os.environ.get('ACCESS_CODE')
    if access_code:
        # allowlist endpoints
        allowed_eps = {'health', 'access', 'static'}
        ep = (request.endpoint or '').split('.')[-1]
        has_cookie = request.cookies.get('ac') == access_code
        from_query = request.args.get('access')
        if from_query and from_query == access_code:
            # mark to set cookie after response
            g._set_access_cookie = True
        elif not has_cookie and ep not in allowed_eps:
            # redirect to /access with next param
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for('access', next=nxt))

    # 2) Auto-login as Staff (no login page)
    if not current_user.is_authenticated:
        staff = User.query.filter_by(email='staff@example.com').first()
        if staff:
            login_user(staff)

@app.after_request
def apply_lang_cookie(response):
    # Apply language cookie if requested in this cycle
    try:
        if getattr(g, 'lang_to_set', None):
            response.set_cookie('lang', g.lang_to_set, max_age=30*24*3600)
        if getattr(g, '_set_access_cookie', False):
            # simple cookie to remember ACCESS_CODE validation
            response.set_cookie('ac', os.environ.get('ACCESS_CODE',''), max_age=7*24*3600, httponly=True)
    except Exception:
        pass
    return response


@app.route('/')
def index():
    return redirect(with_lang(url_for('dashboard')))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Login disabled: just go to dashboard
    return redirect(with_lang(url_for('dashboard')))

@app.route('/access', methods=['GET','POST'])
def access():
    access_code = os.environ.get('ACCESS_CODE')
    if not access_code:
        # If no gate configured, just go home
        return redirect(with_lang(url_for('dashboard')))
    if request.method == 'POST':
        if request.form.get('access') == access_code:
            g._set_access_cookie = True
            nxt = request.args.get('next') or url_for('dashboard')
            return redirect(with_lang(nxt))
        else:
            flash(t('access_denied'), 'warning')
    return render_template('ACCESS')


@app.route('/logout')
def logout():
    # Logout disabled in no-login mode; still clear session then redirect
    try:
        logout_user()
    except Exception:
        pass
    return redirect(with_lang(url_for('dashboard')))


@app.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.order_by(Task.created_at.desc()).limit(10).all()
    checks = Check.query.order_by(Check.created_at.desc()).limit(10).all()
    return render_template('DASH', tasks=tasks, checks=checks, villas=VILLAS)


# ---- SOPs ----
@app.route('/sops')
@login_required
def list_sops():
    villa = request.args.get('villa') or None
    q = SOP.query
    if villa:
        q = q.filter(SOP.villa == villa)
    sops = q.order_by(SOP.created_at.desc()).all()
    return render_template('SOPS', sops=sops, villa=villa, villas=VILLAS)


@app.route('/sops/new', methods=['GET', 'POST'])
@login_required
def new_sop():
    if request.method == 'POST':
        s = SOP(
            title=request.form['title'],
            category=request.form['category'],
            content=request.form['content'],
            villa=(request.form.get('villa') or None),
        )
        db.session.add(s)
        db.session.commit()
        return redirect(with_lang(url_for('list_sops', villa=s.villa)))
    return render_template('SOP_FORM', sop=None, villas=VILLAS)


@app.route('/sops/<int:sop_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sop(sop_id):
    s = SOP.query.get_or_404(sop_id)
    if request.method == 'POST':
        s.title = request.form['title']
        s.category = request.form['category']
        s.content = request.form['content']
        s.villa = request.form.get('villa') or None
        db.session.commit()
        return redirect(with_lang(url_for('list_sops', villa=s.villa)))
    return render_template('SOP_FORM', sop=s, villas=VILLAS)


# ---- Tasks ----
@app.route('/tasks')
@login_required
def list_tasks():
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('TASKS', tasks=tasks)


@app.route('/tasks/new', methods=['GET', 'POST'])
@login_required
def new_task():
    if request.method == 'POST':
        title = request.form['title']
        status = request.form.get('status','pending')
        assigned_to_id = request.form.get('assigned_to') or None
        due_date = request.form.get('due_date')
        task = Task(title=title, status=status, created_by=current_user)
        if assigned_to_id:
            task.assigned_to = User.query.get(int(assigned_to_id))
        if due_date:
            task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
        db.session.add(task)
        db.session.commit()
        return redirect(with_lang(url_for('list_tasks')))
    users = User.query.order_by(User.name).all()
    return render_template('TASK_FORM', task=None, users=users)


@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if request.method == 'POST':
        task.title = request.form['title']
        task.status = request.form.get('status','pending')
        assigned_to_id = request.form.get('assigned_to') or None
        due_date = request.form.get('due_date')
        task.assigned_to = User.query.get(int(assigned_to_id)) if assigned_to_id else None
        task.due_date = datetime.strptime(due_date, '%Y-%m-%d') if due_date else None
        db.session.commit()
        return redirect(with_lang(url_for('list_tasks')))
    users = User.query.order_by(User.name).all()
    return render_template('TASK_FORM', task=task, users=users)


# ---- Checks ----
@app.route('/checks')
@login_required
def list_checks():
    villa = request.args.get('villa') or None
    q = Check.query
    if villa:
        q = q.filter(Check.villa == villa)
    checks = q.order_by(Check.created_at.desc()).all()
    return render_template('CHECKS', checks=checks, villas=VILLAS)


def allowed_file(fn: str) -> bool:
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in {'png','jpg','jpeg','gif','webp'}


@app.route('/checks/new', methods=['GET', 'POST'])
@login_required
def new_check():
    if request.method == 'POST':
        villa = request.form['villa']
        area = request.form['area']
        notes = request.form.get('notes')
        status = request.form.get('status','pending')
        photo_path = None
        file = request.files.get('photo')
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Unsupported file type', 'warning')
                return redirect(request.url)
            filename = datetime.utcnow().strftime('%Y%m%d%H%M%S_') + secure_filename(file.filename)
            fullpath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(fullpath)
            photo_path = fullpath
            flash(t('upload_ok'), 'success')
        c = Check(villa=villa, area=area, notes=notes, status=status, created_by=current_user, photo_path=photo_path)
        db.session.add(c)
        db.session.commit()
        return redirect(with_lang(url_for('list_checks')))
    return render_template('CHECK_FORM', check=None, villas=VILLAS)


@app.route('/checks/<int:check_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_check(check_id):
    c = Check.query.get_or_404(check_id)
    if request.method == 'POST':
        c.villa = request.form['villa']
        c.area = request.form['area']
        c.notes = request.form.get('notes')
        c.status = request.form.get('status','pending')
        file = request.files.get('photo')
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Unsupported file type', 'warning')
                return redirect(request.url)
            filename = datetime.utcnow().strftime('%Y%m%d%H%M%S_') + secure_filename(file.filename)
            fullpath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(fullpath)
            c.photo_path = fullpath
            flash(t('upload_ok'), 'success')
        db.session.commit()
        return redirect(with_lang(url_for('list_checks')))
    return render_template('CHECK_FORM', check=c, villas=VILLAS)


# ---- Uploads ----
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ------------------------------
# DB Init & Seed
# ------------------------------
@app.cli.command('initdb')
def initdb_command():
    """flask initdb — reset and seed demo data"""
    db.drop_all()
    db.create_all()
    seed()
    print('Initialized the database with demo data.')


def seed():
    if User.query.count() == 0:
        admin = User(email='admin@example.com', name='Admin', role='admin')
        admin.set_password('9910')
        staff = User(email='staff@example.com', name='Staff', role='staff')
        staff.set_password('9910')
        db.session.add_all([admin, staff])
        db.session.commit()

    if SOP.query.count() == 0:
        db.session.add_all([
            SOP(
                title='客房清潔（退房）',
                category='清潔',
                villa=(VILLAS[0] if VILLAS else None),
                content="""1) 換床品
2) 吸塵與拖地
3) 垃圾清理
4) 補充備品"""
            ),
            SOP(
                title='花園巡檢',
                category='園藝',
                villa=(VILLAS[1] if len(VILLAS) > 1 else None),
                content="""1) 除草
2) 澆水
3) 確認照明
4) 報告異常"""
            )
        ])
        db.session.commit()

    if Task.query.count() == 0:
        admin = User.query.filter_by(email='admin@example.com').first()
        staff = User.query.filter_by(email='staff@example.com').first()
        db.session.add_all([
            Task(title='補充毛巾（A棟）', status='pending', assigned_to=staff, created_by=admin, due_date=datetime.utcnow()+timedelta(days=1)),
            Task(title='更換過濾器（Panorama）', status='in_progress', assigned_to=staff, created_by=admin),
        ])
        db.session.commit()


# Ensure DB exists and seeded on first run
with app.app_context():
    db.create_all()
    # Lightweight migration: ensure sop.villa column exists and index created
    try:
        cols = [r[1] for r in db.engine.execute("PRAGMA table_info(sop)").fetchall()]
        if 'villa' not in cols:
            db.engine.execute("ALTER TABLE sop ADD COLUMN villa VARCHAR(80)")
        db.engine.execute("CREATE INDEX IF NOT EXISTS ix_sop_villa ON sop (villa)")
    except Exception as e:
        print('DB migration check failed:', e)
    seed()


# ------------------------------
# Run
# ------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8000)
