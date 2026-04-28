from fastapi import APIRouter, FastAPI

from knowgraph.mcp.tools import mcp

app = FastAPI(title="KnowGraph API")

mcp_router = mcp.http_handler()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/mcp/sse")
async def mcp_sse():
    return mcp_router


@app.post("/mcp/sse")
async def mcp_sse_post():
    return mcp_router


api_router = APIRouter()
api_router.include_router(mcp_router, prefix="/mcp")
app.include_router(api_router)


def mount_mcp(app: FastAPI) -> FastAPI:
    app.include_router(api_router)
    return app
