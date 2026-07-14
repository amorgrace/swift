import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from rates.models import GiftCardTransaction, RejectionReason
from authenticator.models import User

tx = GiftCardTransaction.objects.filter(status='pending').first()
reason = RejectionReason.objects.first()
admin = User.objects.filter(is_staff=True).first()

if tx and reason and admin:
    from django.utils import timezone
    tx.status = 'rejected'
    tx.rejection_reason = reason
    tx.reviewed_by = admin
    tx.reviewed_at = timezone.now()
    try:
        tx.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])
        print("Success")
    except Exception as e:
        print(f"Error: {e}")
else:
    print(f"Missing data tx={tx}, reason={reason}, admin={admin}")
