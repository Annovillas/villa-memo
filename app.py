# -*- coding: utf-8 -*-
"""
Villa Staff Memo — Flask single‑file demo (Render‑friendly)
-----------------------------------------------------------
- Local run:  python3 app.py  → http://127.0.0.1:8000
- Seed users:
    admin@villa.local / 10051005+   (role=admin,  name=admin)
    stanley@villa.local / 0585      (role=staff,  name=Stanley)
- Optional access gate: set ACCESS_CODE in env → visit /access
- Self‑test page: /selftest (no login needed)
- 24 villa shortcuts on dashboard; override names via env VILLA_NAMES (comma/newline)
"""
from __future__ import annotations

import os
import hmac
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

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
from jinja2 import DictLoader

# --- Optional dotenv (also loads Render Secret Files at /etc/secrets/.env) ---
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=True)
    if os.path.exists('/etc/secrets/.env'):
        load_dotenv('/etc/secrets/.env', override=True)
except Exception:
    pass

# ------------------------------
# App & Config
# ------------------------------

def _prepare_sqlite_uri(raw: str) -> str:
    """Normalize SQLite URI so its directory exists & is writable on cloud hosts.
    Robust against unwritable env paths. Also *touches* the DB file to avoid
    "unable to open database file" on some hosts.

    Rules:
    - sqlite:///relative.db  → place under DATA_DIR or /tmp/vsmdata
    - sqlite:////absolute.db → ensure parent dir exists (and file touched)
    - non-sqlite schemes     → passthrough
    """
    try:
        if not raw or not raw.startswith('sqlite'):
            return raw

        # choose a safe base dir (don't trust UPLOAD_FOLDER env as it may be RO)
        safe_base = os.environ.get('DATA_DIR') or '/tmp/vsmdata'
        base_path = Path(safe_base)
        base_path.mkdir(parents=True, exist_ok=True)

        if raw.startswith('sqlite:////'):  # absolute
            abs_path = Path(raw.replace('sqlite:////', '/', 1))
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                abs_path.touch(exist_ok=True)
            except Exception:
                pass
            return 'sqlite:////' + str(abs_path).lstrip('/')

        if raw.startswith('sqlite:///'):   # relative
            rel = raw[len('sqlite:///'):]
            db_file = base_path / rel
            try:
                db_file.parent.mkdir(parents=True, exist_ok=True)
                db_file.touch(exist_ok=True)
            except Exception:
                # last resort
                db_file = Path('/tmp/vsmdata/fallback.db')
                db_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    db_file.touch(exist_ok=True)
                except Exception:
                    pass
            return 'sqlite:////' + str(db_file).lstrip('/')

        return raw
    except Exception:
        # panic fallback
        pf = Path('/tmp/vsmdata/panic.db')
        pf.parent.mkdir(parents=True, exist_ok=True)
        try:
            pf.touch(exist_ok=True)
        except Exception:
            pass
        return 'sqlite:////' + str(pf).lstrip('/')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# ensure upload dir early (independent from DB path)
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', '/tmp/uploads')
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

# Build a *safe* SQLite URI
raw_db = os.environ.get('DATABASE_URL', 'sqlite:///memo_demo.db')
app.config['SQLALCHEMY_DATABASE_URI'] = _prepare_sqlite_uri(raw_db)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLite engine options for WSGI servers
if str(app.config['SQLALCHEMY_DATABASE_URI']).startswith('sqlite'):
    app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].setdefault('connect_args', {
        'check_same_thread': False,
        'timeout': 30,
    })

# Create DB handle
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ------------------------------
# i18n
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


# ------------------------------
# Villas list (24)
# ------------------------------

def _load_villas() -> List[str]:
    raw = os.environ.get('VILLA_NAMES', '').strip()
    if raw:
        parts: List[str] = []
        for line in raw.splitlines():
            for p in line.split(','):
                p = p.strip()
                if p:
                    parts.append(p)
        names = parts
    else:
        names = [
            'Grand Villa', 'Villa A', 'Villa B', 'Villa C', 'Panorama Villa',
            'Sankando Office', 'Glamping Office', 'MOKA', 'KOKO', 'MARU',
            'RUNA', 'MEI', 'RIN', 'LEO', 'MOMO', 'New DOME', 'CUBE',
            'Gekkouen', 'Villa D', 'Villa E', 'Villa F', 'Villa G',
            'Villa H', 'Villa I'
        ]
    names = names[:24]
    if len(names) < 24:
        start = len(names) + 1
        names += [f'Villa {i:02d}' for i in range(start, 25)]
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
        """Prefer PBKDF2 (werkzeug), fallback to HMAC‑SHA256 when pbkdf2 is unavailable."""
        try:
            self.password_hash = generate_password_hash(pw, method='pbkdf2:sha256')
        except Exception:
            salt = secrets.token_hex(16)
            digest = hmac.new(salt.encode('utf-8'), pw.encode('utf-8'), hashlib.sha256).hexdigest()
            self.password_hash = f"sha256${salt}${digest}"

    def check_password(self, pw: str) -> bool:
        ph = self.password_hash or ''
        if ph.startswith('sha256$'):
            try:
                _, salt, digest = ph.split('$', 2)
                calc = hmac.new(salt.encode('utf-8'), pw.encode('utf-8'), hashlib.sha256).hexdigest()
                return hmac.compare_digest(digest, calc)
            except Exception:
                return False
        try:
            return check_password_hash(ph, pw)
        except Exception:
            return False


class SOP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    villa = db.Column(db.String(80), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending')
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])


# ------------------------------
# Templates (Jinja2 DictLoader)
# ------------------------------
BASE = """
{% set cur_lang = request.args.get('lang') or request.cookies.get('lang') or 'zh' %}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ t('app_title') }}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <style>
    body { padding-top: 4.5rem; }
    .navbar-brand { font-weight: 700; }
    .card { border-radius: 1rem; }
    .btn, .form-control, .form-select { border-radius: .75rem; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ with_lang(url_for('dashboard')) }}">{{ t('app_title') }}</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nav">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="nav">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item"><a class="nav-link" href="{{ with_lang(url_for('dashboard')) }}">{{ t('dashboard') }}</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ with_lang(url_for('list_sops')) }}">{{ t('sops') }}</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ with_lang(url_for('list_tasks')) }}">{{ t('tasks') }}</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ with_lang(url_for('list_checks')) }}">{{ t('checks') }}</a></li>
        {% if current_user.is_authenticated and current_user.role=='admin' %}
        <li class="nav-item"><a class="nav-link" href="{{ with_lang(url_for('admin_users')) }}">Users</a></li>
        {% endif %}
      </ul>
      <form class="d-flex" method="get" action="{{ request.path }}">
        <select class="form-select" name="lang" onchange="this.form.submit()">
          <option value="zh" {% if cur_lang=='zh' %}selected{% endif %}>中文</option>
          <option value="ja" {% if cur_lang=='ja' %}selected{% endif %}>日本語</option>
          <option value="en" {% if cur_lang=='en' %}selected{% endif %}>English</option>
        </select>
      </form>
      <span class="navbar-text text-light ms-3">
        {{ t('hello') }}，{{ (current_user.name if current_user.is_authenticated else 'Guest') }}
        {% if current_user.is_authenticated %}({{ current_user.role }}){% endif %}
      </span>
      {% if current_user.is_authenticated %}
      <a class="btn btn-outline-light btn-sm ms-2" href="{{ with_lang(url_for('logout')) }}">{{ t('logout') }}</a>
      {% endif %}
    </div>
  </div>
</nav>

<div class="container py-3">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for cat, msg in messages %}
        <div class="alert alert-{{ 'warning' if cat=='warning' else 'info' }} alert-dismissible fade show" role="alert">
          {{ msg }}
          <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  {% block body %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

LOGIN = """
{% extends 'BASE' %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-5">
    <div class="card shadow-sm">
      <div class="card-body">
        <h4 class="mb-3">{{ t('login') }}</h4>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">{{ t('email') }}</label>
            <input class="form-control" name="identifier" placeholder="Email or name" required>
          </div>
          <div class="mb-3">
            <label class="form-label">{{ t('password') }}</label>
            <input type="password" class="form-control" name="password" required>
          </div>
          <button class="btn btn-primary w-100">{{ t('login') }}</button>
        </form>
      </div>
    </div>
  </div>
</div>
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
          <a class="btn btn-sm btn-primary mb-2" href="{{ with_lang(url_for('new_task')) }}">+ {{ t('new_task') }}</a>
          <ul class="list-group">
            {% for task in tasks %}
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>{{ task.title }}</strong>
                <div class="small text-muted">{{ t('status') }}: {{ t(task.status) }}{% if task.assigned_to %}|{{ t('assigned_to') }}: {{ task.assigned_to.name }}{% endif %}{% if task.due_date %}|{{ t('due_date') }}: {{ task.due_date.date() }}{% endif %}</div>
              </div>
              <div><a class="btn btn-sm btn-outline-secondary" href="{{ with_lang(url_for('edit_task', task_id=task.id)) }}">{{ t('edit') }}</a></div>
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
          <a class="btn btn-sm btn-primary mb-2" href="{{ with_lang(url_for('new_check')) }}">+ {{ t('new_check') }}</a>
          <ul class="list-group">
            {% for c in checks %}
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>{{ c.villa }} / {{ c.area }}</strong>
                <div class="small text-muted">{{ c.created_at.strftime('%Y-%m-%d %H:%M') }}|{{ t('status') }}: {{ t(c.status) }}</div>
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
    <a class="btn btn-primary" href="{{ with_lang(url_for('new_sop', villa=villa)) }}">+ {{ t('new_sop') }}</a>
  </div>
</div>
<div class="list-group">
  {% for s in sops %}
  <a class="list-group-item list-group-item-action" href="{{ with_lang(url_for('edit_sop', sop_id=s.id)) }}">
    <div class="d-flex w-100 justify-content-between">
      <h5 class="mb-1">{{ s.title }}</h5>
      <small class="text-muted">{{ s.category }}{% if s.villa %} | {{ s.villa }}{% endif %}</small>
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
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('category') }}</label>
    <input name="category" class="form-control" value="{{ sop.category if sop else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('villa') }}</label>
    <select name="villa" class="form-select">
      <option value="">—</option>
      {% for v in villas %}
      <option value="{{ v }}" {% if (sop and sop.villa==v) or (not sop and request.args.get('villa')==v) %}selected{% endif %}>{{ v }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">{{ t('content') }}</label>
    <textarea name="content" class="form-control" rows="8" required>{{ sop.content if sop else '' }}</textarea>
  </div>
  <button class="btn btn-primary">{{ t('save') }}</button>
</form>
{% endblock %}
"""

TASKS = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4>{{ t('tasks') }}</h4>
  <a class="btn btn-primary" href="{{ with_lang(url_for('new_task')) }}">+ {{ t('new_task') }}</a>
</div>
<ul class="list-group">
{% for task in tasks %}
  <li class="list-group-item d-flex justify-content-between align-items-center">
    <div>
      <strong>{{ task.title }}</strong>
      <div class="small text-muted">{{ t('status') }}: {{ t(task.status) }}{% if task.assigned_to %}|{{ t('assigned_to') }}: {{ task.assigned_to.name }}{% endif %}{% if task.due_date %}|{{ t('due_date') }}: {{ task.due_date.date() }}{% endif %}</div>
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
    <a class="btn btn-primary" href="{{ with_lang(url_for('new_check', villa=request.args.get('villa'))) }}">+ {{ t('new_check') }}</a>
  </div>
</div>
<ul class="list-group">
{% for c in checks %}
  <li class="list-group-item d-flex justify-content-between align-items-center">
    <div>
      <strong>{{ c.villa }} / {{ c.area }}</strong>
      <div class="small text-muted">{{ c.created_at.strftime('%Y-%m-%d %H:%M') }}|{{ t('status') }}: {{ t(c.status) }}</div>
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

USERS = """
{% extends 'BASE' %}
{% block body %}
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4>Users</h4>
  <a class="btn btn-primary" href="{{ with_lang(url_for('admin_users_new')) }}">+ New User</a>
</div>
<table class="table table-striped">
  <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Role</th></tr></thead>
  <tbody>
  {% for u in users %}
    <tr>
      <td>{{ u.id }}</td>
      <td>{{ u.name }}</td>
      <td>{{ u.email }}</td>
      <td>{{ u.role }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
"""

USER_FORM = """
{% extends 'BASE' %}
{% block body %}
<h4>New User</h4>
<form method="post">
  <div class="mb-3">
    <label class="form-label">Name</label>
    <input name="name" class="form-control" required>
  </div>
  <div class="mb-3">
    <label class="form-label">Email</label>
    <input name="email" type="email" class="form-control" required>
  </div>
  <div class="mb-3">
    <label class="form-label">Role</label>
    <select name="role" class="form-select">
      <option value="staff">staff</option>
      <option value="admin">admin</option>
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">Password</label>
    <input name="password" type="password" class="form-control" required>
  </div>
  <button class="btn btn-primary">Save</button>
</form>
{% endblock %}
"""

SELFTEST = """
{% extends 'BASE' %}
{% block body %}
<div class="row justify-content-center">
  <div class="col-lg-8">
    <div class="card shadow-sm">
      <div class="card-body">
        <h4 class="mb-3">Self Test</h4>
        <p class="text-muted">Quick smoke checks for routes, templates, and DB.</p>
        <form method="post">
          <button class="btn btn-primary">Run Tests</button>
          <a class="btn btn-outline-secondary ms-2" href="{{ with_lang(url_for('login')) }}">Go Login</a>
        </form>
        {% if results is not none %}
          <hr>
          <h6>Results</h6>
          <ul class="list-group">
            {% for r in results %}
              <li class="list-group-item d-flex justify-content-between align-items-center">
                <span>{{ r.msg }}</span>
                <span class="badge bg-{{ 'success' if r.ok else 'danger' }}">{{ 'OK' if r.ok else 'FAIL' }}</span>
              </li>
            {% endfor %}
          </ul>
        {% endif %}
      </div>
    </div>
  </div>
</div>
{% endblock %}
"""

app.jinja_env.globals.update(t=t, with_lang=with_lang)
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
    'USERS': USERS,
    'USER_FORM': USER_FORM,
    'SELFTEST': SELFTEST,
})

# ------------------------------
# Helpers
# ------------------------------
ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXT


def ensure_seed_users() -> None:
    """Create default users once."""
    if User.query.filter_by(email='admin@villa.local').first() is None:
        u = User(email='admin@villa.local', name='admin', role='admin')
        u.set_password('10051005+')
        db.session.add(u)
    if User.query.filter_by(email='stanley@villa.local').first() is None:
        u2 = User(email='stanley@villa.local', name='Stanley', role='staff')
        u2.set_password('0585')
        db.session.add(u2)
    db.session.commit()

# ------------------------------
# Login
# ------------------------------
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

# Admin‑only decorator
from functools import wraps

def admin_required(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

# ------------------------------
# Hooks & Health
# ------------------------------
@app.route('/health')
def health():
    return 'ok', 200

# Defer DB init to first request to avoid boot‑time crashes on Render
@app.before_request
def _init_db_once_and_gate():
    # lazy DB init
    if not app.config.get('_DB_INIT_DONE', False):
        try:
            db.create_all()
            ensure_seed_users()
            app.config['_DB_INIT_DONE'] = True
        except Exception as e:
            # Don't crash; /selftest will show details
            app.logger.error(f'DB init error (deferred): {e}')

    # lang cookie capture
    g.lang_to_set = None
    lang = request.args.get('lang')
    if lang:
        g.lang_to_set = lang

    # optional ACCESS_CODE gate
    access_code = os.environ.get('ACCESS_CODE')
    if access_code:
        allowed_eps = {'health', 'access', 'static', 'login', 'selftest'}
        ep = (request.endpoint or '').split('.')[-1]
        has_cookie = request.cookies.get('ac') == access_code
        from_query = request.args.get('access')
        if from_query and from_query == access_code:
            g._set_access_cookie = True
        elif not has_cookie and ep not in allowed_eps:
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for('access', next=nxt))

@app.after_request
def apply_lang_cookie(response):
    try:
        if getattr(g, 'lang_to_set', None):
            response.set_cookie('lang', g.lang_to_set, max_age=30*24*3600)
        if getattr(g, '_set_access_cookie', False):
            response.set_cookie('ac', os.environ.get('ACCESS_CODE',''), max_age=7*24*3600, httponly=True)
    except Exception:
        pass
    return response

# ------------------------------
# Routes
# ------------------------------
@app.route('/')
def index():
    return redirect(with_lang(url_for('dashboard')))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ident = (request.form.get('identifier') or '').strip()
        pw = request.form.get('password') or ''
        if '@' in ident:
            user = User.query.filter_by(email=ident).first()
        else:
            user = User.query.filter_by(name=ident).first()
        if user and user.check_password(pw):
            login_user(user)
            nxt = request.args.get('next') or url_for('dashboard')
            return redirect(with_lang(nxt))
        flash('Invalid credentials', 'warning')
    return render_template('LOGIN')

@app.route('/access', methods=['GET','POST'])
def access():
    access_code = os.environ.get('ACCESS_CODE')
    if not access_code:
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
    try:
        logout_user()
    except Exception:
        pass
    return redirect(with_lang(url_for('login')))

@app.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.order_by(Task.created_at.desc()).limit(10).all()
    checks = Check.query.order_by(Check.created_at.desc()).limit(10).all()
    return render_template('DASH', tasks=tasks, checks=checks, villas=VILLAS)

# ---- SOPS ----
@app.route('/sops')
@login_required
def list_sops():
    villa = request.args.get('villa') or None
    q = SOP.query
    if villa:
        q = q.filter_by(villa=villa)
    sops = q.order_by(SOP.created_at.desc()).all()
    return render_template('SOPS', sops=sops, villa=villa, villas=VILLAS)

@app.route('/sops/new', methods=['GET','POST'])
@login_required
def new_sop():
    if request.method == 'POST':
        s = SOP(
            title=request.form['title'],
            category=request.form['category'],
            content=request.form['content'],
            villa=request.form.get('villa') or None,
        )
        db.session.add(s)
        db.session.commit()
        return redirect(with_lang(url_for('list_sops', villa=s.villa or '')))
    return render_template('SOP_FORM', sop=None, villas=VILLAS)

@app.route('/sops/<int:sop_id>/edit', methods=['GET','POST'])
@login_required
def edit_sop(sop_id):
    sop = SOP.query.get_or_404(sop_id)
    if request.method == 'POST':
        sop.title = request.form['title']
        sop.category = request.form['category']
        sop.content = request.form['content']
        sop.villa = request.form.get('villa') or None
        db.session.commit()
        return redirect(with_lang(url_for('list_sops', villa=sop.villa or '')))
    return render_template('SOP_FORM', sop=sop, villas=VILLAS)

# ---- Tasks ----
@app.route('/tasks')
@login_required
def list_tasks():
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('TASKS', tasks=tasks)

@app.route('/tasks/new', methods=['GET','POST'])
@login_required
def new_task():
    if request.method == 'POST':
        title = request.form['title']
        status = request.form.get('status','pending')
        assigned_to_id = request.form.get('assigned_to') or None
        due_date = request.form.get('due_date') or None
        assigned_user = User.query.get(int(assigned_to_id)) if assigned_to_id else None
        task = Task(title=title, status=status, assigned_to=assigned_user, created_by=current_user)
        if due_date:
            try:
                task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
            except Exception:
                pass
        db.session.add(task)
        db.session.commit()
        return redirect(with_lang(url_for('list_tasks')))
    users = User.query.order_by(User.name.asc()).all()
    return render_template('TASK_FORM', task=None, users=users)

@app.route('/tasks/<int:task_id>/edit', methods=['GET','POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if request.method == 'POST':
        task.title = request.form['title']
        task.status = request.form.get('status','pending')
        assigned_to_id = request.form.get('assigned_to') or None
        task.assigned_to = User.query.get(int(assigned_to_id)) if assigned_to_id else None
        due_date = request.form.get('due_date') or None
        if due_date:
            try:
                task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
            except Exception:
                pass
        db.session.commit()
        return redirect(with_lang(url_for('list_tasks')))
    users = User.query.order_by(User.name.asc()).all()
    return render_template('TASK_FORM', task=task, users=users)

# ---- Checks ----
@app.route('/checks')
@login_required
def list_checks():
    villa = request.args.get('villa')
    q = Check.query
    if villa:
        q = q.filter_by(villa=villa)
    checks = q.order_by(Check.created_at.desc()).all()
    return render_template('CHECKS', checks=checks, villas=VILLAS)

@app.route('/checks/new', methods=['GET','POST'])
@login_required
def new_check():
    if request.method == 'POST':
        c = Check(
            villa=request.form['villa'],
            area=request.form['area'],
            notes=request.form.get('notes') or None,
            status=request.form.get('status','pending'),
            created_by=current_user,
        )
        file = request.files.get('photo')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = str(Path(app.config['UPLOAD_FOLDER']) / filename)
            file.save(save_path)
            c.photo_path = save_path
        db.session.add(c)
        db.session.commit()
        return redirect(with_lang(url_for('list_checks', villa=c.villa)))
    return render_template('CHECK_FORM', check=None, villas=VILLAS)

@app.route('/checks/<int:check_id>/edit', methods=['GET','POST'])
@login_required
def edit_check(check_id):
    c = Check.query.get_or_404(check_id)
    if request.method == 'POST':
        c.villa = request.form['villa']
        c.area = request.form['area']
        c.notes = request.form.get('notes') or None
        c.status = request.form.get('status','pending')
        file = request.files.get('photo')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = str(Path(app.config['UPLOAD_FOLDER']) / filename)
            file.save(save_path)
            c.photo_path = save_path
        db.session.commit()
        return redirect(with_lang(url_for('list_checks', villa=c.villa)))
    return render_template('CHECK_FORM', check=c, villas=VILLAS)

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---- Admin Users ----
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.id.asc()).all()
    return render_template('USERS', users=users)

@app.route('/admin/users/new', methods=['GET','POST'])
@login_required
@admin_required
def admin_users_new():
    if request.method == 'POST':
        u = User(name=request.form['name'], email=request.form['email'], role=request.form.get('role','staff'))
        u.set_password(request.form['password'])
        db.session.add(u)
        db.session.commit()
        return redirect(with_lang(url_for('admin_users')))
    return render_template('USER_FORM')

# ---- Debug helper: show DB URI (admin only) ----
@app.route('/admin/dburi')
@login_required
@admin_required
def show_dburi():
    return app.config['SQLALCHEMY_DATABASE_URI']

# ---- Self Test ----
@dataclass
class R:
    ok: bool
    msg: str

@app.route('/selftest', methods=['GET','POST'])
def selftest():
    results: List[R] = [] if request.method == 'POST' else None
    if request.method == 'POST':
        try:
            results.append(R(True, 'App loaded'))
            # DB URL normalized
            uri = app.config['SQLALCHEMY_DATABASE_URI']
            results.append(R(uri.startswith('sqlite') or bool(uri), f'DB URI = {uri}'))

            # DB path existence (sqlite only)
            if uri.startswith('sqlite:////'):
                p = uri.replace('sqlite:////','/',1)
                results.append(R(Path(p).parent.exists(), f'DB dir exists: {Path(p).parent}'))
                results.append(R(Path(p).exists(), f'DB file exists: {p}'))

            # Try connect
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text('SELECT 1'))
                results.append(R(True, 'DB connect ok'))
            except Exception as e:
                results.append(R(False, f'DB connect failed: {e}'))

            # create_all
            try:
                db.create_all()
                results.append(R(True, 'create_all ok'))
            except Exception as e:
                results.append(R(False, f'create_all failed: {e}'))

            # seed users
            try:
                ensure_seed_users()
                results.append(R(True, 'seed users ok'))
            except Exception as e:
                results.append(R(False, f'seed users failed: {e}'))

            # templates render
            try:
                render_template('LOGIN')
                results.append(R(True, 'templates loaded'))
            except Exception as e:
                results.append(R(False, f'templates failed: {e}'))

        except Exception as e:
            results.append(R(False, f'Fatal: {e}'))
    return render_template('SELFTEST', results=results)

# ------------------------------
# Entrypoint
# ------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    app.run(host='0.0.0.0', port=port, debug=True)
