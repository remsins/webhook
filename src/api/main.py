from dotenv import load_dotenv

# Load environment variables first, before importing modules that depend on them
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.db.session import Base, engine
from src.api.routes.subscriptions import router as subs_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.status import router as status_router

# Auto-create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Webhook Delivery Service",
    version="0.1.1",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

origins = [
    "http://localhost:8501", # Streamlit default dev server
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods (GET, POST, PATCH, DELETE, etc.)
    allow_headers=["*"], # Allow all headers
)

# Subscription CRUD
app.include_router(
    subs_router,
    prefix="/subscriptions",
    tags=["subscriptions"],
)

# Ingestion endpoint
app.include_router(
    ingest_router,
    tags=["ingest"],
)

# Status & Analytics endpoints
app.include_router(
    status_router,
    tags=["analytics"],
)