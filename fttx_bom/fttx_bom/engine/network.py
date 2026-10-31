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
    # labelled boundaries of networks that are in the drawing but not in this job (combined drawings run per OLM)
    foreign: dict[str, Region] = field(default_factory=dict)
    foreign_assigned: list[tuple[str, str]] = field(default_factory=list)
    job: list[str] = field(default_factory=list)  # network names of this job (some may lack a boundary)

    def in_job(self, net: str) -> bool:
        return net in self.networks or net in self.job

    def resolve(self, p: Point, strict: bool = False) -> tuple[str | None, str, float]:
        """(network, how, distance ft) without recording anything. how: inside | single | transport |
        nearest | outside. The network may be a foreign one (not in this job)."""
        if self.single_network and not self.networks and not self.foreign:
            return self.single_network, "single", 0.0
        hits = [n for n, r in self.networks.items() if r.contains(p)]
        if len(hits) > 1:
            # overlapping boundaries: choose the smallest containing polygon
            hits = [min(hits, key=lambda n: area(self.networks[n].poly))]
        if hits:
            return hits[0], "inside", 0.0
        fh = [n for n, r in self.foreign.items() if r.contains(p)]
        if fh:
            return min(fh, key=lambda n: area(self.foreign[n].poly)), "inside", 0.0
        regions = {**self.foreign, **self.networks}
        if not regions or strict:
            return None, "outside", 0.0
        best = min(regions, key=lambda n: regions[n].distance(p))
        d = regions[best].distance(p)
        if any(t.contains(p) for t in self.transport):
            net = self.transport_network or best
            r = regions.get(net)
            return net, "transport", round(r.distance(p), 1) if r else 0.0
        if d <= self.tolerance:
            return best, "nearest", round(d, 1)
        return None, "outside", round(d, 1)

    def network_of(self, p: Point, what: str = "", strict: bool = False) -> str | None:
        """Job network containing p. Unless strict:
        * objects inside a transport-corridor boundary belong to the network the
          corridor feeds (far end of the OTN transport cable) - the NMK reference books
          the OTN transport cable and its vault to NMK-R04 this way;
        * other objects within `tolerance` ft of a boundary go to the nearest network.
        Objects of a network that is in the drawing but not in this job return None and are
        recorded in `foreign_assigned` (not counted, not reported as unassigned)."""
        net, how, d = self.resolve(p, strict)
        if net is None:
            if self.networks or self.foreign:
                self.unassigned.append((what, p))
            return None
        if not self.in_job(net) and how != "single":
            self.foreign_assigned.append((what + (" [transport corridor]" if how == "transport" else ""), net))
            return None
        if how == "transport":
            self.nearest_assigned.append((what + " [transport corridor]", net, d))
        elif how == "nearest":
            self.nearest_assigned.append((what, net, d))
        return net

    def foreign_of(self, p: Point, strict: bool = False) -> str | None:
        """The other network p belongs to, when it is in the drawing but not in this job."""
        net, how, _d = self.resolve(p, strict)
        return net if net is not None and not self.in_job(net) and how != "single" else None

    def area_of(self, p: Point) -> str:
        return NONGRANT if any(r.contains(p) for r in self.nongrant) else GRANT


def _poly_label(region_poly: Region, labels: list[tuple[str, Point]]) -> list[str]:
    return [t for t, p in labels if p is not None and region_poly.contains(p)]


DEFAULT_LABEL_RE = r"\b([A-Z]{2,5}-R\d{2})\b"


def build_classifier(d: Drawing, conv: dict, network_names: list[str]) -> Classifier:
    names_upper = {n.upper(): n for n in network_names}
    label_re = re.compile(conv.get("network_label_regex", DEFAULT_LABEL_RE))

    labels: list[tuple[str, Point]] = []
    for t in d.texts:
        if t.layer in conv["network_label_layers"] and t.pt is not None:
            labels.append((t.text.strip(), t.pt))

    regions: dict[str, Region] = {}  # every labelled network boundary in the drawing, job or not
    notes: list[str] = []
    unlabelled: list = []
    for pl in d.polylines:
        if pl.layer not in conv["network_boundary_layers"] or len(pl.points) < 3:
            continue
        reg = Region("", pl.handle, pl.points)
        found = set()
        for txt in _poly_label(reg, labels):
            for m in label_re.findall(txt.upper()):
                found.add(names_upper.get(m, m))
        if len(found) == 1:
            name = found.pop()
            if name in regions:
                # keep the larger polygon, note the duplicate
                if area(pl.points) > area(regions[name].poly):
                    regions[name] = Region(name, pl.handle, pl.points)
                notes.append(f"multiple boundary polygons labelled {name}; largest kept")
            else:
                regions[name] = Region(name, pl.handle, pl.points)
        elif len(found) > 1:
            notes.append(f"boundary {pl.handle} on {pl.layer} contains several network labels {sorted(found)}; ignored")
        else:
            unlabelled.append(pl)
    networks = {n: r for n, r in regions.items() if n in network_names}
    foreign = {n: r for n, r in regions.items() if n not in network_names}
    single = network_names[0] if len(network_names) == 1 else None
    missing = [n for n in network_names if n not in networks]
    if single and missing and not regions:
        if len(unlabelled) == 1:
            pl = unlabelled[0]
            networks[single] = Region(single, pl.handle, pl.points)
            notes.append(f"boundary fallback: the only boundary polygon ({pl.handle}) has no network label; used for {single}")
        elif not unlabelled:
            notes.append(f"boundary fallback: the drawing has no network boundary polygons; every object is counted for {single}")
        else:
            single = None
            notes.append(f"no DWG boundary polygon found for networks {missing} ({len(unlabelled)} boundary polygons carry no "
                         f"recognised label - expected text matching {label_re.pattern} on {conv['network_label_layers']})")
    elif missing:
        single = None
        notes.append(f"no DWG boundary polygon found for networks {missing}"
                     + (f" (labelled boundaries found: {sorted(regions)})" if regions else ""))
    if foreign:
        notes.append(f"boundaries of other networks in the drawing, excluded from this job: {sorted(foreign)}")

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
    known = {n.upper(): n for n in list(regions) + list(network_names)}
    for ins in d.inserts:
        seg = ins.attr("SEGNUM").upper()
        if ins.name in label_names and "OTN" in seg and " TO " in seg:
            b_end = seg.split(" TO ", 1)[1].rsplit(" FC", 1)[0].strip()
            m = re.match(conv.get("splice_name_regex", r"^([A-Z]+)-(\d{2})\d{3}[A-Z]?$"), b_end)
            cand = f"{m.group(1)}-R{m.group(2)}" if m else None
            if cand:
                # the far-end network by the splice naming, even when its boundary is not in the drawing
                tnet = known.get(cand.upper(), cand)
                notes.append(f"transport corridor assigned to {tnet} (transport cable {seg})"
                             + ("" if tnet in network_names else " - not in this job, corridor excluded"))
    return Classifier(networks, ng, conv["network_assign_tolerance_ft"], single, notes, transport=transport,
                      transport_network=tnet, foreign=foreign, job=list(network_names))
