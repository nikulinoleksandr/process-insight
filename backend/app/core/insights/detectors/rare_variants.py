"""Seltene Varianten: Fälle, die einen ungewöhnlichen Weg durch den Prozess nehmen."""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE, TIMESTAMP
from app.core.insights.base import Detector, Insight, pct, severity_by_share
from app.core.process.variants import case_variants


class RareVariantsConfig(BaseModel):
    max_variant_share: float = Field(
        0.01, gt=0, lt=1, description="Varianten unter diesem Anteil gelten als selten"
    )
    min_case_share: float = Field(0.02, ge=0, le=1, description="Erst ab diesem Anteil melden")
    high_share: float = Field(0.20, ge=0, le=1)
    medium_share: float = Field(0.05, ge=0, le=1)


class RareVariantsDetector(Detector):
    id = "rare_variants"
    name = "Seltene Varianten"
    category = "deviation"
    required_columns = {CASE, ACTIVITY, TIMESTAMP}
    config_model = RareVariantsConfig

    def detect(self, log: pd.DataFrame, config: RareVariantsConfig) -> list[Insight]:
        per_case = case_variants(log)
        total = len(per_case)
        shares = per_case.value_counts() / total
        rare = shares[shares < config.max_variant_share]
        affected = per_case[per_case.isin(rare.index)]
        share = len(affected) / total
        if affected.empty or share < config.min_case_share:
            return []

        return [
            self.make_insight(
                key="rare",
                severity=severity_by_share(share, config.high_share, config.medium_share),
                title="Viele Fälle weichen vom Standardablauf ab",
                summary=(
                    f"{len(affected)} von {total} Fällen ({pct(share)}) folgen einer von "
                    f"{len(rare)} seltenen Varianten, die jeweils weniger als "
                    f"{pct(config.max_variant_share)} der Fälle ausmachen."
                ),
                severity_rule=(
                    f"hoch ab {pct(config.high_share)} betroffener Fälle, "
                    f"mittel ab {pct(config.medium_share)}, sonst niedrig"
                ),
                metrics={
                    "rare_variant_count": len(rare),
                    "total_variant_count": len(shares),
                },
                evidence={"max_variant_share": config.max_variant_share},
                affected_cases=affected.index,
                total_cases=total,
            )
        ]
