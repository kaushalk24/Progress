"""Fibre colour code helpers (TIA-598 position <-> colour)."""

from __future__ import annotations


class ColorCode:
    def __init__(self, cfg: dict):
        c = cfg["colors"]
        self.sequence = [s.lower() for s in c["sequence"]]
        self.abbr = {k.lower(): v for k, v in c["abbreviations"].items()}
        self.from_abbr = {v.upper(): k for k, v in self.abbr.items()}
        self.per_tube = int(c.get("fibers_per_tube", 12))

    def name_at(self, position: int) -> str:
        return self.sequence[(position - 1) % len(self.sequence)]

    def expected(self, fiber_no: int) -> tuple[str, str]:
        """(tube colour, fibre colour) expected for an absolute fibre number."""
        tube = (fiber_no - 1) // self.per_tube + 1
        pos = (fiber_no - 1) % self.per_tube + 1
        return self.name_at(tube), self.name_at(pos)

    def to_abbr(self, name: str | None) -> str | None:
        if not name:
            return None
        return self.abbr.get(str(name).strip().lower())

    def normalise(self, text: str | None) -> str | None:
        """Accept a colour name or abbreviation; return the colour name."""
        if not text:
            return None
        t = str(text).strip()
        if t.lower() in self.abbr:
            return t.lower()
        return self.from_abbr.get(t.upper())

    def fiber_number(self, tube_color: str, fiber_color: str) -> int | None:
        t = self.normalise(tube_color)
        f = self.normalise(fiber_color)
        if t is None or f is None:
            return None
        return self.sequence.index(t) * self.per_tube + self.sequence.index(f) + 1
