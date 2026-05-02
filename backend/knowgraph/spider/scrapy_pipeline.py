from datetime import date

from ..database.artifact import ArtifactStore


class ArtifactPipeline:
    async def process_item(self, item: dict, spider) -> dict:
        store: ArtifactStore | None = getattr(spider, "artifact_store", None)
        if store is None:
            return item

        await store.ainsert_artifact(
            object_id=item.get("object_id", ""),
            title=item.get("title", ""),
            period=item.get("period", ""),
            type=item.get("type", ""),
            material=item.get("material", ""),
            description=item.get("description", ""),
            dimensions=item.get("dimensions", ""),
            museum=item.get("museum", ""),
            location=item.get("location", ""),
            detail_url=item.get("detail_url", ""),
            image_url=item.get("image_url", ""),
            image_path=item.get("image_path", ""),
            credit_line=item.get("credit_line", ""),
            accession_number=item.get("accession_number", ""),
            crawl_date=item.get("crawl_date", date.today()),
        )
        return item
