# 🔐 Security Implementation
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when implementing any authentication, form handling,
> API endpoint, or session-related code. Every item here is a hard requirement.

---

## Requirements Coverage
`REQ 15.1 → 15.15`

---

## Security Checklist

| # | Control | Implementation |
|---|---|---|
| 1 | Password hashing | Argon2 via `PASSWORD_HASHERS` in settings |
| 2 | HTTPS enforcement | `SECURE_SSL_REDIRECT = True` in production |
| 3 | CSRF protection | Django `CsrfViewMiddleware` + `{% csrf_token %}` in all forms |
| 4 | XSS prevention | Django auto-escaping in templates; `mark_safe` banned |
| 5 | SQL Injection | Django ORM only; raw SQL banned; user input never interpolated |
| 6 | Session security | `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SECURE = True` |
| 7 | Account lockout | After 5 failed logins, locked for 300s |
| 8 | RBAC enforcement | Every view and API endpoint checks role |
| 9 | Secrets management | All secrets in `.env` via `python-decouple` |
| 10 | Inactive session | Auto-expire via `SESSION_COOKIE_AGE` |
| 11 | Password reset | Email verification only — no security questions |
| 12 | Audit logging | Every auth and sensitive operation logged |
| 13 | URL access control | `@login_required` and `permission_classes` everywhere |
| 14 | Immutable records | `AuditLog.save()` raises on update; `InventoryMovement` never modified |
| 15 | Input validation | DRF serializers + Django forms validate all user input |

---

## Production Security Settings

```python
# config/settings/production.py
from .base import *

DEBUG = False

# HTTPS
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Session cookies
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF cookie
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Clickjacking
X_FRAME_OPTIONS = 'DENY'

# Content type sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True

# XSS filter header
SECURE_BROWSER_XSS_FILTER = True
```

---

## Password Policy Enforcement

```python
# config/settings/base.py
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    # Custom: require uppercase, lowercase, special char
    {
        'NAME': 'apps.authentication.validators.StrongPasswordValidator',
    },
]
```

```python
# apps/authentication/validators.py
import re
from django.core.exceptions import ValidationError

class StrongPasswordValidator:
    def validate(self, password, user=None):
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            errors.append('Password must contain at least one lowercase letter.')
        if not re.search(r'\d', password):
            errors.append('Password must contain at least one digit.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append('Password must contain at least one special character.')
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return 'Password must be 8+ chars with uppercase, lowercase, digit, and special character.'
```

---

## CSRF in Templates

Always include in every form:

```html
<form method="post">
  {% csrf_token %}
  ...
</form>
```

For AJAX requests:

```javascript
// Get CSRF token from cookie
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Use in AJAX
fetch('/api/v1/some-endpoint/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken'),
  },
  body: JSON.stringify(data),
});
```

---

## Input Sanitization Rules

- **Never** use `mark_safe()` on user-provided content
- **Never** use raw SQL with string interpolation (use `params=` with ORM)
- **Always** validate file uploads (type, size, extension)
- **Always** use DRF serializers for API input validation
- Reject file uploads that are not allowed image types for product/profile images

```python
# apps/products/validators.py
from django.core.exceptions import ValidationError
import os

ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
MAX_IMAGE_SIZE_MB = 5

def validate_product_image(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}')
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Image file too large. Maximum size is {MAX_IMAGE_SIZE_MB}MB.')
```

---

## Secrets Management

Use `python-decouple`. Never hardcode secrets.

```python
# config/settings/base.py
from decouple import config

SECRET_KEY  = config('SECRET_KEY')
DB_PASSWORD = config('DB_PASSWORD')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
```

`.env` is **gitignored**. `.env.example` is committed with placeholder values.

---

## Banned Patterns

```python
# ❌ NEVER DO THESE:

# Raw SQL with string formatting
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# Trusting user input without validation
Product.objects.filter(name=request.GET['name'])  # safe in ORM, but always validate first

# mark_safe on user content
from django.utils.safestring import mark_safe
return mark_safe(user_input)  # XSS vulnerability

# Secrets in code
SECRET_KEY = 'hardcoded-secret'

# Disabling CSRF on sensitive views
@csrf_exempt
def approve_purchase(request): ...
```
