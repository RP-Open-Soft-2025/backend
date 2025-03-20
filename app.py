from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from auth.jwt_bearer import JWTBearer
from config.config import initiate_database
from routes.login import router as LoginRouter
from routes.admin import router as AdminRouter
from routes.admin_hr import router as AdminHRRouter
from routes.employee import router as EmployeeRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event to initialize resources like the database."""
    await initiate_database()
    yield  # No cleanup needed, but you can add if necessary


app = FastAPI(
    title="Fantastic App",
    description="An API for managing students and administrators.",
    lifespan=lifespan  # Register lifespan handler
)

token_listener = JWTBearer()


@app.get("/", tags=["Root"])
async def read_root() -> dict:
    """Root endpoint."""
    return {"message": "Welcome to this fantastic app."}


# Including routers
app.include_router(LoginRouter, tags=["Login"], prefix="/login")
app.include_router(AdminRouter, tags=["Admin"], prefix="/admin")
app.include_router(AdminHRRouter, tags=["Admin-HR"], prefix="/admin-hr")
app.include_router(EmployeeRouter, tags=["Employee"], prefix="/user")

