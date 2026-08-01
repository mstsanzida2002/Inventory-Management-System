"""
docs/SECURITY.md's `StrongPasswordValidator`, translated into the single
`frontend` app — no `apps/authentication/` app created (see
docs/project_memory.md §13). Registered in `AUTH_PASSWORD_VALIDATORS`
(config/settings.py) as `frontend.validators.StrongPasswordValidator`,
stacked on top of Django's own built-in validators (which already provide
the 8-char minimum).
"""
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
