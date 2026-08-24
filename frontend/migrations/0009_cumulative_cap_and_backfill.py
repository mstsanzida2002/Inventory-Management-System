"""
Phase 12.1 §4 — updates the existing priority=40/adjustment AUTO policy
row (seeded by 0007) with the new cumulative window/cap, and backfills
InventoryAdjustment.was_auto_posted/resolved_policy (added in 0008) for
any adjustments already AUTO-posted before this migration ran, from the
one place that fact was previously recorded: AuditLog entries with
action='ADJUSTMENT_AUTO_POSTED'. Best-effort — a details blob missing
'policy_id' (shouldn't happen, AdjustmentService.create() always wrote
one, but not assumed) is left with was_auto_posted=True and
resolved_policy=None rather than raising.
"""
from django.db import migrations


def update_and_backfill(apps, schema_editor):
    ApprovalPolicy = apps.get_model("frontend", "ApprovalPolicy")
    InventoryAdjustment = apps.get_model("frontend", "InventoryAdjustment")
    AuditLog = apps.get_model("frontend", "AuditLog")

    ApprovalPolicy.objects.filter(transaction_type="adjustment", priority=40).update(
        cumulative_window_days=30, cumulative_value_cap="2000.00",
    )

    for entry in AuditLog.objects.filter(action="ADJUSTMENT_AUTO_POSTED"):
        if not entry.affected_id:
            continue
        policy_id = (entry.details or {}).get("policy_id")
        InventoryAdjustment.objects.filter(pk=entry.affected_id).update(
            was_auto_posted=True,
            resolved_policy_id=policy_id if ApprovalPolicy.objects.filter(pk=policy_id).exists() else None,
        )


def noop_reverse(apps, schema_editor):
    # Not worth reconstructing "which rows were backfilled" on reverse —
    # was_auto_posted/resolved_policy are additive metadata, not
    # something a rollback needs to strip for correctness.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0008_approvalpolicy_cumulative_value_cap_and_more'),
    ]

    operations = [
        migrations.RunPython(update_and_backfill, noop_reverse),
    ]
