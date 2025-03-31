from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from auth.jwt_bearer import JWTBearer
from config.config import initiate_database
from routes.auth import router as authRouter
from routes.admin import router as AdminRouter
from routes.admin_hr import router as AdminHRRouter
from routes.employee import router as EmployeeRouter
from routes.hr import router as HRRouter
from routes.session import router as SessionRouter
from routes.llm_chat import router as LLMChatRouter
from routes.chat import router as ChatRouter

from fastapi.middleware.cors import CORSMiddleware 
from middleware import AuthMiddleware

app = FastAPI(
    title="Fantastic App",
    description="An API for managing students and administrators.",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.add_middleware(AuthMiddleware)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event to initialize resources like the database."""
    await initiate_database()
    yield  # No cleanup needed, but you can add if necessary

# Root endpoint
@app.get("/", tags=["Root"])
async def read_root() -> dict:
    """Root endpoint."""
    return {"message": "Welcome to this fantastic app."}

# Including routers
app.include_router(authRouter, prefix="/auth", tags=["auth"])
app.include_router(AdminRouter, tags=["Admin"], prefix="/admin")
app.include_router(AdminHRRouter, tags=["Admin-HR"], prefix="/admin-hr")
app.include_router(EmployeeRouter, tags=["Employee"], prefix="/employee")
app.include_router(HRRouter, tags=["HR"], prefix="/hr")
app.include_router(ChatRouter, tags=["chat"], prefix="/chat")
app.include_router(LLMChatRouter, tags=["LLM-Chat"], prefix="/llm/chat")
