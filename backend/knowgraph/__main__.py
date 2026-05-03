import logging
import sys

import uvicorn
import uvloop
from asyncer import runnify
from rich import traceback
from rich.logging import RichHandler
from typer import Typer

from knowgraph.database.initdb import init_db
from knowgraph.routers import app
from knowgraph.spider.runner import ScrapyCrawler
from knowgraph.utils.environments import FASTAPI_HOST, FASTAPI_PORT, SSL_CERT_PATH, SSL_KEY_PATH

cmd = Typer(pretty_exceptions_enable=False)


@cmd.command()
@runnify
async def run_client() -> None:
    config = uvicorn.Config(
        app,
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        log_level="info",
        workers=5,
        log_config=None,
        access_log=True,
        ssl_keyfile=SSL_KEY_PATH if SSL_KEY_PATH is not None and SSL_KEY_PATH.exists() else None,
        ssl_certfile=SSL_CERT_PATH if SSL_CERT_PATH is not None and SSL_CERT_PATH.exists() else None,
    )
    server = uvicorn.Server(config)
    await server.serve()


@cmd.command()
@runnify
async def initdb() -> None:
    await init_db()


@cmd.command()
@runnify
async def spider() -> None:
    crawler = ScrapyCrawler()
    await crawler.acrawl_museums()

def main():
    traceback.install()
    uvloop.install()
    logging.captureWarnings(True)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logging.basicConfig(
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    cmd()


if __name__ == "__main__":
    main()
