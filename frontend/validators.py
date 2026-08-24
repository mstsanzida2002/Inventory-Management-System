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


# Phase 13 — the company logo needs SVG support (a document header logo
# is very commonly vector), which `validate_product_image` deliberately
# doesn't offer: Django's ImageField opens every upload with Pillow to
# verify it's a real image, and Pillow cannot open SVG at all — a raster
# ImageField hard-rejects every SVG before this validator would even
# run. SystemSettings.company_logo is a plain FileField instead (see
# models.py), with this validator doing the type/size checking Django's
# ImageField would otherwise have done for free. Not reused for
# Product.image: products don't need vector logos, and widening that
# field's accepted types wasn't asked for.
ALLOWED_LOGO_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.svg']
MAX_LOGO_SIZE_MB = 5


def validate_company_logo(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_LOGO_EXTENSIONS)}')
    if file.size > MAX_LOGO_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Logo file too large. Maximum size is {MAX_LOGO_SIZE_MB}MB.')
    if ext == '.svg':
        # No Pillow check available for SVG, so at least confirm the
        # upload is really an SVG and not an arbitrary file renamed
        # with a .svg extension — a cheap sniff, not full XML
        # validation/sanitization.
        head = file.read(512)
        file.seek(0)
        if b'<svg' not in head and b'<?xml' not in head:
            raise ValidationError('That file does not look like a valid SVG.')
    else:
        # PNG/JPG still go through Pillow, same guarantee ImageField
        # itself would have provided.
        from PIL import Image, UnidentifiedImageError
        try:
            Image.open(file).verify()
        except UnidentifiedImageError:
            raise ValidationError('Upload a valid PNG or JPG image.')
        finally:
            file.seek(0)
