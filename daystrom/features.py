from dataclasses import dataclass
from datetime import datetime


@dataclass
class FeatureWindow:
    window_start: datetime
    host: str
    app: str

    request_count: int = 0
    error_count: int = 0

    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    llm_generation_count: int = 0
    avg_generation_ms: float = 0.0

    memory_evaluation_count: int = 0
    memory_creation_count: int = 0

    tool_call_count: int = 0
