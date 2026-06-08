from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional


class UserRegisterSchema(BaseModel):
    """Schema for user registration"""
    full_name: str = Field(..., min_length=2, max_length=255, examples=["John Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    phone_number: Optional[str] = Field(None, max_length=20, examples=["+1234567890"])
    password: str = Field(..., min_length=8, examples=["SecurePass123"])
    confirm_password: str = Field(..., min_length=8, examples=["SecurePass123"])

    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class UserLoginSchema(BaseModel):
    """Schema for user login"""
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=8, examples=["SecurePass123"])


class UserResponseSchema(BaseModel):
    """Schema for user response"""
    id: str
    full_name: str
    email: str
    phone_number: Optional[str] = None
    created_at: str
    updated_at: str
    last_login: Optional[str] = None

    class Config:
        from_attributes = True


class AuthTokenResponseSchema(BaseModel):
    """Schema for authentication token response"""
    access: str
    refresh: Optional[str] = None
    user: UserResponseSchema

class ForgotPasswordSchema(BaseModel):
    """Schema for requesting a password reset token"""
    email: EmailStr = Field(..., examples=["john@example.com"])

class ResetPasswordSchema(BaseModel):
    """Schema for resetting password with a token"""
    email: EmailStr = Field(..., examples=["john@example.com"])
    token: str = Field(..., min_length=6, max_length=6, examples=["123456"])
    new_password: str = Field(..., min_length=8, examples=["NewSecurePass123"])
    confirm_password: str = Field(..., min_length=8, examples=["NewSecurePass123"])

    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v

class ChangePasswordSchema(BaseModel):
    """Schema for changing password when authenticated"""
    old_password: str = Field(..., examples=["CurrentPass123"])
    new_password: str = Field(..., min_length=8, examples=["NewSecurePass123"])
    confirm_password: str = Field(..., min_length=8, examples=["NewSecurePass123"])

    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v

class LogoutSchema(BaseModel):
    """Schema for JWT logout (blacklist refresh token)"""
    refresh: str = Field(..., examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])

class VerifyEmailSchema(BaseModel):
    """Schema for verifying email with a token"""
    email: EmailStr = Field(..., examples=["john@example.com"])
    token: str = Field(..., min_length=6, max_length=6, examples=["123456"])


class ResendVerificationSchema(BaseModel):
    """Schema for requesting a new email verification code"""
    email: EmailStr = Field(..., examples=["john@example.com"])
