from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class KYCSubmissionSchema(BaseModel):
    document_type: str = Field(..., examples=["bvn", "nin", "drivers_license", "passport"])
    document_number: str = Field(..., min_length=5, max_length=50, examples=["12345678901"])
    document_url: HttpUrl = Field(..., examples=["https://res.cloudinary.com/demo/image/upload/id_front.jpg"])
    selfie_url: HttpUrl = Field(..., examples=["https://res.cloudinary.com/demo/image/upload/selfie.jpg"])


class KYCResponseSchema(BaseModel):
    status: str
    document_type: str
    document_number: str
    rejection_reason: Optional[str] = None
    created_at: str
