from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import initialize, router


app = FastAPI(title="AI RPG World Data Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    initialize()


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(router)
