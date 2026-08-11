"""
Dev-environment convenience command — recreates the three standing manual-
verification accounts (one per UserRole) so they survive this project's
recurring db.sqlite3/PostgreSQL resets (Phase 3.7, Phase 3.8, and however
many more happen after this). Not part of any documented module; this is
local test-data setup only, same spirit as Django's own `createsuperuser`.

Required fields read directly off frontend.models.User (username, email,
employee_id, full_name — none of the four have blank=True or a usable
default; role/password are supplied explicitly per account below rather
than left at the model's own default=STAFF/unusable-password).

Refuses to run when DEBUG is False: these are known, published passwords
by design (so a human can log in and click around), which must never be
creatable against a real deployment's database.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from frontend.models import User, UserRole

ACCOUNTS = [
    {
        "username": "verify_admin",
        "password": "Stockwell-Admin1!",
        "full_name": "Naomi Whitfield",
        "email": "naomi.whitfield@stockwell.example",
        "employee_id": "EMP-1001",
        "role": UserRole.ADMIN,
    },
    {
        "username": "verify_super",
        "password": "Stockwell-Super1!",
        "full_name": "Marcus Bellweather",
        "email": "marcus.bellweather@stockwell.example",
        "employee_id": "EMP-1002",
        "role": UserRole.SUPERVISOR,
    },
    {
        "username": "verify_user",
        "password": "Stockwell-Staff1!",
        "full_name": "Talia Nakamura",
        "email": "talia.nakamura@stockwell.example",
        "employee_id": "EMP-1003",
        "role": UserRole.STAFF,
    },
]


class Command(BaseCommand):
    help = "Create/reset the 3 standing manual-verification accounts (one per role). DEBUG-only."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_test_users refuses to run with DEBUG=False — these are "
                "known passwords and must never exist on a real deployment."
            )

        self.stdout.write("Username/password pairs:\n")

        for account in ACCOUNTS:
            user, created = User.objects.update_or_create(
                username=account["username"],
                defaults={
                    "email": account["email"],
                    "employee_id": account["employee_id"],
                    "full_name": account["full_name"],
                    "role": account["role"],
                    "is_active": True,
                    "failed_login_attempts": 0,
                    "locked_until": None,
                },
            )
            user.set_password(account["password"])
            user.save()

            status = "created" if created else "updated"
            self.stdout.write(
                f"  {account['username']:<15} {account['password']:<20} "
                f"({account['role']}, {status})"
            )

        self.stdout.write(self.style.SUCCESS("\nDone — safe to re-run any time (idempotent)."))
