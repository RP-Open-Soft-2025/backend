import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8080,
        reload=True,
        timeout_keep_alive=86400, # 1 day in seconds
        timeout_notify=0,  # Disable timeout notifications
        timeout_graceful_shutdown=None  # No graceful shutdown timeout
    )
