import logging
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import uvicorn
import uvloop
from asyncer import runnify
from rich import print as rprint
from rich import traceback
from rich.logging import RichHandler
from rich.table import Table
from typer import Argument, Option, Typer

from knowgraph.adapters import AsianArtAdapter, MetMuseumAdapter, PhilaMuseumAdapter
from knowgraph.database.artifact import ArtifactStore
from knowgraph.database.document import DocumentStore
from knowgraph.database.initdb import clean_db, init_db, reset_db
from knowgraph.database.ragmode import RAGMode
from knowgraph.routers import app
from knowgraph.spider.runner import ScrapyCrawler
from knowgraph.utils.environments import find_project_directory, settings

cmd = Typer(pretty_exceptions_enable=False)
ingest_cmd = Typer(pretty_exceptions_enable=False, help="数据摄入命令")

DEFAULT_DATA_DIR = find_project_directory() / "doc"


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


@cmd.command()
@runnify
async def search(
    query: Annotated[str, Argument(help="Search query")],
    k: Annotated[int, Option("--top", "-k", help="Number of results")] = 5,
    graph: Annotated[bool, Option("--graph/--no-graph", help="Enable/disable graph search")] = True,
    max_hops: Annotated[int, Option("--max-hops", "-h", help="Max graph traversal hops")] = 2,
    vector_weight: Annotated[float, Option("--vector-weight", help="Vector search weight")] = 0.4,
    bm25_weight: Annotated[float, Option("--bm25-weight", help="BM25 search weight")] = 0.3,
    graph_weight: Annotated[float, Option("--graph-weight", help="Graph search weight")] = 0.3,
) -> None:
    rag = RAGMode()
    docs, graph_entities = await rag.ahyprid_search(
        queries=[query],
        k=k,
        use_graph=graph,
        max_hops=max_hops,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
        graph_weight=graph_weight,
    )

    if docs:
        table = Table(title=f'搜索结果: "{query}"', title_style="bold")
        table.add_column("score", style="cyan", width=8)
        table.add_column("title", style="green", width=30)
        table.add_column("content", style="white")
        for doc in docs:
            score = f"{doc.query_score:.4f}" if doc.query_score else "N/A"
            name = doc.name or "Untitled"
            content = doc.content[:100].replace("\n", " ") + ("..." if len(doc.content) > 100 else "")
            table.add_row(score, name, content)
        rprint(table)
    else:
        rprint("无搜索结果")

    if graph_entities:
        gtable = Table(title="图谱实体", title_style="bold")
        gtable.add_column("score", style="cyan", width=8)
        gtable.add_column("name", style="green")
        gtable.add_column("type", style="yellow")
        gtable.add_column("uri", style="dim")
        for g in graph_entities:
            gtable.add_row(f"{g.score:.4f}", g.entity_name, g.entity_type, g.entity_uri)
        rprint(gtable)


@ingest_cmd.command("csv")
@runnify
async def ingest_csv(
    data_dir: Annotated[
        Path,
        Option("--data-dir", "-d", help="Data directory for CSV files and reference tables"),
    ] = DEFAULT_DATA_DIR,
    adapter: Annotated[
        str,
        Option("--adapter", "-a", help="Adapter/template: philamuseum, metmuseum, asianart, all"),
    ] = "all",
    do_ingest: Annotated[
        bool,
        Option("--ingest/--no-ingest", help="Also ingest new artifacts into DocumentTable"),
    ] = False,
    use_llm: Annotated[
        bool,
        Option("--llm/--no-llm", help="Enable/disable LLM triple extraction (only with --ingest)"),
    ] = False,
    dedup_threshold: Annotated[
        float,
        Option("--dedup", help="Vector/BM25 dedup threshold (0=disabled, 0.95 recommended)"),
    ] = 0.95,
) -> None:
    data_dir = data_dir.resolve()
    if adapter == "all":
        for adp_cls in [PhilaMuseumAdapter, MetMuseumAdapter, AsianArtAdapter]:
            adp = adp_cls(data_dir=data_dir)
            rows = adp.load_csv()
            if not rows:
                logging.warning(f"适配器 {adp_cls.__name__} 的 CSV 中没有有效数据行")
                continue

            store = ArtifactStore()
            ids = await store.ainsert_artifacts(rows, skip_existing=True)
            logging.info(
                f"适配器 {adp_cls.__name__}: 已导入 {len(ids)} 条新文物记录，跳过 {len(rows) - len(ids)} 条已存在",
            )

            if do_ingest and ids:
                doc_store = DocumentStore()
                doc_ids = await doc_store.alingest_artifacts(
                    artifact_ids=ids,
                    use_llm=use_llm,
                    dedup_threshold=dedup_threshold,
                )
                logging.info(
                    f"适配器 {adp_cls.__name__}: 已提取 {len(doc_ids)} 个文档到 DocumentTable",
                )
        return
    if adapter == "philamuseum":
        adp = PhilaMuseumAdapter(data_dir=data_dir)
    elif adapter == "metmuseum":
        adp = MetMuseumAdapter(data_dir=data_dir)
    elif adapter == "asianart":
        adp = AsianArtAdapter(data_dir=data_dir)
    else:
        logging.error("未知适配器: %s", adapter)
        raise SystemExit(1)

    rows = adp.load_csv()
    if not rows:
        logging.warning("CSV 中没有有效数据行")
        return

    store = ArtifactStore()
    ids = await store.ainsert_artifacts(rows, skip_existing=True)
    logging.info("已导入 %d 条新文物记录，跳过 %d 条已存在", len(ids), len(rows) - len(ids))

    if do_ingest and ids:
        doc_store = DocumentStore()
        doc_ids = await doc_store.alingest_artifacts(
            artifact_ids=ids,
            use_llm=use_llm,
            dedup_threshold=dedup_threshold,
        )
        logging.info("已提取 %d 个文档到 DocumentTable", len(doc_ids))


@ingest_cmd.command("artifacts")
@runnify
async def ingest_artifacts(
    museum: Annotated[str | None, Option("--museum", "-m", help="Filter by museum name")] = None,
    limit: Annotated[int | None, Option("--limit", "-n", help="Max artifacts to ingest")] = None,
    use_llm: Annotated[bool, Option("--llm/--no-llm", help="Enable/disable LLM triple extraction")] = False,
    skip_ingested: Annotated[
        bool,
        Option("--skip-ingested/--no-skip-ingested", help="Skip already ingested artifacts"),
    ] = True,
    dedup_threshold: Annotated[
        float,
        Option("--dedup", help="Vector/BM25 dedup threshold (0=disabled, 0.95 recommended)"),
    ] = 0,
    offset: Annotated[
        int,
        Option("--offset", "-o", help="Skip the first N artifacts before ingesting"),
    ] = 0,
    batch_size: Annotated[
        int,
        Option("--batch-size", "-b", help="Batch size for incremental ingest (0=all at once)"),
    ] = 50,
) -> None:
    store = DocumentStore()
    total_doc_ids: list[UUID] = []
    current_offset = offset

    while True:
        batch_limit = batch_size if batch_size > 0 else limit
        try:
            batch_ids = await store.alingest_artifacts(
                museum=museum,
                limit=batch_limit,
                offset=current_offset,
                use_llm=use_llm,
                skip_ingested=skip_ingested,
                dedup_threshold=dedup_threshold,
            )
        except Exception:
            logging.exception("批次 offset=%d 失败，跳过", current_offset)
            current_offset += max(0, batch_size)
            if batch_size <= 0:
                break
            continue
        if not batch_ids:
            break
        total_doc_ids.extend(batch_ids)
        current_offset += batch_size if batch_size > 0 else len(batch_ids)
        logging.info(
            "批次 offset=%d 完成，提取 %d 个文档，累计 %d",
            current_offset - (batch_size if batch_size > 0 else len(batch_ids)),
            len(batch_ids),
            len(total_doc_ids),
        )
        if batch_size <= 0:
            break

    logging.info("已从 ArtifactStore 提取 %d 个文档到 DocumentTable", len(total_doc_ids))


cmd.add_typer(ingest_cmd, name="ingest")


@cmd.command()
@runnify
async def check_similar(
    content: Annotated[str, Argument(help="Content to check for similarity")],
    threshold: Annotated[float, Option("--threshold", "-t", help="Similarity threshold (0-1)")] = 0.95,
    topn: Annotated[int, Option("--top", "-n", help="Max results")] = 5,
) -> None:
    rag = RAGMode()
    results = await rag.acheck_similar_documents(content=content, threshold=threshold, topn=topn)
    if not results:
        rprint("未找到相似文档")
        return

    table = Table(title=f"相似文档检查 (threshold≥{threshold})", title_style="bold")
    table.add_column("similarity", style="cyan", width=10)
    table.add_column("source", style="green", width=25)
    table.add_column("content", style="white")
    for r in results:
        table.add_row(str(r["similarity"]), str(r["source_name"]), str(r["content_preview"]))
    rprint(table)


def main():
    traceback.install()
    uvloop.install()
    logging.captureWarnings(True)

    logging.basicConfig(
        handlers=[RichHandler(rich_tracebacks=True)],
        level=logging.INFO,
    )
    cmd()


if __name__ == "__main__":
    main()
