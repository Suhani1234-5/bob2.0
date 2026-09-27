from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.verify import router as verify_router
from routers.debug import router as debug_router
from routers.fix_verify import router as fix_verify_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ProofPR Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(verify_router)
app.include_router(debug_router)
app.include_router(fix_verify_router)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ProofPR Backend",
        "version": "0.1.0",
    }
