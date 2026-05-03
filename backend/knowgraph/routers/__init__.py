from fastapi import FastAPI

from knowgraph.mcp.tools import mcp

from .chat import router as chat_router
from .rag import router as rag_router

mcp_app = mcp.http_app()
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(rag_router, prefix="/rag", tags=["rag"])

__all__ = ["chat_router", "rag_router"]
