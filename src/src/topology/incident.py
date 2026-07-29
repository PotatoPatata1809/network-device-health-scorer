"""
What-if (G) + Alert suppression (H) — both are graph walks over the topology.

WHAT-IF (G): "if THIS device fails, what goes with it?" For any device, walk the
tree to its descendants. Planning tool: click any node, see the consequence before
it happens. This is blast_radius() exposed per-device for the console's click-through.

ALERT SUPPRESSION (H): when a parent fails, everything downstream also alarms — a
storm of alerts for ONE root cause. We recognise the parent, suppress the child
alerts, and raise ONE incident naming the root and its blast radius. Turns "14 red
devices" into "1 incident: core-sw-01 failed, 13 downstream affected."

Both read topology.json (built from LLDP) + the per-device alert states. No new
model — pure graph logic on the map we already have.
"""
import json
import networkx as nx


def _tree(topo):
    g = nx.DiGraph()
    for d in topo["devices"]:
        g.add_node(d["id"], **d)
        if d["parent"]:
            g.add_edge(d["parent"], d["id"])
    return g


# ---------------------------------------------------------------- what-if (G) --
def what_if(topo, device):
    """If `device` fails, what goes down? Returns the downstream devices + count.
    (Same walk as blast radius, exposed per-device for interactive click-through.)"""
    g = _tree(topo)
    if device not in g:
        return {"device": device, "impact": 0, "downstream": []}
    desc = sorted(nx.descendants(g, device))
    return {"device": device, "impact": len(desc), "downstream": desc}


# ------------------------------------------------------ alert suppression (H) --
def correlate_alerts(topo, alerting: set, independent_evidence: dict = None):
    """Collapse parent-caused alert storms WITHOUT hiding devices that have their own
    real problem.

    A child alert is only fully SUPPRESSED if (a) an ancestor is also alerting AND
    (b) the child shows no INDEPENDENT evidence of its own fault. `independent_evidence`
    maps device -> truthy signal that the device has its own active anomaly (e.g. its
    own health still degrading, its own driver metric misbehaving — not merely 'went
    dark'). A child WITH independent evidence is kept as a LINKED sub-incident under the
    root, never hidden — so fixing the parent never masks a second real fault.

    Returns: {incidents, suppressed, linked_subincidents, raw_alert_count, incident_count}
    """
    g = _tree(topo)
    alerting = set(alerting)
    ev = independent_evidence or {}

    def alerting_ancestor(node):
        cur = node
        while True:
            preds = list(g.predecessors(cur))
            if not preds:
                return None
            parent = preds[0]
            if parent in alerting:
                return parent
            cur = parent

    roots, suppressed, linked = [], [], []
    for dev in alerting:
        anc = alerting_ancestor(dev)
        if anc is None:
            roots.append(dev)                       # genuine root incident
        elif ev.get(dev):
            linked.append((dev, anc))               # downstream BUT has its own fault -> keep, linked
        else:
            suppressed.append(dev)                  # pure downstream symptom -> safe to suppress

    incidents = []
    for r in sorted(roots):
        desc = set(nx.descendants(g, r)) if r in g else set()
        explained = sorted(desc & alerting)
        sub = sorted([d for d, a in linked if d in desc])   # linked faults under this root
        incidents.append({
            "root": r,
            "type": g.nodes[r].get("type") if r in g else None,
            "explains_n": len(explained),
            "explained_children": explained,
            "blast_radius": len(desc),
            "linked_independent_faults": sub,       # surfaced, NOT hidden
        })

    return {
        "incidents": incidents,
        "suppressed": sorted(suppressed),
        "linked_subincidents": sorted([d for d, a in linked]),
        "raw_alert_count": len(alerting),
        "incident_count": len(incidents),
    }


if __name__ == "__main__":
    topo = json.load(open("topology.json"))

    print("=== WHAT-IF (G) — click any device, see what goes down ===")
    for dev in ["core-sw-01", "dist-sw-01", "acc-sw-01", "srv-mon-01"]:
        r = what_if(topo, dev)
        print(f"  {dev:<12} -> {r['impact']} downstream: {r['downstream'][:5]}{'...' if r['impact']>5 else ''}")

    print("\n=== ALERT SUPPRESSION (H) — parent fails, children storm ===")
    # simulate: core-sw-01 fails, so it + all its descendants alarm at once
    g = _tree(topo)
    storm = {"core-sw-01"} | set(nx.descendants(g, "core-sw-01"))
    print(f"  raw alerts during storm: {len(storm)} devices all red")
    result = correlate_alerts(topo, storm)
    print(f"  -> collapsed to {result['incident_count']} incident(s), "
          f"{len(result['suppressed'])} child alerts suppressed\n")
    for inc in result["incidents"]:
        print(f"  INCIDENT: {inc['root']} ({inc['type']}) failed — "
              f"explains {inc['explains_n']} downstream alerts, blast radius {inc['blast_radius']}")

    print("\n  --- mixed case: two unrelated failures ---")
    mixed = {"acc-sw-01", "srv-mon-01",      # acc-sw-01 + its child server (should collapse to 1)
             "acc-sw-12"}                     # unrelated access switch elsewhere (separate incident)
    r2 = correlate_alerts(topo, mixed)
    print(f"  raw {r2['raw_alert_count']} alerts -> {r2['incident_count']} incidents, "
          f"suppressed {r2['suppressed']}")
    for inc in r2["incidents"]:
        print(f"    INCIDENT: {inc['root']} explains {inc['explains_n']} downstream")
