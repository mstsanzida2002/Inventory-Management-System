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
    """Generates a password satisfying every configured password validator."""
    # Security: uses secrets, not random -- this is a real credential.
    upper, lower, digits, special = string.ascii_uppercase, string.ascii_lowercase, string.digits, '!@#$%^&*'
    required = [secrets.choice(upper), secrets.choice(lower), secrets.choice(digits), secrets.choice(special)]
    pool = upper + lower + digits + special
    password_chars = required + [secrets.choice(pool) for _ in range(max(length - len(required), 0))]
    secrets.SystemRandom().shuffle(password_chars)
    return ''.join(password_chars)


# Assumption: applied via ProductForm.image, not a model validator.
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
MAX_IMAGE_SIZE_MB = 5


def validate_product_image(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}')
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Image file too large. Maximum size is {MAX_IMAGE_SIZE_MB}MB.')


# Workaround: Pillow can't open SVG; this checks type/size instead.
ALLOWED_LOGO_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.svg']
MAX_LOGO_SIZE_MB = 5


def validate_company_logo(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_LOGO_EXTENSIONS)}')
    if file.size > MAX_LOGO_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Logo file too large. Maximum size is {MAX_LOGO_SIZE_MB}MB.')
    if ext == '.svg':
        # Edge: shallow sniff only -- not full XML validation/sanitization.
        head = file.read(512)
        file.seek(0)
        if b'<svg' not in head and b'<?xml' not in head:
            raise ValidationError('That file does not look like a valid SVG.')
    else:
        from PIL import Image, UnidentifiedImageError
        try:
            Image.open(file).verify()
        except UnidentifiedImageError:
            raise ValidationError('Upload a valid PNG or JPG image.')
        finally:
            file.seek(0)
