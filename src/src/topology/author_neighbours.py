"""
Author LLDP neighbour data for the 28 SMD devices  ->  neighbours.json

SMD ships NO connectivity data. A real network exposes neighbours via LLDP
(SNMP lldpRemTable). Since SMD has none, we AUTHOR neighbour tables in the EXACT
shape a live LLDP walk returns — so swapping in a real SNMP poller needs no
downstream change. Sightings are UNDIRECTED (A sees B and B sees A, as real LLDP
reports); parent/child DIRECTION is computed later by build_topology.py, never
authored here. The map is derived only from neighbour records — never from metrics.
"""
import json, hashlib

# 28 SMD machines -> device roles, 2-site enterprise network
ASSIGN = {
    "machine-1-1": ("core-sw-01","core-switch","DC-A"),
    "machine-1-2": ("dist-sw-01","dist-switch","DC-A"),
    "machine-1-3": ("dist-sw-02","dist-switch","DC-A"),
    "machine-1-4": ("fw-01","firewall","DC-A"),
    "machine-1-5": ("rtr-edge-01","router","DC-A"),
    "machine-1-6": ("acc-sw-01","access-switch","DC-A"),
    "machine-1-7": ("acc-sw-02","access-switch","DC-A"),
    "machine-1-8": ("acc-sw-03","access-switch","DC-A"),
    "machine-2-1": ("acc-sw-04","access-switch","DC-A"),
    "machine-2-2": ("acc-sw-05","access-switch","DC-A"),
    "machine-2-3": ("acc-sw-06","access-switch","DC-A"),
    "machine-2-4": ("ap-ctrl-01","wlc","DC-A"),
    "machine-2-5": ("srv-mon-01","server","DC-A"),
    "machine-2-6": ("srv-app-01","server","DC-A"),
    "machine-2-7": ("core-sw-02","core-switch","DC-B"),
    "machine-2-8": ("dist-sw-03","dist-switch","DC-B"),
    "machine-2-9": ("dist-sw-04","dist-switch","DC-B"),
    "machine-3-1": ("fw-02","firewall","DC-B"),
    "machine-3-2": ("rtr-edge-02","router","DC-B"),
    "machine-3-3": ("acc-sw-07","access-switch","DC-B"),
    "machine-3-4": ("acc-sw-08","access-switch","DC-B"),
    "machine-3-5": ("acc-sw-09","access-switch","DC-B"),
    "machine-3-6": ("acc-sw-10","access-switch","DC-B"),
    "machine-3-7": ("acc-sw-11","access-switch","DC-B"),
    "machine-3-8": ("acc-sw-12","access-switch","DC-B"),
    "machine-3-9": ("acc-sw-13","access-switch","DC-B"),
    "machine-3-10":("srv-log-01","server","DC-B"),
    "machine-3-11":("srv-db-01","server","DC-B"),
}
# physical cabling (undirected). DC-A slightly larger so core-sw-01 -> 13 downstream.
LINKS = [
    ("core-sw-01","core-sw-02"),
    ("core-sw-01","dist-sw-01"),("core-sw-01","dist-sw-02"),
    ("core-sw-01","fw-01"),("core-sw-01","rtr-edge-01"),
    ("dist-sw-01","acc-sw-01"),("dist-sw-01","acc-sw-02"),("dist-sw-01","acc-sw-03"),
    ("dist-sw-02","acc-sw-04"),("dist-sw-02","acc-sw-05"),("dist-sw-02","acc-sw-06"),
    ("dist-sw-02","ap-ctrl-01"),
    ("acc-sw-01","srv-mon-01"),("acc-sw-02","srv-app-01"),
    ("core-sw-02","dist-sw-03"),("core-sw-02","dist-sw-04"),
    ("core-sw-02","fw-02"),("core-sw-02","rtr-edge-02"),
    ("dist-sw-03","acc-sw-07"),("dist-sw-03","acc-sw-08"),("dist-sw-03","acc-sw-09"),
    ("dist-sw-04","acc-sw-10"),("dist-sw-04","acc-sw-11"),("dist-sw-04","acc-sw-12"),
    ("dist-sw-04","acc-sw-13"),
    ("acc-sw-07","srv-log-01"),("acc-sw-13","srv-db-01"),
]
CAPS = {"core-switch":"Bridge","dist-switch":"Bridge","access-switch":"Bridge",
        "router":"Router","firewall":"Router","wlc":"Bridge","server":"Station"}

def mac(h):
    x = hashlib.md5(h.encode()).hexdigest()
    return "00:1b:" + ":".join(x[i:i+2] for i in range(0,8,2))

by_host = {v[0]:(k,v[1],v[2]) for k,v in ASSIGN.items()}
port = {h:0 for h in by_host}
def nextport(h):
    port[h]+=1; return f"GigabitEthernet1/0/{port[h]}"

rec = {h:[] for h in by_host}
for a,b in LINKS:
    pa,pb = nextport(a),nextport(b)
    rec[a].append({"local_port":pa,"remote_sys_name":b,"remote_port":pb,
                   "remote_chassis_id":mac(b),"capabilities":CAPS[by_host[b][1]]})
    rec[b].append({"local_port":pb,"remote_sys_name":a,"remote_port":pa,
                   "remote_chassis_id":mac(a),"capabilities":CAPS[by_host[a][1]]})

out = {"_provenance":("AUTHORED LLDP neighbour data (lldpRemTable shape). SMD ships no "
        "connectivity, so sightings are hand-authored, NOT discovered. A live LLDP/CDP "
        "SNMP walk of this same shape swaps in with no downstream change. Sightings are "
        "undirected; direction is computed by build_topology.py."),
       "devices":[{"sys_name":h,"device_type":by_host[h][1],"site":by_host[h][2],
                   "chassis_id":mac(h),"smd_machine":by_host[h][0],"lldp_neighbours":rec[h]}
                  for h in sorted(by_host)]}
with open("neighbours.json","w") as f: json.dump(out,f,indent=1)
n = sum(len(d["lldp_neighbours"]) for d in out["devices"])
print(f"neighbours.json: {len(out['devices'])} devices, {len(LINKS)} links, {n} sightings")
