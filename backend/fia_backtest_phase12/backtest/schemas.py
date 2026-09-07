from dataclasses import dataclass
from typing import Optional


@dataclass
class DashboardMetric:
    name: str
    value: Optional[float] = None
    available: bool = False
    source_phase: Optional[int] = None

    def to_dict(self):
        return {
            "name": self.name,
            "value": self.value,
            "available": self.available,
            "source_phase": self.source_phase,
        }
