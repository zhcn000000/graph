from fastapi import FastAPI

from knowgraph.tools.mcp import mcp

from .chat import router as chat_router
from .rag import router as rag_router
from .user import auth_router
from .user import router as user_router

mcp_app = mcp.http_app()
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(rag_router, prefix="/rag", tags=["rag"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(user_router, prefix="/users", tags=["users"])

__all__ = ["auth_router", "chat_router", "rag_router", "user_router"]
