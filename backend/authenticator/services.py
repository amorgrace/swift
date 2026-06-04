import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from ninja_jwt.tokens import RefreshToken
from typing import Optional, Dict, Any

from .email import (
    send_password_reset_email,
    send_password_changed_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class AuthenticationService:
    """Service for authentication operations"""

    @staticmethod
    def create_user(
        full_name: str,
        email: str,
        password: str,
        phone_number: Optional[str] = None
    ) -> User:
        """
        Create a new user with the given credentials.
        
        Args:
            full_name: User's full name
            email: User's email (unique)
            password: User's password (will be hashed)
            phone_number: Optional phone number
            
        Returns:
            Created User instance
            
        Raises:
            ValueError: If email already exists
        """
        from django.db import transaction

        if User.objects.filter(email=email).exists():
            raise ValueError(f"User with email {email} already exists")

        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                full_name=full_name,
                phone_number=phone_number,
                password=password,
                is_active=False
            )

            AuthenticationService.generate_email_verification_token(email)

        # Create user NGN wallet and Quidax sub-account asynchronously
        try:
            from wallets.services import WalletService
            WalletService.create_wallet_for_user(user)
        except Exception as e:
            logger.error(f"Failed to create wallet for {user.email}: {e}")

        return user

    @staticmethod
    def authenticate_user(email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.
        
        Args:
            email: User's email
            password: User's password
            
        Returns:
            User instance if credentials are valid, None otherwise
        """
        try:
            user = User.objects.get(email=email)
            if check_password(password, user.password):
                return user
        except User.DoesNotExist:
            pass
        return None

    @staticmethod
    def get_tokens_for_user(user: User) -> Dict[str, str]:
        """
        Generate JWT tokens for a user.
        
        Args:
            user: User instance
            
        Returns:
            Dictionary with access and refresh tokens
        """
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """
        Get user by email.
        
        Args:
            email: User's email
            
        Returns:
            User instance or None
        """
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            return None

    @staticmethod
    def generate_password_reset_token(email: str) -> Optional[str]:
        """Generate a 6-digit password reset token for the given email."""
        from django.utils import timezone
        import secrets
        from datetime import timedelta
        from .models import PasswordResetToken

        user = AuthenticationService.get_user_by_email(email)
        if not user:
            return None
        
        # Invalidate old tokens
        PasswordResetToken.objects.filter(user=user).delete()
        
        # Generate new 6-digit token
        token_val = "".join(str(secrets.randbelow(10)) for _ in range(6))
        
        PasswordResetToken.objects.create(
            user=user,
            token=token_val,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        send_password_reset_email(user, token_val)

        return token_val

    @staticmethod
    def generate_email_verification_token(email: str) -> Optional[str]:
        """Generate a 6-digit email verification token for the given email."""
        from django.utils import timezone
        import secrets
        from datetime import timedelta
        from .models import EmailVerificationToken

        user = AuthenticationService.get_user_by_email(email)
        if not user:
            return None
        
        # Invalidate old tokens
        EmailVerificationToken.objects.filter(user=user).delete()
        
        # Generate new 6-digit token
        token_val = "".join(str(secrets.randbelow(10)) for _ in range(6))
        
        EmailVerificationToken.objects.create(
            user=user,
            token=token_val,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        success = send_verification_email(user, token_val)
        if not success:
            raise ValueError("Failed to send verification email. Please try again later.")

        return token_val

    @staticmethod
    def verify_email_token(email: str, token: str) -> bool:
        """Verify the email verification token and activate the user."""
        from django.utils import timezone
        from .models import EmailVerificationToken

        user = AuthenticationService.get_user_by_email(email)
        if not user:
            raise ValueError("Invalid email or token")

        try:
            verification_token = EmailVerificationToken.objects.get(user=user, token=token)
        except EmailVerificationToken.DoesNotExist:
            raise ValueError("Invalid email or token")

        if verification_token.expires_at < timezone.now():
            verification_token.delete()
            raise ValueError("Token has expired")

        user.is_active = True
        user.save()
        verification_token.delete()

        return True

    @staticmethod
    def reset_password_with_token(email: str, token: str, new_password: str) -> bool:
        """Verify token and reset password."""
        from django.utils import timezone
        from .models import PasswordResetToken

        user = AuthenticationService.get_user_by_email(email)
        if not user:
            raise ValueError("Invalid email or token")

        try:
            reset_token = PasswordResetToken.objects.get(user=user, token=token)
        except PasswordResetToken.DoesNotExist:
            raise ValueError("Invalid email or token")

        if reset_token.expires_at < timezone.now():
            reset_token.delete()
            raise ValueError("Token has expired")

        user.set_password(new_password)
        user.save()
        reset_token.delete()

        send_password_changed_email(user)

        return True

    @staticmethod
    def change_user_password(user: User, old_password: str, new_password: str) -> bool:
        """Change authenticated user's password."""
        if not user.check_password(old_password):
            raise ValueError("Incorrect old password")

        user.set_password(new_password)
        user.save()

        send_password_changed_email(user)

        return True
