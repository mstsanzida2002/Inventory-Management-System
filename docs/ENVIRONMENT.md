# 🌍 Environment Variables
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when setting up `.env`, configuring settings files,
> or deploying. Never hardcode any value listed here.

---

## `.env.example` — Copy to `.env` and fill in values

```env
# ─────────────────────────────────────
# Django Core
# ─────────────────────────────────────
SECRET_KEY=replace-with-50-char-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SETTINGS_MODULE=config.settings.development

# ─────────────────────────────────────
# Database (PostgreSQL)
# ─────────────────────────────────────
DB_NAME=inventory_db
DB_USER=inventory_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# ─────────────────────────────────────
# Redis & Celery
# ─────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# ─────────────────────────────────────
# Email (SMTP)
# ─────────────────────────────────────
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password
DEFAULT_FROM_EMAIL=AI Inventory System <noreply@yourdomain.com>

# ─────────────────────────────────────
# Security & Session
# ─────────────────────────────────────
SESSION_COOKIE_AGE=3600
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION=300

# ─────────────────────────────────────
# AI Configuration
# ─────────────────────────────────────
FORECAST_RETRAIN_INTERVAL_DAYS=7
DEFAULT_FORECAST_PERIODS=12
SLOW_MOVING_THRESHOLD_DAYS=60
DEAD_STOCK_THRESHOLD_DAYS=180
```

---

## Generating a SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## Gmail App Password Setup

1. Enable 2-Factor Authentication on your Gmail account
2. Go to Google Account → Security → App Passwords
3. Generate a new App Password for "Mail"
4. Use that 16-character password as `EMAIL_HOST_PASSWORD`

---

## Deliverability Notes (Phase 8.99f-7)

Proven working, locally, over real Gmail SMTP (Phase 8.99f/f-5): the one
thing that actually matters on plain Gmail SMTP is that
`DEFAULT_FROM_EMAIL` matches `EMAIL_HOST_USER` exactly — Gmail
rejects/rewrites a `From` address that doesn't match the authenticated
account. There is no SPF/DKIM/domain-authentication concern to configure
here, because the sending domain (`gmail.com`) is Google's own — that
only becomes relevant once sending as a custom domain address (Phase D).

**Flagged for Phase D, not built now:**
- **SPF/DKIM/DMARC** become the deployment's own concern the moment
  `DEFAULT_FROM_EMAIL` moves off `@gmail.com` onto a custom domain
  (e.g. `noreply@stockwell.example`) — typically handled by whichever
  transactional email provider is used at that point (DNS records they
  generate for you), not hand-rolled.
- **A transactional email provider (SendGrid, Mailgun, Amazon SES, etc.)
  is the recommended production choice over personal Gmail SMTP.** Gmail
  has low daily send limits (roughly 500/day on a free account) and an
  App Password is a personal-account credential, not a production service
  auth story — fine, and already proven, for local dev/demo use; not
  where a real deployment's outbound mail should live. Swapping providers
  is a `.env`-only change (`EMAIL_HOST`/`PORT`/`HOST_USER`/`HOST_PASSWORD`
  point at the new provider's SMTP relay; `EMAIL_BACKEND` stays Django's
  own SMTP backend) — no code change, matching how console vs. Gmail SMTP
  already differ only by environment.

---

## How Variables Are Loaded

`python-decouple` reads from `.env` automatically:

```python
from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG       = config('DEBUG', default=False, cast=bool)
DB_PORT     = config('DB_PORT', default='5432')
```

---

## `.gitignore` — Must Include

```gitignore
# Environment
.env
.env.local

# Python
__pycache__/
*.pyc
*.pyo
venv/
env/

# Django
staticfiles/
media/
*.log

# AI Models
ai_models/

# IDE
.vscode/
.idea/

# Coverage
htmlcov/
.coverage
```
