import httpx
from django.conf import settings

def get_headers():
    return {
        "x-api-key": settings.PREMBLY_API_KEY,
        "Content-Type": "application/json"
    }

def get_base_url():
    return settings.PREMBLY_BASE_URL.rstrip('/')

def verify_nin(number: str) -> dict:
    """POST /verification/vnin-basic"""
    with httpx.Client() as client:
        response = client.post(
            f"{get_base_url()}/verification/vnin-basic", 
            headers=get_headers(), 
            json={"number": number}
        )
        response.raise_for_status()
        return response.json()

def verify_bvn(number: str) -> dict:
    """POST /verification/bvn"""
    with httpx.Client() as client:
        response = client.post(
            f"{get_base_url()}/verification/bvn", 
            headers=get_headers(), 
            json={"number": number}
        )
        response.raise_for_status()
        return response.json()

def verify_drivers_license(number: str, dob: str, first_name: str, last_name: str) -> dict:
    """POST /verification/drivers_license/advance"""
    with httpx.Client() as client:
        response = client.post(
            f"{get_base_url()}/verification/drivers_license/advance",
            headers=get_headers(),
            json={
                "number": number,
                "dob": dob,
                "first_name": first_name,
                "last_name": last_name
            }
        )
        response.raise_for_status()
        return response.json()

def check_face_liveness(image_url: str) -> dict:
    """POST /verification/biometrics/face/liveliness_check"""
    with httpx.Client() as client:
        response = client.post(
            f"{get_base_url()}/verification/biometrics/face/liveliness_check",
            headers=get_headers(),
            json={"image": image_url}
        )
        response.raise_for_status()
        return response.json()

def compare_faces(image_one: str, image_two: str) -> dict:
    """POST /verification/biometrics/face/comparison"""
    with httpx.Client() as client:
        response = client.post(
            f"{get_base_url()}/verification/biometrics/face/comparison",
            headers=get_headers(),
            json={
                "image_one": image_one,
                "image_two": image_two
            }
        )
        response.raise_for_status()
        return response.json()
