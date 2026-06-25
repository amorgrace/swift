from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from .models import Notification
from .schemas import NotificationOut

router = Router(tags=["Notifications"])

@router.get("/", response=List[NotificationOut])
def get_notifications(request):
    """Get all notifications for the authenticated user"""
    return Notification.objects.filter(user=request.user)

@router.patch("/{notification_id}/read")
def mark_as_read(request, notification_id: int):
    """Mark a specific notification as read"""
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.read = True
    notif.save()
    return {"success": True}

@router.post("/mark-all-read")
def mark_all_read(request):
    """Mark all notifications for the user as read"""
    Notification.objects.filter(user=request.user, read=False).update(read=True)
    return {"success": True}

@router.delete("/{notification_id}")
def delete_notification(request, notification_id: int):
    """Delete a specific notification"""
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.delete()
    return {"success": True}
