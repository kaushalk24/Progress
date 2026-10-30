"""Normalized drawing model shared by all CAD extraction backends.

The BOM engine only ever sees these classes, so a DXF export, a LibreDWG
conversion or any future backend can be swapped in without touching the
engineering rules.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

Point = tuple[float, float]


@dataclass
class Insert:
    handle: str
    name: str
    layer: str
    pt: Point
    rotation: float = 0.0
    xscale: float = 1.0
    attribs: dict[str, str] = field(default_factory=dict)

    def attr(self, tag: str, default: str = "") -> str:
        return (self.attribs.get(tag) or default).strip()


@dataclass
class Polyline:
    handle: str
    layer: str
    points: list[Point]
    closed: bool = False
    source: str = "LWPOLYLINE"  # LWPOLYLINE | LINE | PROXY

    def length(self) -> float:
        from ..engine.geometry import polyline_length

        return polyline_length(self.points, self.closed)


@dataclass
class Text:
    handle: str
    layer: str
    text: str
    pt: Point | None
    kind: str = "TEXT"  # TEXT | MTEXT | MLEADER


@dataclass
class Leader:
    handle: str
    layer: str
    points: list[Point]


@dataclass
class Drawing:
    source: str
    backend: str
    inserts: list[Insert] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    leaders: list[Leader] = field(default_factory=list)
    census: Counter = field(default_factory=Counter)  # every entity type seen in model space
    block_census: dict[str, dict[str, int]] = field(default_factory=dict)
    header: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def inserts_named(self, name: str, layer: str | None = None) -> list[Insert]:
        return [i for i in self.inserts if i.name == name and (layer is None or i.layer == layer)]

    def polylines_on(self, layer: str) -> list[Polyline]:
        return [p for p in self.polylines if p.layer == layer]

    def texts_on(self, layer: str) -> list[Text]:
        return [t for t in self.texts if t.layer == layer]
