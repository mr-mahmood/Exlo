from django.db import migrations, models
from django.db.models import Count, OuterRef, Subquery
import django.db.models.deletion


def backfill_gym_and_check_duplicates(apps, schema_editor):
    Subscription = apps.get_model("gym_subscriptions", "GymSubscription")
    Plan = apps.get_model("gym_plans", "GymMembershipPlan")
    Subscription.objects.update(
        gym_id=Subquery(Plan.objects.filter(pk=OuterRef("plan_id")).values("gym_id")[:1])
    )
    duplicate = (
        Subscription.objects.filter(status__in=["ACTIVE", "PENDING"])
        .values("subscriber_id", "gym_id", "status")
        .annotate(count=Count("pk"))
        .filter(count__gt=1)
        .order_by("subscriber_id")
        .first()
    )
    if duplicate:
        raise RuntimeError(
            "Cannot enforce per-gym subscription uniqueness: duplicate "
            f"{duplicate['status']} subscriptions for subscriber "
            f"{duplicate['subscriber_id']} and gym {duplicate['gym_id']}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("gym_subscriptions", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="gymsubscription",
            name="gym",
            field=models.ForeignKey(
                to="gym.gym",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_gym_and_check_duplicates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="gymsubscription",
            name="gym",
            field=models.ForeignKey(
                to="gym.gym",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                editable=False,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="gymsubscription",
            name="unique_active_subscription_per_user",
        ),
        migrations.AddConstraint(
            model_name="gymsubscription",
            constraint=models.UniqueConstraint(
                fields=("subscriber", "gym"),
                condition=models.Q(status="ACTIVE"),
                name="unique_active_subscription_per_user_gym",
            ),
        ),
        migrations.AddConstraint(
            model_name="gymsubscription",
            constraint=models.UniqueConstraint(
                fields=("subscriber", "gym"),
                condition=models.Q(status="PENDING"),
                name="unique_pending_subscription_per_user_gym",
            ),
        ),
    ]
