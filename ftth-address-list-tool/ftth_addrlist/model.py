"""Data model shared by the parsers, the tracer and the writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIRMED = "CONFIRMED"
PROVISIONAL = "PROVISIONAL"
UNRESOLVED = "UNRESOLVED"
APPROVED = "APPROVED"  # value supplied or accepted through the overrides file

STATUS_RANK = {CONFIRMED: 0, APPROVED: 1, PROVISIONAL: 2, UNRESOLVED: 3}


def worst(statuses) -> str:
    statuses = list(statuses) or [CONFIRMED]
    return max(statuses, key=lambda s: STATUS_RANK[s])


@dataclass(frozen=True)
class SourceRef:
    file: str
    row: int | None = None

    def __str__(self) -> str:
        return f"{self.file}" + (f" row {self.row}" if self.row else "")


@dataclass(frozen=True)
class Location:
    """An enclosure named in a splice report, e.g. 'Splice Case: ABC-00001G'."""
    kind: str
    name: str

    @classmethod
    def parse(cls, text) -> "Location | None":
        if text is None:
            return None
        text = " ".join(str(text).split())
        if not text:
            return None
        if ": " in text:
            kind, name = text.split(": ", 1)
        elif text.endswith(":"):
            kind, name = text[:-1], ""
        else:
            kind, name = "", text
        return cls(kind.strip(), name.strip())

    def __str__(self) -> str:
        return f"{self.kind}: {self.name}" if self.kind else self.name


@dataclass(frozen=True)
class CableFiber:
    cable: str
    seg: int
    fiber: int
    tube: int | None = None
    tube_fiber: int | None = None

    @property
    def key(self):
        return ("C", self.cable, self.seg, self.fiber)

    def __str__(self) -> str:
        return f"{self.cable}: Seg{self.seg} f{self.fiber}"


@dataclass(frozen=True)
class DevicePort:
    device: str
    port: int

    @property
    def key(self):
        return ("D", self.device, self.port)

    def __str__(self) -> str:
        return f"{self.device} port {self.port}"


@dataclass
class Side:
    endpoint: CableFiber | DevicePort
    tube_color: str | None = None   # report colour name, lower case (e.g. "blue")
    fiber_color: str | None = None


@dataclass
class Connection:
    closure: str
    a: Side
    b: Side
    usage: str | None
    state: str | None
    owner: str | None
    circuit_start: Location | None
    circuit_end: Location | None
    direction: str | None
    source: SourceRef
    fmt: str  # "connections_report" | "splice_guide"
    notes: list[str] = field(default_factory=list)

    def side_for(self, key) -> Side | None:
        if self.a.endpoint.key == key:
            return self.a
        if self.b.endpoint.key == key:
            return self.b
        return None

    def other(self, key) -> Side | None:
        if self.a.endpoint.key == key:
            return self.b
        if self.b.endpoint.key == key:
            return self.a
        return None


@dataclass
class SegmentInfo:
    cable: str
    seg: int
    count: int | None
    start: Location | None
    end: Location | None
    placement: str | None
    source: SourceRef


@dataclass
class DeviceInfo:
    device_id: str
    label: str
    count: int | None
    ratio: int | None
    index: int | None
    source: SourceRef


@dataclass
class Issue:
    severity: str          # ERROR | WARNING | INFO
    code: str
    message: str
    olm: str | None = None
    cable: str | None = None
    fiber: int | None = None
    source: str | None = None


@dataclass
class SpliceReport:
    path: Path
    fmt: str
    closure: str
    header: dict[str, Any]
    segments: list[SegmentInfo] = field(default_factory=list)
    devices: list[DeviceInfo] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass
class FieldValue:
    value: Any
    status: str = CONFIRMED
    rule: str = ""                 # human-readable derivation
    evidence: list[str] = field(default_factory=list)
    note: str = ""
    code: str = ""                 # rule code, see docs/FIELD_MAPPING.md


@dataclass
class OutputRow:
    olm: str
    section: int
    cable: str
    fiber: int
    fields: dict[str, FieldValue]
    kind: str = ""                  # subscriber | spare | transport | splitter_common | power | other
    trace: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    needs_reports: list[str] = field(default_factory=list)   # closure reports that would confirm this row
    route: list[str] = field(default_factory=list)           # closures the fibre trace passed, in order
    trace_end: dict | None = None                            # where/how the fibre trace stopped

    @property
    def status(self) -> str:
        return worst(f.status for f in self.fields.values())

    def value(self, key):
        fv = self.fields.get(key)
        return fv.value if fv else None
