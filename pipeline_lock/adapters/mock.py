from pipeline_lock.adapters.base import PipelineAdapter


class MockAdapter(PipelineAdapter):
    def __init__(self, known_resources: set[str]):
        self.known_resources = known_resources

    def resource_exists(self, resource_path: str) -> bool:
        return resource_path in self.known_resources
