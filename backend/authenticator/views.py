from ninja import Router
from ninja.errors import HttpError
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import get_user_model
from .schemas import (
	UserRegisterSchema,
	UserLoginSchema,
	AuthTokenResponseSchema,
	UserResponseSchema,
    ForgotPasswordSchema,
    ResetPasswordSchema,
    ChangePasswordSchema,
    LogoutSchema,
    VerifyEmailSchema,
    ResendVerificationSchema,
    AdminUserResponseSchema,
    AdminAuthTokenResponseSchema,
)
from decimal import Decimal
from .services import AuthenticationService

User = get_user_model()

# Router for authentication endpoints
router = Router(tags=["Authentication"])


@router.post("/register", response={200: dict}, auth=None)
@ratelimit(key='ip', rate='10/h', block=True)
def register(request, payload: UserRegisterSchema):
	try:
		user = AuthenticationService.create_user(
			full_name=payload.full_name,
			email=payload.email,
			password=payload.password,
			phone_number=payload.phone_number,
		)

		return {"message": "Verification email sent. Please check your inbox.", "email": user.email}

	except ValueError as e:
		raise HttpError(400, str(e))
	except Exception as e:
		raise HttpError(500, f"Registration failed: {str(e)}")


@router.post("/verify-email", response=AuthTokenResponseSchema, auth=None)
@ratelimit(key='ip', rate='15/m', block=True)
def verify_email(request, payload: VerifyEmailSchema):
    try:
        success = AuthenticationService.verify_email_token(
            email=payload.email, token=payload.token
        )
        if success:
            user = AuthenticationService.get_user_by_email(payload.email)
            tokens = AuthenticationService.get_tokens_for_user(user)

            user_data = UserResponseSchema(
                id=str(user.id),
                full_name=user.full_name,
                email=user.email,
                phone_number=user.phone_number,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat(),
                last_login=user.last_login.isoformat() if user.last_login else None,
            )

            return AuthTokenResponseSchema(
                access=tokens["access"], refresh=tokens.get("refresh"), user=user_data
            )
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Verification failed: {str(e)}")


@router.post("/login", response=AuthTokenResponseSchema, auth=None)
@ratelimit(key='ip', rate='10/m', block=True)
def login(request, payload: UserLoginSchema):
	try:
		user = AuthenticationService.authenticate_user(
			email=payload.email, password=payload.password
		)

		if not user:
			raise HttpError(401, "Invalid email or password")

		tokens = AuthenticationService.get_tokens_for_user(user)

		user_data = UserResponseSchema(
			id=str(user.id),
			full_name=user.full_name,
			email=user.email,
			phone_number=user.phone_number,
			created_at=user.created_at.isoformat(),
			updated_at=user.updated_at.isoformat(),
			last_login=user.last_login.isoformat() if user.last_login else None,
		)

		return AuthTokenResponseSchema(
			access=tokens["access"], refresh=tokens.get("refresh"), user=user_data
		)

	except HttpError:
		raise
	except Exception as e:
		raise HttpError(500, f"Login failed: {str(e)}")


@router.post("/admin/login", response=AdminAuthTokenResponseSchema, auth=None)
@ratelimit(key='ip', rate='10/m', block=True)
def admin_login(request, payload: UserLoginSchema):
	try:
		user = AuthenticationService.authenticate_user(
			email=payload.email, password=payload.password
		)

		if not user:
			raise HttpError(401, "Invalid email or password")
            
		if not user.is_staff:
			raise HttpError(403, "Permission denied. Admin access only.")

		tokens = AuthenticationService.get_tokens_for_user(user)

		balance = Decimal('0.00')
		if hasattr(user, 'ngn_wallet'):
			balance = user.ngn_wallet.balance

		user_data = AdminUserResponseSchema(
			id=str(user.id),
			full_name=user.full_name,
			email=user.email,
			phone_number=user.phone_number,
			created_at=user.created_at.isoformat(),
			updated_at=user.updated_at.isoformat(),
			last_login=user.last_login.isoformat() if user.last_login else None,
			kyc_status=user.kyc.status if hasattr(user, 'kyc') else None,
			ngn_balance=balance,
			is_staff=user.is_staff,
			is_active=user.is_active
		)

		return AdminAuthTokenResponseSchema(
			access=tokens["access"], refresh=tokens.get("refresh"), user=user_data
		)

	except HttpError:
		raise
	except Exception as e:
		raise HttpError(500, f"Login failed: {str(e)}")


@router.get("/me", response=UserResponseSchema)
def get_current_user(request):
	if not request.user or not request.user.is_authenticated:
		raise HttpError(401, "Not authenticated")

	return UserResponseSchema(
		id=str(request.user.id),
		full_name=request.user.full_name,
		email=request.user.email,
		phone_number=request.user.phone_number,
		created_at=request.user.created_at.isoformat(),
		updated_at=request.user.updated_at.isoformat(),
		last_login=request.user.last_login.isoformat() if request.user.last_login else None,
	)

@router.post("/forget-password", response={200: dict}, auth=None)
@ratelimit(key='ip', rate='5/h', block=True)
def forget_password(request, payload: ForgotPasswordSchema):
    try:
        token = AuthenticationService.generate_password_reset_token(payload.email)
        # Even if token is None (user not found), return success to avoid email enumeration
        return {"message": "If an account with that email exists, a password reset token has been generated."}
    except Exception as e:
        raise HttpError(500, f"Failed to process request: {str(e)}")

@router.post("/reset-password", response={200: dict}, auth=None)
@ratelimit(key='ip', rate='15/m', block=True)
def reset_password(request, payload: ResetPasswordSchema):
    try:
        success = AuthenticationService.reset_password_with_token(
            email=payload.email,
            token=payload.token,
            new_password=payload.new_password
        )
        if success:
            return {"message": "Password has been successfully reset."}
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Reset failed: {str(e)}")

@router.post("/change-password", response={200: dict})
@ratelimit(key='user', rate='10/h', block=True)
def change_password(request, payload: ChangePasswordSchema):
    if not request.user or not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
        
    try:
        success = AuthenticationService.change_user_password(
            user=request.user,
            old_password=payload.old_password,
            new_password=payload.new_password
        )
        if success:
            return {"message": "Password changed successfully."}
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Change password failed: {str(e)}")

@router.post("/logout", response={200: dict})
def logout(request, payload: LogoutSchema):
    try:
        from ninja_jwt.tokens import RefreshToken
        token = RefreshToken(payload.refresh)
        token.blacklist()
        return {"message": "Successfully logged out."}
    except Exception as e:
        raise HttpError(400, f"Logout failed: {str(e)}")

@router.post("/resend-reset-token", response={200: dict}, auth=None)
@ratelimit(key='ip', rate='5/h', block=True)
def resend_reset_token(request, payload: ForgotPasswordSchema):
    try:
        token = AuthenticationService.generate_password_reset_token(payload.email)
        return {"message": "If an account with that email exists, a new password reset token has been sent."}
    except Exception as e:
        raise HttpError(500, f"Failed to resend token: {str(e)}")


@router.post("/resend-verification", response={200: dict}, auth=None)
@ratelimit(key='ip', rate='5/h', block=True)
def resend_verification_email(request, payload: ResendVerificationSchema):
    """
    Resend the email verification code to the given email address.
    Only works if the account exists and is not yet verified.
    """
    try:
        AuthenticationService.resend_email_verification(payload.email)
        return {"message": "If an unverified account with that email exists, a new verification code has been sent."}
    except Exception as e:
        raise HttpError(500, f"Failed to resend verification email: {str(e)}")


@router.delete("/deactivate", response={200: dict})
def deactivate_account(request):
    """
    Deactivate the user account by setting is_active to False.
    This allows the user to be reinstated later if desired.
    """
    try:
        user = request.user
        user.is_active = False
        user.save()
        return {"message": "Account deactivated successfully."}
    except Exception as e:
        raise HttpError(500, f"Failed to deactivate account: {str(e)}")


@router.get("/admin/users", response=list[AdminUserResponseSchema])
def get_all_users(request):
    """Admin endpoint to list all users with balances and KYC statuses."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    
    users = User.objects.all().select_related('kyc', 'ngn_wallet')
    
    result = []
    for user in users:
        # Get balance
        balance = Decimal('0.00')
        if hasattr(user, 'ngn_wallet'):
            balance = user.ngn_wallet.balance
            
        # Get latest KYC status
        kyc_status = None
        if hasattr(user, 'kyc'):
            kyc_status = user.kyc.status
            
        result.append(AdminUserResponseSchema(
            id=str(user.id),
            full_name=user.full_name,
            email=user.email,
            phone_number=user.phone_number,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None,
            kyc_status=kyc_status,
            ngn_balance=balance,
            is_staff=user.is_staff,
            is_active=user.is_active
        ))
        
    return result

