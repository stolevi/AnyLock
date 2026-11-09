import pytest

from pipeline_lock.adapters.base import PipelineAdapter
from pipeline_lock.adapters.mock import MockAdapter


def test_resource_exists():
    adapter = MockAdapter({"SQ01_SH010", "SQ02_SH010", "SQ03_SH030"})
    assert adapter.resource_exists("SQ01_SH010")

def test_resource_does_not_exist():
    adapter = MockAdapter({"SQ01_SH010", "SQ02_SH020", "SQ03_SH030"})
    assert not adapter.resource_exists("SQ04_SH040")

def test_pipeline_adapter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        PipelineAdapter()

def test_mock_adapter_lists_resources_sorted():
    adapter = MockAdapter({"shots/SQ03_SH030", "shots/SQ01_SH010", "shots/SQ02_SH020"})
    assert adapter.list_resources() == [
        "shots/SQ01_SH010",
        "shots/SQ02_SH020",
        "shots/SQ03_SH030",
    ]

def test_mock_adapter_lists_nothing_when_empty():
    assert MockAdapter(set()).list_resources() == []

def test_adapter_without_list_resources_cannot_be_instantiated():
    class HalfFinishedAdapter(PipelineAdapter):
        def resource_exists(self, resource_path: str) -> bool:
            return False
        # list_resources is missing on purpose

    with pytest.raises(TypeError):
        HalfFinishedAdapter()