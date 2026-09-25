"""Liste aller Detektoren. Ein neuer Detektor muss nur hier eingetragen werden."""

from app.core.insights.base import Detector
from app.core.insights.detectors.bottleneck import BottleneckDetector
from app.core.insights.detectors.rare_variants import RareVariantsDetector
from app.core.insights.detectors.rework import ReworkDetector
from app.core.insights.detectors.segregation_of_duties import SegregationOfDutiesDetector
from app.core.insights.detectors.sla import SlaDetector

DETECTORS: list[Detector] = [
    ReworkDetector(),
    BottleneckDetector(),
    SlaDetector(),
    SegregationOfDutiesDetector(),
    RareVariantsDetector(),
]


def get_detector(detector_id: str) -> Detector:
    for detector in DETECTORS:
        if detector.id == detector_id:
            return detector
    raise KeyError(detector_id)
