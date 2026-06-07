from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routers import dreamers, questions, recommend

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Karynos Hypo API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dreamers.router)
app.include_router(questions.router)
app.include_router(recommend.router)


@app.get("/health")
def health():
    return {"status": "ok"}
