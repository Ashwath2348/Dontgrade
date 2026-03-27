from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from .routes import auth_routes, analysis_routes

app = FastAPI()

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(analysis_routes.router)

repo_frontend_dir = Path(__file__).resolve().parent / "frontend"
workspace_frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
frontend_dir = (
    repo_frontend_dir
    if repo_frontend_dir.exists()
    else workspace_frontend_dir
)
assets_dir = frontend_dir / "assets"

if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/")
def frontend_index():
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend not found"}


@app.get("/login")
def frontend_login_page():
    login_file = frontend_dir / "login.html"
    if login_file.exists():
        return FileResponse(login_file)
    return {"message": "Login page not found"}


@app.get("/signup")
def frontend_signup_page():
    signup_file = frontend_dir / "signup.html"
    if signup_file.exists():
        return FileResponse(signup_file)
    return {"message": "Signup page not found"}


@app.get("/history-page")
def frontend_history_page():
    history_file = frontend_dir / "history.html"
    if history_file.exists():
        return FileResponse(history_file)
    return {"message": "History page not found"}
