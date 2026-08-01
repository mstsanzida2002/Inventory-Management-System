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
