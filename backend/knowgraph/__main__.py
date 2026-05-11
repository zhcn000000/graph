import logging
from typing import Annotated, Literal

import uvicorn
import uvloop
from asyncer import runnify
from rich import traceback
from rich.logging import RichHandler
from typer import Argument, Option, Typer

from knowgraph.database.initdb import clean_db, init_db, reset_db
from knowgraph.routers import app
from knowgraph.spider.runner import ScrapyCrawler
from knowgraph.utils.environments import settings

cmd = Typer(pretty_exceptions_enable=False)


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
