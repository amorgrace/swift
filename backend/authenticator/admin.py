from django.contrib import admin
from .models import User, PasswordResetToken, EmailVerificationToken, PinUpdateToken

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'phone_number', 'is_staff', 'is_active', 'created_at')
    search_fields = ('email', 'full_name', 'phone_number')
    ordering = ('-created_at',)
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    
@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')

@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')

@admin.register(PinUpdateToken)
class PinUpdateTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')
