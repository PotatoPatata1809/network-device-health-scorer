"""
build_topology.py — build a directed network map from LLDP neighbour data, and
expose blast radius. Reproducible: run after author_neighbours.py.

Input : neighbours.json (authored LLDP sightings, or a live LLDP/CDP walk of the
        same shape — identical code path).
Output: topology.json (device -> parent/children/site/type/smd_machine).

Direction is COMPUTED here, not in the input. LLDP adjacency is undirected
("A sees B"); real NMS tools orient it into a hierarchy using role hints (core =
root, build downward). That is what orient() does. Links come ONLY from neighbour
records — never from metric correlations.

Public API for the scoring core:
    topo = load_topology("topology.json")
    n, downstream = blast_radius(topo, "core-sw-01")   # -> (13, [...])
"""
import json
import networkx as nx


def load_sightings(path="neighbours.json"):
    data = json.load(open(path))
    devices = {d["sys_name"]: d for d in data["devices"]}
    edges = set()
    for d in data["devices"]:
        for nb in d["lldp_neighbours"]:
            edges.add(frozenset((d["sys_name"], nb["remote_sys_name"])))
    return devices, [tuple(sorted(e)) for e in edges]


def orient(devices, edges):
    """Undirected adjacency -> directed tree via role hints (core = roots)."""
    ug = nx.Graph(edges)
    dg = nx.DiGraph()
    for name, d in devices.items():
        dg.add_node(name, device_type=d["device_type"], site=d["site"],
                    smd_machine=d["smd_machine"])
    roots = [n for n, d in devices.items() if d["device_type"] == "core-switch"]
    visited = set(roots); frontier = list(roots)
    while frontier:
        nxt = []
        for u in frontier:
            for v in ug.neighbors(u):
                if v in visited:
                    continue
                visited.add(v); dg.add_edge(u, v); nxt.append(v)
        frontier = nxt
    for a, b in edges:                       # core-core trunk = peer, not parent/child
        if a in roots and b in roots:
            dg.add_edge(a, b, peer=True); dg.add_edge(b, a, peer=True)
    return dg


def build(neighbours="neighbours.json", out="topology.json"):
    devices, edges = load_sightings(neighbours)
    dg = orient(devices, edges)
    topo = {"_provenance": ("Derived by build_topology.py from neighbours.json (LLDP "
                            "sightings). Direction computed from role hints, not authored."),
            "devices": []}
    for n in sorted(dg.nodes):
        parents = [u for u, v, d in dg.in_edges(n, data=True) if not d.get("peer")]
        children = [v for u, v, d in dg.out_edges(n, data=True) if not d.get("peer")]
        topo["devices"].append({
            "id": n, "type": dg.nodes[n]["device_type"], "site": dg.nodes[n]["site"],
            "smd_machine": dg.nodes[n]["smd_machine"],
            "parent": parents[0] if parents else None, "children": sorted(children)})
    json.dump(topo, open(out, "w"), indent=1)
    return topo


def load_topology(path="topology.json"):
    return json.load(open(path))


def _tree(topo):
    g = nx.DiGraph()
    for d in topo["devices"]:
        g.add_node(d["id"], **d)
        if d["parent"]:
            g.add_edge(d["parent"], d["id"])
    return g


def blast_radius(topo, device):
    """Devices that lose their path if `device` fails = its descendants."""
    g = _tree(topo)
    if device not in g:
        return 0, []
    desc = sorted(nx.descendants(g, device))
    return len(desc), desc


if __name__ == "__main__":
    topo = build()
    print(f"topology.json: {len(topo['devices'])} devices\n")
    print("BLAST RADIUS")
    print(f"{'device':<14}{'type':<15}{'site':<7}{'blast':>6}")
    print("-" * 44)
    rows = [(blast_radius(topo, d["id"])[0], d["id"], d["type"], d["site"])
            for d in topo["devices"]]
    for cnt, dev, typ, site in sorted(rows, reverse=True):
        print(f"{dev:<14}{typ:<15}{site:<7}{cnt:>6}")
