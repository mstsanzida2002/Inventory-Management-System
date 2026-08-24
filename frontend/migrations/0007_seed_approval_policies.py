"""
Phase 12 — seeds the starting ApprovalPolicy ruleset (§9). Not a
migration-from-an-existing-value: discovery found no pre-existing
purchase-order approval ceiling anywhere in this codebase (no
SystemSettings field, no service-layer check) to convert byte-
identically — see docs/project_memory.md §13 for the full disclosure.
The ৳50,000 purchase-order supervisor/admin split below is a fresh
value, confirmed with the user rather than invented.

One adaptation from §9's own table: ApprovalPolicy.reason_code is a
single value, not a list, and (transaction_type, priority) must be
unique among active rows — so the original "damage / expiry, value <=
5,000 -> Supervisor" row (a single row matching two reason codes) is
split into two rows here (priority 30 for damage, 31 for expiry), both
resolving to the same outcome. Every "above X" row (70/90) is left with
no max_value/min_value condition at all rather than an explicit
lower bound: priority ordering alone already guarantees it's only ever
reached once the lower-priority row above it (60/80) has failed to
match, so an explicit ">X" condition would be redundant, not load-bearing.
"""
from decimal import Decimal

from django.db import migrations


POLICIES = [
    # -- Inventory Adjustment ------------------------------------------------
    {
        "name": "Unexplained shrinkage — any value", "transaction_type": "adjustment",
        "reason_code": "shrinkage_unknown", "required_level": "admin", "priority": 10,
        "notes": "The single most common fraud vector this phase exists to close: "
                 "shrinkage laundered through a self-approved adjustment.",
    },
    {
        "name": "Class-A product, high variance", "transaction_type": "adjustment",
        "abc_class": "A", "max_variance_pct": Decimal("1.00"), "required_level": "admin", "priority": 20,
        "notes": "Matches when variance exceeds 1% for a top-revenue product.",
    },
    {
        "name": "Damage adjustment up to ৳5,000", "transaction_type": "adjustment",
        "reason_code": "damage", "max_value": Decimal("5000.00"), "required_level": "supervisor", "priority": 30,
    },
    {
        "name": "Expiry adjustment up to ৳5,000", "transaction_type": "adjustment",
        "reason_code": "expiry", "max_value": Decimal("5000.00"), "required_level": "supervisor", "priority": 31,
    },
    {
        "name": "Small, low-variance adjustment", "transaction_type": "adjustment",
        "max_value": Decimal("500.00"), "max_variance_pct": Decimal("2.00"), "required_level": "auto", "priority": 40,
        "notes": "The lever that makes this a policy engine, not just a permission "
                 "wall: routine, low-value, low-variance adjustments post immediately, no human approval.",
    },
    {
        "name": "All other adjustments", "transaction_type": "adjustment",
        "required_level": "supervisor", "priority": 50,
        "notes": "Catch-all — anything not matched by a more specific rule above.",
    },
    # -- Purchase Order --------------------------------------------------------
    {
        "name": "Purchase order up to ৳50,000", "transaction_type": "purchase_order",
        "max_value": Decimal("50000.00"), "required_level": "supervisor", "priority": 60,
    },
    {
        "name": "Purchase order above ৳50,000", "transaction_type": "purchase_order",
        "required_level": "admin", "priority": 70,
    },
    # -- Sale Cancellation -------------------------------------------------------
    {
        "name": "Sale cancellation up to ৳10,000", "transaction_type": "sale_cancel",
        "max_value": Decimal("10000.00"), "required_level": "supervisor", "priority": 80,
    },
    {
        "name": "Sale cancellation above ৳10,000", "transaction_type": "sale_cancel",
        "required_level": "admin", "priority": 90,
    },
]


def seed_policies(apps, schema_editor):
    ApprovalPolicy = apps.get_model("frontend", "ApprovalPolicy")
    for entry in POLICIES:
        ApprovalPolicy.objects.get_or_create(
            transaction_type=entry["transaction_type"], priority=entry["priority"],
            defaults={
                "name": entry["name"],
                "reason_code": entry.get("reason_code", ""),
                "abc_class": entry.get("abc_class", ""),
                "min_value": entry.get("min_value", Decimal("0")),
                "max_value": entry.get("max_value"),
                "max_variance_pct": entry.get("max_variance_pct"),
                "required_level": entry["required_level"],
                "block_self_approval": entry.get("block_self_approval", True),
                "is_active": True,
                "notes": entry.get("notes", ""),
            },
        )


def unseed_policies(apps, schema_editor):
    ApprovalPolicy = apps.get_model("frontend", "ApprovalPolicy")
    for entry in POLICIES:
        ApprovalPolicy.objects.filter(
            transaction_type=entry["transaction_type"], priority=entry["priority"], name=entry["name"],
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0006_inventoryadjustment_reason_code_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_policies, unseed_policies),
    ]
