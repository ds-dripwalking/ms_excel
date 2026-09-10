"""API роутеры v1."""
from app.api.v1.vendor import router as vendor_router
from app.api.v1.auth import router as auth_router
from app.api.v1.profiles import router as profiles_router

__all__ = ["vendor_router", "auth_router", "profiles_router"]
