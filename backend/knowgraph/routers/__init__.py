from fastapi import APIRouter

from .chat import router as chat_router
from .rag import router as rag_router

api_router = APIRouter()
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])

__all__ = ["api_router", "chat_router", "rag_router"]
