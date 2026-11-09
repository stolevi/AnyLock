from abc import ABC, abstractmethod


class PipelineAdapter(ABC):
    @abstractmethod
    def resource_exists(self, resource_path: str) -> bool:
        """Return True if resource_path exists in the pipeline,
        False otherwise."""

    @abstractmethod
    def list_resources(self) -> list[str]:
        """Return the paths of all resources in the pipeline's storage, sorted."""