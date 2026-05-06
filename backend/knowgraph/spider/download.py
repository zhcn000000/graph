import logging

from curl_cffi import AsyncSession
from scrapy.http import Request, Response


class DownloadMiddleware:
    async def process_request(self, request: Request) -> Response:
        async with AsyncSession(
            impersonate="chrome146",
        ) as session:
            response = await session.request(
                method=request.method,  # pyright: ignore
                url=request.url,
                headers=request.headers.to_unicode_dict(),
                data=request.body,
                impersonate="chrome146",
            )
            body = response.content
            if response.status_code != 200:
                logging.error(f"Failed to fetch {request.url} with status {response.status_code},{body.decode()}")
            return Response(
                url=request.url,
                status=response.status_code,
                headers=dict(response.headers),
                body=body,
                request=request,
            )
