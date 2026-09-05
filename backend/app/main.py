from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import sentry_sdk

from app.config import settings
from app.database import get_db, engine, Base
from app.logging_config import logger
from app.api.vendor import router as vendor_router

# Initialize Sentry
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0,
    )

# Create tables (for initial setup, Alembic will handle migrations)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kombain API")

# Include routers
app.include_router(vendor_router)


@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}


@app.get("/readyz")
async def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return {"status": "not ready"}, 503


@app.get("/")
async def root():
    return {"message": "Welcome to Kombain API"}
