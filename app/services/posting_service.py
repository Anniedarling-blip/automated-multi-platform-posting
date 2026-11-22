"""Coordinate post requests across configured platform adapters."""

from collections.abc import Mapping, Sequence

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest, PostingResponse


class PostingService:
    """Dispatch posts to adapters and return only actual confirmed results."""

    def __init__(
        self,
        target_platforms: Sequence[Platform],
        publishers: Mapping[Platform, PlatformPublisher] | None = None,
    ) -> None:
        self._target_platforms = tuple(target_platforms)
        self._publishers = dict(publishers or {})

    async def publish(self, request: PostingRequest) -> PostingResponse:
        results = []
        for platform in self._target_platforms:
            publisher = self._publishers.get(platform)
            if publisher is None:
                results.append(
                    self._failure(platform, "Publishing is not configured.")
                )
                continue

            try:
                result = await publisher.publish(request)
                if result.platform != platform:
                    results.append(
                        self._failure(
                            platform,
                            "Publisher returned a result for the wrong platform.",
                        )
                    )
                else:
                    results.append(result)
            except Exception:
                # Isolate adapter errors so one platform cannot block the rest.
                results.append(
                    self._failure(platform, "Platform publisher failed unexpectedly.")
                )

        return PostingResponse(results=results)

    @staticmethod
    def _failure(platform: Platform, error: str) -> PlatformResult:
        return PlatformResult(
            platform=platform,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )

