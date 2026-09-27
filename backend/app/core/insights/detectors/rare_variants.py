"""Seltene Varianten: Fälle, die einen ungewöhnlichen Weg durch den Prozess nehmen.

"Ungewöhnlich" setzt voraus, dass es einen gewöhnlichen Weg gibt. Decken die häufigsten
Varianten nur einen kleinen Teil der Fälle ab (z.B. im Krankenhaus, wo fast jeder Fall
anders verläuft), wird statt eines Alarms ein Hinweis auf den fehlenden Standard gegeben.
"""

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
    top_variants: int = Field(10, ge=1, le=100, description="So viele Varianten bilden den Kern")
    min_standard_coverage: float = Field(
        0.5,
        gt=0,
        le=1,
        description="Decken die häufigsten Varianten weniger ab, gibt es keinen Standardablauf",
    )


class RareVariantsDetector(Detector):
    id = "rare_variants"
    name = "Seltene Varianten"
    category = "deviation"
    required_columns = {CASE, ACTIVITY, TIMESTAMP}
    config_model = RareVariantsConfig

    def detect(self, log: pd.DataFrame, config: RareVariantsConfig) -> list[Insight]:
        per_case = case_variants(log)
        total = len(per_case)
        counts = per_case.value_counts()
        shares = counts / total
        coverage = float(shares.head(config.top_variants).sum())

        if coverage < config.min_standard_coverage:
            return [self._no_standard(per_case, counts, total, coverage, config)]

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
                    f"Die {config.top_variants} häufigsten Abläufe decken {pct(coverage)} der "
                    f"Fälle ab. {len(affected)} von {total} Fällen ({pct(share)}) nehmen "
                    f"dagegen einen von {len(rare)} seltenen Wegen, die jeweils weniger als "
                    f"{pct(config.max_variant_share)} der Fälle ausmachen."
                ),
                severity_rule=(
                    f"hoch ab {pct(config.high_share)} betroffener Fälle, "
                    f"mittel ab {pct(config.medium_share)}, sonst niedrig"
                ),
                metrics={
                    "rare_variant_count": len(rare),
                    "total_variant_count": len(shares),
                    "standard_coverage": coverage,
                },
                evidence={"max_variant_share": config.max_variant_share, "kind": "rare"},
                affected_cases=affected.index,
                total_cases=total,
            )
        ]

    def _no_standard(self, per_case, counts, total, coverage, config) -> Insight:
        # Betroffen sind alle Fälle außerhalb der häufigsten Varianten.
        core = counts.head(config.top_variants).index
        outside = per_case[~per_case.isin(core)]
        return self.make_insight(
            key="no_standard",
            severity="low",
            title="Kein einheitlicher Standardablauf erkennbar",
            summary=(
                f"Die {config.top_variants} häufigsten Abläufe decken nur {pct(coverage)} der "
                f"Fälle ab, insgesamt gibt es {len(counts)} verschiedene Abläufe bei {total} "
                f"Fällen. Einzelne Abweichungen sind hier deshalb nicht aussagekräftig. Das ist "
                f"typisch für Prozesse mit viel Einzelfallentscheidung (z.B. Behandlungen); "
                f"sonst kann es auf fehlende Vorgaben hindeuten."
            ),
            severity_rule=(
                f"immer niedrig: die {config.top_variants} häufigsten Abläufe decken weniger "
                f"als {pct(config.min_standard_coverage)} der Fälle ab"
            ),
            metrics={
                "total_variant_count": len(counts),
                "standard_coverage": coverage,
            },
            evidence={"kind": "no_standard"},
            affected_cases=outside.index,
            total_cases=total,
        )
