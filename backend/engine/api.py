from ninja import NinjaAPI
from ninja_jwt.authentication import JWTAuth
from authenticator.views import router as auth_router

api = NinjaAPI(
    title="Swift API",
    description="API documentation for the Swift backend",
    version="1.0.0",
    docs_url="/docs",
    auth=JWTAuth(),
)

# Register app routers here
api.add_router("auth/", auth_router)


@api.get("/")
def root(request):
    return {"msg": "Hello from Django Ninja (engine)"}
