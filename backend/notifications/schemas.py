from ninja import Schema
from datetime import datetime
from typing import Optional
from django.utils.timesince import timesince
from django.utils import timezone

class NotificationOut(Schema):
    id: int
    type: str
    title: str
    body: str
    read: bool
    time: str

    @staticmethod
    def resolve_time(obj):
        return f"{timesince(obj.created_at, timezone.now()).split(',')[0]} ago"
