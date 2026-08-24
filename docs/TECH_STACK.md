# ⚙️ Tech Stack & Dependencies
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when setting up the project for the first time,
> installing packages, or resolving dependency issues.
>
> **Corrected against the actual codebase (docs/bugsfound.md BUG-69):**
> the Frontend CSS row below no longer claims Bootstrap — the real
> frontend is a 100% custom vanilla-CSS design system, no framework
> dependency at all (see "Frontend Design System" below). The Task
> Queue/Message Broker rows describe reference material only: **no
> Celery, no Redis, no scheduler of any kind actually runs in this
> project** — `requirements.txt` has no `celery`/`redis` dependency, and
> every AI/notification task that this stack section shows as a
> background job runs synchronously instead, triggered by a real event
> (a sale approval, a manual "Run now" button) — see
> `docs/DEAD_STOCK_DETECTION.md` and `docs/DEMAND_FORECASTING.md` for the
> details, and `docs/bugsfound.md` for the full history of this
> correction (REQ 9.7 and REQ 17.4, periodic retraining, are consequently
> PHANTOM).

---

## Core Stack

| Layer | Technology | Version (min) | Purpose |
|---|---|---|---|
| Backend Framework | Django | 5.x | Web framework, ORM, admin, sessions |
| REST API | Django REST Framework | 3.15+ | API views, serializers, authentication |
| Database | PostgreSQL | 15+ | Primary data store |
| Task Queue | ~~Celery~~ | — | **Not installed.** Reference material only — see header note |
| Message Broker | ~~Redis~~ | — | **Not installed.** Reference material only — see header note |
| AI / ML | Scikit-learn | 1.4+ | Demand forecasting models |
| Data Processing | Pandas | 2.x | Sales data aggregation for AI |
| Numerical | NumPy | 1.26+ | Array operations for forecasting |
| Password Hashing | django[argon2] | — | Argon2 via django.contrib.auth |
| Static Files | WhiteNoise | 6.x | Serve static files in production |
| WSGI Server | Gunicorn | 22+ | Production app server |
| Frontend CSS | Custom vanilla CSS | — | Hand-built design system — `tokens.css`/`components.css`/`dashboard.css`/`landing.css`, no framework dependency |
| Charts | Chart.js | 4.x | Interactive dashboard charts |
| PDF Export | ReportLab or WeasyPrint | latest | Report PDF generation |
| CSV Export | Python built-in `csv` | — | Report CSV generation |

---

## Frontend Design System (corrected — not Bootstrap)

The frontend is 100% hand-built vanilla CSS, not a framework. Design
tokens (`frontend/static/css/tokens.css`: colors, type scale, spacing,
radius/shadow/motion), components (`components.css`: buttons, cards,
badges, form fields, modals), and shell layout (`dashboard.css`: sidebar,
topbar, KPI cards, panels) — no Bootstrap, no build step, no CDN CSS
framework of any kind. `docs/frontend_work.md` has the full component
inventory. This is a stronger engineering claim than the framework this
file used to document, not a weaker one — a hand-built design system
demonstrates CSS architecture the way pulling in Bootstrap would not.

---

## requirements.txt

```txt
# Core
Django>=5.0
djangorestframework>=3.15
django-cors-headers>=4.3

# Database
psycopg2-binary>=2.9

# Cache & Task Queue
redis>=5.0
celery>=5.3
django-celery-beat>=2.6
django-celery-results>=2.5

# Authentication
django[argon2]

# AI & Data
scikit-learn>=1.4
pandas>=2.1
numpy>=1.26
joblib>=1.3

# Static Files
whitenoise>=6.6

# WSGI
gunicorn>=22.0

# PDF Generation
weasyprint>=61.0
# OR: reportlab>=4.0

# Environment
python-decouple>=3.8

# Dev & Testing
coverage>=7.4
factory-boy>=3.3
faker>=24.0
```

---

## Installation

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify Redis is running
redis-cli ping                  # Should return PONG

# 4. Verify PostgreSQL is running
pg_isready
```

---

## Django Settings Split Pattern

Use a split settings pattern for clean environment separation:

```
config/
├── settings/
│   ├── __init__.py     # imports from base
│   ├── base.py         # shared settings
│   ├── development.py  # DEBUG=True, console email backend
│   └── production.py   # DEBUG=False, WhiteNoise, secure cookies
```

**`config/settings/base.py` — Critical settings to include:**

```python
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'corsheaders',
    'django_celery_beat',
    'django_celery_results',
    # Local apps
    'apps.authentication',
    'apps.users',
    'apps.rbac',
    'apps.products',
    'apps.suppliers',
    'apps.purchases',
    'apps.sales',
    'apps.inventory',
    'apps.adjustments',
    'apps.ai.forecasting',
    'apps.ai.classification',
    'apps.dashboard',
    'apps.reports',
    'apps.notifications',
    'apps.audit',
    'apps.settings_manager',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',    # Must be second
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Custom user model
AUTH_USER_MODEL = 'users.User'

# Password hashing — Argon2 first
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# Redis & Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
    }
}

# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND')
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# Session
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', default=3600, cast=int)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True        # Production only (set False in dev)
SESSION_COOKIE_SAMESITE = 'Lax'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

---

## Celery App Initialization

**`config/celery.py`:**

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('inventory')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

**`config/__init__.py`:**

```python
from .celery import app as celery_app
__all__ = ('celery_app',)
```

---

## Frontend Assets (CDN — no build step required)

Add to `templates/base.html`:

```html
<!-- Chart.js 4 -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

No Bootstrap, no Bootstrap Icons CDN link — the design system and its
own inline SVG icon set (`frontend/templates/includes/icons.html`) are
both hand-built; see "Frontend Design System" above.
