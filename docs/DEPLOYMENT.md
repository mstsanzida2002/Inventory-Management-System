# 🚀 Deployment Guide
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when deploying to Render or configuring
> production settings, Procfile, Celery workers, or static file serving.

---

## Platform: Render

### Services to Create

| Service Type | Name | Purpose |
|---|---|---|
| Web Service | `inventory-web` | Django + Gunicorn |
| Background Worker | `inventory-celery-worker` | Celery worker |
| Background Worker | `inventory-celery-beat` | Celery beat (scheduled tasks) |
| PostgreSQL | `inventory-db` | Primary database |
| Redis | `inventory-redis` | Broker + cache |

---

## Procfile

```
web: gunicorn config.wsgi:application --workers 2 --timeout 120
worker: celery -A config worker --loglevel=info --concurrency=2
beat: celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Build Command (Render → Build Command)

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

---

## Start Command (Render → Start Command)

```bash
gunicorn config.wsgi:application
```

---

## Environment Variables to Set in Render Dashboard

```env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=False
ALLOWED_HOSTS=your-app-name.onrender.com

DB_NAME=<from Render PostgreSQL>
DB_USER=<from Render PostgreSQL>
DB_PASSWORD=<from Render PostgreSQL>
DB_HOST=<from Render PostgreSQL>
DB_PORT=5432

REDIS_URL=<from Render Redis>
CELERY_BROKER_URL=<same as REDIS_URL>
CELERY_RESULT_BACKEND=<same as REDIS_URL>

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your@email.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=AI Inventory <noreply@yourdomain.com>

SESSION_COOKIE_AGE=3600
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION=300
```

---

## `config/settings/production.py`

```python
from .base import *
from decouple import config

DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Security
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# Static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
```

---

## `config/settings/development.py`

```python
from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Use console email backend (no SMTP needed)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable secure cookies for local HTTP
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Debug toolbar (optional)
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1']
```

---

## Static Files with WhiteNoise

WhiteNoise serves compressed static files in production without a CDN.

**Required in `base.py`:**
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # Must be second
    ...
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

---

## AI Models Directory

The trained Scikit-learn models are stored in `ai_models/` at the project root.

**Important:** On Render's free tier, the filesystem is ephemeral. Solutions:
1. Store models in PostgreSQL as binary blobs (serialize with `joblib.dumps()`)
2. Re-train on worker startup if model file not found (handled in pipeline)
3. Use Render's persistent disk (paid feature)

The pipeline already handles missing model files gracefully:
```python
def load_model(period='W'):
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    if not os.path.exists(model_path):
        # Auto-train if missing
        model, _ = train_model(period)
        return model
    return joblib.load(model_path)
```

---

## First Deployment Checklist

```
[ ] 1. Set all environment variables in Render dashboard
[ ] 2. Verify PostgreSQL and Redis services are running
[ ] 3. Deploy web service — migrations run automatically in build command
[ ] 4. Create superuser via Render shell:
        python manage.py createsuperuser
[ ] 5. Load initial system settings fixture:
        python manage.py loaddata fixtures/initial_settings.json
[ ] 6. Deploy celery worker service
[ ] 7. Deploy celery beat service
[ ] 8. Verify Celery beat creates beat schedules:
        Django Admin → Periodic Tasks
[ ] 9. Trigger manual AI classification run to initialize classifications
[ ] 10. Test login → confirm role-based redirect works
```

---

## Database Backup Strategy

Render PostgreSQL includes automatic daily backups on paid plans.

For manual backup:
```bash
# Export
pg_dump -U DB_USER -h DB_HOST DB_NAME > backup_$(date +%Y%m%d).sql

# Restore
psql -U DB_USER -h DB_HOST DB_NAME < backup_20240115.sql
```
