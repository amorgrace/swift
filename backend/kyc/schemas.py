from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class KYCSubmitSchema(BaseModel):
    document_type: str = Field(..., examples=["nin", "drivers_license", "voters_card", "international_passport"])
    document_number: str = Field(..., min_length=5, max_length=50, examples=["12345678901"])
    document_url: HttpUrl
    selfie_url: HttpUrl
    date_of_birth: Optional[str] = None

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

