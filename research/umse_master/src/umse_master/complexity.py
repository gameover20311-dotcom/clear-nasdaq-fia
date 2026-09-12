from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ComplexityAssessment:
    parameter_count: int
    sample_size: int
    bic_penalty: float
    bits_penalty: float
    adequate_sample_ratio: bool


def assess_complexity(parameter_count: int, sample_size: int, *, minimum_rows_per_parameter: float = 10.0) -> ComplexityAssessment:
    if parameter_count < 0 or sample_size <= 0:
        raise ValueError("parameter_count must be >=0 and sample_size >0")
    bic = parameter_count * math.log(sample_size)
    bits = bic / (2.0 * math.log(2.0))
    ratio_ok = parameter_count == 0 or sample_size / parameter_count >= minimum_rows_per_parameter
    return ComplexityAssessment(parameter_count, sample_size, bic, bits, ratio_ok)
