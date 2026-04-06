"""
AI EvoGraph FastAPI application entry point.

Exposes four core feature endpoints:
  POST /api/lineage      — Research Lineage Exploration
  POST /api/breakthrough — Breakthrough Detection
  POST /api/trend        — Trending Methods Discovery
  POST /api/evolution    — Method Evolution Path
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aievograph.api.routers import breakthrough, evolution, lineage, trend
from aievograph.infrastructure.logging import configure_logging

configure_logging()

app = FastAPI(
    title="AI EvoGraph API",
    description="GraphRAG-based analysis of AI research paper evolution",
    version="0.1.0",
)

# Allow the Next.js dev server (port 3000) and any Vercel deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lineage.router)
app.include_router(breakthrough.router)
app.include_router(trend.router)
app.include_router(evolution.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
