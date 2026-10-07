import pytest
from foundation.event_bus.event_bus import EventBus
from foundation.observability.observability_engine import ObservabilityEngine


def test_observability_engine_traces():
    event_bus = EventBus()
    obs = ObservabilityEngine(event_bus=event_bus)

    trc = obs.record_trace("LLMEngine", "generate_tokens", 250.5, "ok")
    assert trc.trace_id == "trc-1"

    traces = obs.get_recent_traces()
    assert len(traces) == 1
    assert traces[0]["component"] == "LLMEngine"
