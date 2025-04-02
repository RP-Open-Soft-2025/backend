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
# from routes.chain import router as ChainRouter
from utils.scheduler import setup_scheduler
from middleware import AuthMiddleware

# Initialize scheduler
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event to initialize resources like the database and scheduler."""
    # Initialize database first
    await initiate_database()
    
    # Then initialize scheduler
    global scheduler
    scheduler = setup_scheduler()
    
    yield
    
    # Cleanup
    if scheduler:
        scheduler.shutdown()

# Create FastAPI app with lifespan
app = FastAPI(
    title="Fantastic App",
    description="An API for managing students and administrators.",
    lifespan=lifespan
)

# Configure middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.add_middleware(AuthMiddleware)

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
# app.include_router(ChainRouter, tags=["Chain"], prefix="/chain")
