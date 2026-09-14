import pytest
from pipeline_lock.adapters.mock import MockAdapter
from pipeline_lock.adapters.base import PipelineAdapter

def test_resource_exists():
    adapter = MockAdapter({"SQ01_SH010", "SQ02_SH010", "SQ03_SH030"})
    assert adapter.resource_exists("SQ01_SH010")

def test_resource_does_not_exist():
    adapter = MockAdapter({"SQ01_SH010", "SQ02_SH020", "SQ03_SH030"})
    assert not adapter.resource_exists("SQ04_SH040")

def test_pipeline_adapter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        PipelineAdapter()