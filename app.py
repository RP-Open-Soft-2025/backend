from fastapi import FastAPI, Depends, Request

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
# from auth.jwt_bearer import JWTBearer
from config.config import initiate_database
from routes.auth import router as authRouter
from routes.admin import router as AdminRouter
from routes.admin_hr import router as AdminHRRouter
from routes.employee import router as EmployeeRouter
from routes.hr import router as HRRouter
from routes.session import router as SessionRouter
from async_fastapi_jwt_auth import AuthJWT
from async_fastapi_jwt_auth.exceptions import AuthJWTException
from fastapi.middleware.cors import CORSMiddleware
# from middleware import AuthMiddleware
from config.config import JWTSettings
from fastapi.responses import JSONResponse
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

@AuthJWT.load_config
def get_config():
    return JWTSettings()  # Return your settings instance
@app.exception_handler(AuthJWTException)
async def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )
# Configure CORS
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://10.145.66.172:3000"],  # Allows all origins
#     allow_credentials=True,
#     allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],  # Allows all methods
#     allow_headers=["Authorization","Content-Type"],  # Allows all headers
# )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
# app.add_middleware(AuthMiddleware)
# token_listener = JWTBearer()


@app.get("/", tags=["Root"])
async def read_root() -> dict:
    """Root endpoint."""
    return {"message": "Welcome to this fantastic app."}

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}

# Including routers
app.include_router(authRouter,prefix="/auth", tags=["auth"])

app.include_router(AdminRouter, tags=["Admin"], prefix="/admin")
app.include_router(AdminHRRouter, tags=["Admin-HR"], prefix="/admin-hr")
app.include_router(EmployeeRouter, tags=["Employee"], prefix="/user")
app.include_router(HRRouter, tags=["HR"], prefix="/hr")
app.include_router(SessionRouter, tags=["Session"], prefix="/session")

