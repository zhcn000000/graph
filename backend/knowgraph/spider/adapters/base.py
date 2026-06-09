from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseCrawlerAdapter(ABC):
    museum_name: str
    museum_location: str
    use_streaming: bool = False

    @abstractmethod
    async def search(self) -> list[dict]:
        """Return identifiers; each dict must contain at least 'detail_url'."""

    @abstractmethod
    async def get_detail(self, item: dict) -> dict | None:
        """Fetch artifact detail; return dict for ArtifactStore.ainsert_artifact()."""

    async def astream_items(self) -> AsyncGenerator[dict]:
        """Yield artifact dicts as they are fetched; for streaming adapters."""
        if False:
            yield {}

    async def aclose(self) -> None:
        """Cleanup resources (e.g. browser, HTTP client)."""
        return
