"""Network (OLM service area) and Grant / Non-Grant classification.

* Network boundaries: closed polylines on the configured boundary layers,
  named by a network label (e.g. "NMK-R02" site text or "DMI-R15 15f")
  lying inside them. Objects just outside every boundary are assigned to the
  nearest boundary within a tolerance and reported.
* Non-Grant areas: every polygon on the "Boundary - Designed Not Built" layer
  (Map/SpatialNet proxy LWPolygons or LWPOLYLINEs) except polygons labelled as
  network/transport boundaries. Everything else inside a network is Grant.
  Verified against the NMK reference: grant/non-grant splits of commercial and
  MDU passings reproduce exactly with this definition.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..extract.model import Drawing, Point
from .geometry import Region, area

GRANT, NONGRANT = "G", "NG"
AREAS = (GRANT, NONGRANT)


@dataclass
class Classifier:
    networks: dict[str, Region]
    nongrant: list[Region]
    tolerance: float
    single_network: str | None = None
    notes: list[str] = field(default_factory=list)
    unassigned: list[tuple[str, Point]] = field(default_factory=list)
    nearest_assigned: list[tuple[str, str, float]] = field(default_factory=list)
    transport: list[Region] = field(default_factory=list)
    transport_network: str | None = None

    def network_of(self, p: Point, what: str = "", strict: bool = False) -> str | None:
        """Network containing p. Unless strict:
        * objects inside a transport-corridor boundary belong to the network the
          corridor feeds (nearest network boundary) - the NMK reference books the
          OTN transport cable and its vault to NMK-R04 this way;
        * other objects within `tolerance` ft of a boundary go to the nearest network."""
        if self.single_network and not self.networks:
            return self.single_network
        hits = [n for n, r in self.networks.items() if r.contains(p)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            # overlapping boundaries: choose the smallest containing polygon
            return min(hits, key=lambda n: area(self.networks[n].poly))
        if not self.networks:
            return None
        if strict:
            self.unassigned.append((what, p))
            return None
        best = min(self.networks, key=lambda n: self.networks[n].distance(p))
        d = self.networks[best].distance(p)
        if any(t.contains(p) for t in self.transport):
            net = self.transport_network or best
            self.nearest_assigned.append((what + " [transport corridor]", net, round(self.networks[net].distance(p), 1)))
            return net
        if d <= self.tolerance:
            self.nearest_assigned.append((what, best, round(d, 1)))
            return best
        self.unassigned.append((what, p))
        return None

    def area_of(self, p: Point) -> str:
        return NONGRANT if any(r.contains(p) for r in self.nongrant) else GRANT


def _poly_label(region_poly: Region, labels: list[tuple[str, Point]]) -> list[str]:
    return [t for t, p in labels if p is not None and region_poly.contains(p)]


def build_classifier(d: Drawing, conv: dict, network_names: list[str]) -> Classifier:
    names_upper = {n.upper(): n for n in network_names}
    label_re = re.compile(r"\b([A-Z]{2,5}-R\d{2})\b")

    labels: list[tuple[str, Point]] = []
    for t in d.texts:
        if t.layer in conv["network_label_layers"] and t.pt is not None:
            labels.append((t.text.strip(), t.pt))

    networks: dict[str, Region] = {}
    notes: list[str] = []
    for pl in d.polylines:
        if pl.layer not in conv["network_boundary_layers"] or len(pl.points) < 3:
            continue
        reg = Region("", pl.handle, pl.points)
        found = set()
        for txt in _poly_label(reg, labels):
            for m in label_re.findall(txt.upper()):
                if m in names_upper:
                    found.add(names_upper[m])
        if len(found) == 1:
            name = found.pop()
            if name in networks:
                # keep the larger polygon, note the duplicate
                if area(pl.points) > area(networks[name].poly):
                    networks[name] = Region(name, pl.handle, pl.points)
                notes.append(f"multiple boundary polygons labelled {name}; largest kept")
            else:
                networks[name] = Region(name, pl.handle, pl.points)
        elif len(found) > 1:
            notes.append(f"boundary {pl.handle} on {pl.layer} contains several network labels {sorted(found)}; ignored")
    single = network_names[0] if len(network_names) == 1 else None
    missing = [n for n in network_names if n not in networks]
    if missing and not single:
        notes.append(f"no DWG boundary polygon found for networks {missing}")

    ex = re.compile(conv["nongrant_exclude_label_regex"], re.I)
    ng: list[Region] = []
    for pl in d.polylines:
        if pl.layer != conv["nongrant_layer"] or len(pl.points) < 3:
            continue
        reg = Region("NG", pl.handle, pl.points)
        lbl = _poly_label(reg, labels)
        if any(ex.search(x) for x in lbl):
            notes.append(f"polygon {pl.handle} labelled {lbl} treated as boundary, not Non-Grant")
            continue
        reg.name = "; ".join(lbl) or "NG (unlabelled)"
        ng.append(reg)
    transport = [Region("transport", pl.handle, pl.points) for pl in d.polylines
                 if pl.layer in conv.get("transport_boundary_layers", []) and len(pl.points) >= 3]
    # the corridor feeds the network at the far end of the OTN transport cable
    tnet = None
    label_names = set(conv["blocks"]["cable_label"]["names"])
    for ins in d.inserts:
        seg = ins.attr("SEGNUM").upper()
        if ins.name in label_names and "OTN" in seg and " TO " in seg:
            b_end = seg.split(" TO ", 1)[1].rsplit(" FC", 1)[0].strip()
            m = re.match(r"^([A-Z]+)-(\d{2})\d{3}[A-Z]?$", b_end)
            cand = f"{m.group(1)}-R{m.group(2)}" if m else None
            if cand and cand.upper() in names_upper:
                tnet = names_upper[cand.upper()]
                notes.append(f"transport corridor assigned to {tnet} (transport cable {seg})")
    return Classifier(networks, ng, conv["network_assign_tolerance_ft"], single, notes, transport=transport,
                      transport_network=tnet)
