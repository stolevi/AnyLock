from pipeline_lock.adapters.base import PipelineAdapter


class MockAdapter(PipelineAdapter):
    def __init__(self, known_resources: set[str]):
        self.known_resources = known_resources

    def resource_exists(self, resource_id: str) -> bool:
        return resource_id in self.known_resources
