from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0004_deposit_deposits_wallet__127754_idx_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="deposit",
            old_name="quidax_reference",
            new_name="tx_hash",
        ),
        migrations.AlterField(
            model_name="deposit",
            name="tx_hash",
            field=models.CharField(
                help_text="On-chain transaction hash \u2014 used as idempotency key to prevent double-crediting",
                max_length=255,
                unique=True,
            ),
        ),
    ]
