"""Classify raw count differences into named, actionable defect patterns.

A count delta on its own ("6 headings became 5") is not a finding — it could be
a tool defect or an editorial change the author made while publishing. These
detectors promote a delta to a named pattern only when the specific evidence
for that pattern is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .structure import Structure


@dataclass
class Pattern:
    """A named, explained defect pattern with a suggested owner requirement."""

    key: str
    title: str
    requirement: str
    detail: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def detect(
    pipeline: Structure, published: Structure, published_title: str
) -> list[Pattern]:
    """Return every pattern whose evidence is present for this article."""
    patterns: list[Pattern] = []

    placeholders = [c for c in pipeline.comments if "TABLE" in c.upper()]
    if placeholders:
        patterns.append(
            Pattern(
                key="table_placeholder_leaked",
                title="Table placeholder comment reached the composer",
                requirement="TBL-01",
                detail=(
                    f"Pipeline output contains {len(placeholders)} table placeholder "
                    f"comment(s) and {pipeline.tables} rendered table(s). The published "
                    f"post has {published.tables} table(s). Example: "
                    f"`{placeholders[0][:80]}`"
                ),
            )
        )

    if pipeline.headings and published_title:
        first_level, first_text = pipeline.headings[0]
        if first_level == 1 and _normalize(first_text) == _normalize(published_title):
            patterns.append(
                Pattern(
                    key="duplicate_title_h1",
                    title="Leading H1 duplicates the post title",
                    requirement="FMT-02",
                    detail=(
                        f"Pipeline output opens with `<h1>{first_text}</h1>`, which "
                        "matches the Substack post title. Substack renders its own "
                        "title above the body, so this pastes as a duplicate heading "
                        "the author must delete by hand."
                    ),
                )
            )

    pipeline_images = len(pipeline.images)
    published_images = len(published.images)
    if pipeline_images and published_images < pipeline_images:
        patterns.append(
            Pattern(
                key="images_lost",
                title="Fewer images published than the pipeline emitted",
                requirement="DIAG-01",
                detail=(
                    f"Pipeline emitted {pipeline_images} image(s); published post has "
                    f"{published_images}. Needs a live paste to confirm whether the "
                    "paste dropped them or the author removed them editorially."
                ),
            )
        )
    elif published_images > pipeline_images:
        patterns.append(
            Pattern(
                key="images_hand_added",
                title="Published post has images the pipeline never emitted",
                requirement="DIAG-01",
                detail=(
                    f"Pipeline emitted {pipeline_images} image(s); published post has "
                    f"{published_images}. The extra image(s) were added by hand in the "
                    "composer — the usual cause is a table redrawn as a diagram."
                ),
            )
        )

    return patterns
