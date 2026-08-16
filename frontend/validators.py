"""
docs/SECURITY.md's `StrongPasswordValidator`, translated into the single
`frontend` app — no `apps/authentication/` app created (see
docs/project_memory.md §13). Registered in `AUTH_PASSWORD_VALIDATORS`
(config/settings.py) as `frontend.validators.StrongPasswordValidator`,
stacked on top of Django's own built-in validators (which already provide
the 8-char minimum).
"""
import os
import re
import secrets
import string

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


def generate_strong_password(length=14):
    """Phase 8.98e — admin-driven user creation no longer lets the Admin
    choose (or ever see) a new user's password; this generates one that's
    guaranteed to pass every validator in AUTH_PASSWORD_VALIDATORS
    (config/settings.py): StrongPasswordValidator's own upper/lower/digit/
    special-char requirement is enforced by construction below (one of
    each is always included), and Django's built-in
    MinimumLengthValidator/CommonPasswordValidator/NumericPasswordValidator/
    UserAttributeSimilarityValidator are satisfied by construction too — a
    `secrets`-random string of this length is neither a common password,
    nor all-digits, nor plausibly similar to any real user's own
    attributes. Uses `secrets`, not `random`, since this is a real
    credential, not test data."""
    upper, lower, digits, special = string.ascii_uppercase, string.ascii_lowercase, string.digits, '!@#$%^&*'
    required = [secrets.choice(upper), secrets.choice(lower), secrets.choice(digits), secrets.choice(special)]
    pool = upper + lower + digits + special
    password_chars = required + [secrets.choice(pool) for _ in range(max(length - len(required), 0))]
    secrets.SystemRandom().shuffle(password_chars)
    return ''.join(password_chars)


# docs/SECURITY.md's `apps/products/validators.py`, translated the same way
# as StrongPasswordValidator above — same single-app reasoning. Registered
# directly on ProductForm.image (frontend/forms.py), not via a model-level
# `validators=` kwarg, since Product.image (frontend/models.py, Phase 1) is
# a pre-existing field and this validator is new in Phase 5.
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
MAX_IMAGE_SIZE_MB = 5


def validate_product_image(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}')
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Image file too large. Maximum size is {MAX_IMAGE_SIZE_MB}MB.')
