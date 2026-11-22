"""Common interface for real publishing platform adapters."""

from abc import ABC, abstractmethod

from app.schemas import Platform, PlatformResult, PostingRequest


class PlatformPublisher(ABC):
    """Adapter contract; implementations must return verified API results."""

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """The platform handled by this adapter."""

    @abstractmethod
    async def publish(self, request: PostingRequest) -> PlatformResult:
        """Publish through the platform API or raise a meaningful error."""

