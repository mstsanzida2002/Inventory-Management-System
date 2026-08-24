# Phase 12.2 — ABC removed as an approval-routing input entirely. This
# data migration deletes the seeded "Class-A product, high variance" row
# (priority 20, adjustment type) BEFORE the schema change in the next
# migration removes ApprovalPolicy.abc_class — split into two migrations
# (not one, as originally written) because Postgres refuses an ALTER
# TABLE on a table with pending trigger events from a DELETE earlier in
# the same transaction ("cannot ALTER TABLE ... because it has pending
# trigger events"), found by actually running this migration, not
# assumed safe to combine.
#
# Left behind as a schema-only RemoveField, this row's required_level=
# ADMIN would have started matching every adjustment unconditionally
# once abc_class stopped being a real filter — silently widening what
# escalates to Admin, not a harmless no-op.

from django.db import migrations


def delete_abc_policy_row(apps, schema_editor):
    ApprovalPolicy = apps.get_model("frontend", "ApprovalPolicy")
    ApprovalPolicy.objects.filter(transaction_type="adjustment", priority=20).delete()


def noop_reverse(apps, schema_editor):
    # Not worth reseeding the deleted row on reverse — abc_class itself
    # would already be gone by the time this migration is unapplied in
    # that direction (0011's own reverse, AddField, restores the column
    # first since Django unapplies migrations in reverse dependency order).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0009_cumulative_cap_and_backfill'),
    ]

    operations = [
        migrations.RunPython(delete_abc_policy_row, noop_reverse),
    ]
