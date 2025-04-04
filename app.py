from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from auth.jwt_bearer import JWTBearer
from config.config import initiate_database
from routes.auth import router as authRouter
from routes.admin import router as AdminRouter
from routes.employee import router as EmployeeRouter
from routes.session import router as SessionRouter
from routes.llm_chat import router as LLMChatRouter
from routes.chat import router as ChatRouter
from routes.meet import router as MeetRouter
# from routes.chain import router as ChainRouter
from utils.scheduler import setup_scheduler
from middleware import AuthMiddleware
from models.reset_token import ResetToken
import asyncio

# Initialize scheduler
scheduler = None

async def cleanup_expired_tokens():
    """Periodic task to clean up expired tokens."""
    try:
        await ResetToken.cleanup_expired_tokens()
        print("Cleaned up expired tokens")
    except Exception as e:
        print(f"Error cleaning up tokens: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event to initialize resources like the database and scheduler."""
    # Initialize database first
    await initiate_database()
    
    # Then initialize scheduler
    global scheduler
    scheduler = setup_scheduler()
    
    # Start token cleanup task
    asyncio.create_task(periodic_cleanup())
    
    yield
    
    # Cleanup
    if scheduler:
        scheduler.shutdown()

async def periodic_cleanup():
    """Run token cleanup every 10 minutes."""
    while True:
        await cleanup_expired_tokens()
        await asyncio.sleep(600)  # 10 minutes

# Create FastAPI app with lifespan
app = FastAPI(
    title="Deloitte Chatbot API",
    description="An API for managing employees and administrators.",
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
app.include_router(AdminRouter, prefix="/admin")
app.include_router(EmployeeRouter, tags=["Employee"], prefix="/employee")
app.include_router(ChatRouter, tags=["chat"], prefix="/chat")
app.include_router(LLMChatRouter, tags=["LLM-Chat"], prefix="/llm/chat")
# app.include_router(ChainRouter, tags=["Chain"], prefix="/chain")
app.include_router(MeetRouter, tags=["Meetings"], prefix="/meet")