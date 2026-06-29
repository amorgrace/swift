from ninja import NinjaAPI
from ninja_jwt.authentication import JWTAuth
from authenticator.views import router as auth_router
from rates.views import router as rates_router
from wallets.views import router as wallets_router
from transactions.views import router as transactions_router
from transactions.webhooks import router as webhooks_router
from kyc.views import router as kyc_router
from dashboard.views import router as dashboard_router
from notifications.views import router as notifications_router
from django_ratelimit.exceptions import Ratelimited

api = NinjaAPI(
    title="Swift API",
    description="API documentation for the Swift backend",
    version="1.0.0",
    docs_url="/docs",
    auth=JWTAuth(),
)

# Register app routers here
api.add_router("auth/", auth_router)
api.add_router("rates/", rates_router)
api.add_router("wallets/", wallets_router)
api.add_router("transactions/", transactions_router)
api.add_router("webhooks/", webhooks_router)

api.add_router("kyc/", kyc_router)
api.add_router("dashboard/", dashboard_router)
api.add_router("notifications/", notifications_router)


@api.exception_handler(Ratelimited)
def ratelimited_handler(request, exc):
    return api.create_response(
        request,
        {"message": "Too many requests. Please try again later."},
        status=429,
    )

@api.get("/")
def health_check(request):
    return {"msg": "Hello from Django Ninja (engine)"}
