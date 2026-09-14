from abc import ABC, abstractmethod

class PipelineAdapter(ABC):
    @abstractmethod
    def resource_exists(self, resource_id: str) -> bool:
        """Return True if resource_id exists in the pipeline,
        False otherwise."""
        