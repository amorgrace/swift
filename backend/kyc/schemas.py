from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class KYCStep1Schema(BaseModel):
    document_type: str = Field(..., examples=["nin", "bvn", "drivers_license"])
    document_number: str = Field(..., min_length=5, max_length=50, examples=["12345678901"])
    date_of_birth: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class KYCStep1ResponseSchema(BaseModel):
    status: str
    document_type: str
    verified_name: str
    date_of_birth: Optional[str] = None

class KYCStep2Schema(BaseModel):
    selfie_url: HttpUrl

class KYCStep2ResponseSchema(BaseModel):
    status: str
    message: str
    remaining_attempts: Optional[int] = None

class KYCResponseSchema(BaseModel):
    status: str
    document_type: str
    document_number: str
    rejection_reason: Optional[str] = None
    created_at: str

class AdminKYCResponseSchema(KYCResponseSchema):
    id: str
    user_id: str
    user_email: str
    user_full_name: str
    document_url: Optional[str] = None
    selfie_url: Optional[str] = None

