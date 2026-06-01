import logging
from typing import Annotated, Literal

import uvicorn
import uvloop
from asyncer import runnify
from rich import traceback
from rich.logging import RichHandler
from typer import Argument, Option, Typer

from knowgraph.adapters import PhilaMuseumAdapter, PhilaMuseumRawAdapter
from knowgraph.database.artifact import ArtifactStore
from knowgraph.database.document import DocumentStore
from knowgraph.database.initdb import clean_db, init_db, reset_db
from knowgraph.routers import app
from knowgraph.spider.runner import ScrapyCrawler
from knowgraph.utils.environments import settings

cmd = Typer(pretty_exceptions_enable=False)
ingest_cmd = Typer(pretty_exceptions_enable=False, help="数据摄入命令")


@cmd.command()
@runnify
async def start() -> None:
    config = uvicorn.Config(
        app,
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        log_level="info",
        workers=5,
        log_config=None,
        access_log=True,
        ssl_keyfile=settings.SSL_KEY_PATH
        if settings.SSL_KEY_PATH is not None and settings.SSL_KEY_PATH.exists()
        else None,
        ssl_certfile=settings.SSL_CERT_PATH
        if settings.SSL_CERT_PATH is not None and settings.SSL_CERT_PATH.exists()
        else None,
    )
    server = uvicorn.Server(config)
    await server.serve()


@cmd.command()
@runnify
async def database(
    mode: Annotated[Literal["init", "reset", "clean"], Argument(help="Database operation mode")],
    dbname: Annotated[str | None, Option("--dbname", "-d", help="Name of the database to initialize")] = None,
) -> None:
    if mode == "init":
        await init_db(dbname=dbname)
    elif mode == "reset":
        await reset_db(dbname=dbname)
    elif mode == "clean":
        await clean_db(dbname=dbname)


@cmd.command()
@runnify
async def spider(museum: Annotated[list[str], Argument(help="List of museums to crawl")]) -> None:
    crawler = ScrapyCrawler()
    await crawler.acrawl_museums(museum)


@ingest_cmd.command("csv")
@runnify
async def ingest_csv(
    csv_path: Annotated[str, Argument(help="Path to CSV file")],
    adapter: Annotated[
        str,
        Option("--adapter", "-a", help="Adapter name: philamuseum, philamuseum_raw"),
    ] = "philamuseum_raw",
    data_dir: Annotated[
        str | None,
        Option("--data-dir", "-d", help="Directory with reference tables (dynasties, museums)"),
    ] = None,
) -> None:
    if adapter == "philamuseum":
        adp = PhilaMuseumAdapter(data_dir=data_dir)
    elif adapter == "philamuseum_raw":
        adp = PhilaMuseumRawAdapter()
    else:
        logging.error("未知适配器: %s", adapter)
        raise SystemExit(1)

    rows = adp.load_csv(csv_path)
    if not rows:
        logging.warning("CSV 中没有有效数据行")
        return

    store = ArtifactStore()
    count = await store.ainsert_artifacts(rows)
    logging.info("已导入 %d 条文物记录到 ArtifactStore", count)


@ingest_cmd.command("artifacts")
@runnify
async def ingest_artifacts(
    museum: Annotated[str | None, Option("--museum", "-m", help="Filter by museum name")] = None,
    limit: Annotated[int | None, Option("--limit", "-n", help="Max artifacts to ingest")] = None,
    use_llm: Annotated[bool, Option("--llm/--no-llm", help="Enable/disable LLM triple extraction")] = False,
) -> None:
    store = DocumentStore()
    file_ids = await store.alingest_artifacts(museum=museum, limit=limit, use_llm=use_llm)
    logging.info("已从 ArtifactStore 提取 %d 个文档到 DocumentTable", len(file_ids))


cmd.add_typer(ingest_cmd, name="ingest")


def main():
    traceback.install()
    uvloop.install()
    logging.captureWarnings(True)

    logging.basicConfig(
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    cmd()


if __name__ == "__main__":
    main()
