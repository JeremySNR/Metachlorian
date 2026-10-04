"""Record rights on the demo library from each clip's actual licence (eval/media/SOURCES.md).

CC0 / CC BY footage: cleared for commercial and editorial use on all channels worldwide, with attribution for CC BY.
Netflix Chimera/El Fuente (conflicting notices): restricted, local evaluation only. Pexels licence: cleared, no
model releases recorded (so commercial use with people visible comes back 'restricted'). One CC BY set gets an
expiry within 30 days to exercise the 'expiring' state. Copyrighted test clips (goldeneye trailer) are not cleared.
usage: python seed_rights.py http://127.0.0.1:8770 [token]
"""
import datetime as dt
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
headers = {"Content-Type": "application/json", "X-Metachlorian": "1"}
if len(sys.argv) > 2:
    headers["Authorization"] = f"Bearer {sys.argv[2]}"


def call(method, path, body=None):
    req = urllib.request.Request(base + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    return json.load(urllib.request.urlopen(req))


assets = call("GET", "/api/assets?limit=500")["assets"]
soon = (dt.date.today() + dt.timedelta(days=21)).isoformat()
counts = {}
for a in assets:
    f = a["filename"]
    if f.startswith(("shotstack_", "mdn_")):
        r = {"status": "cleared", "source": "Open test media", "owner": "Shotstack / MDN contributors", "licence": "CC0-1.0",
             "permitted_uses": ["commercial", "editorial", "marketing", "advertising", "internal"], "channels": [], "territories": ["WW"],
             "model_release": "not_applicable" if "scott" not in f else "unlimited", "property_release": "not_applicable"}
    elif f.startswith(("ugc_", "cremad_")) or f in ("classroom.mp4", "people-detection.mp4", "store-aisle-detection.mp4",
                                                     "person-bicycle-car-detection.mp4", "head-pose-face-detection-female-and-male.mp4"):
        r = {"status": "cleared", "source": "Open dataset", "licence": "CC-BY-4.0" if not f.startswith("cremad") else "ODbL-1.0",
             "permitted_uses": ["commercial", "editorial", "marketing", "internal", "educational"], "channels": [], "territories": ["WW"],
             "model_release": "unknown", "attribution": "YouTube UGC dataset (Google), CC BY" if f.startswith("ugc_") else "Intel IoT sample videos, CC BY 4.0"}
        if f.startswith("ugc_Sports"):
            r["expires"] = soon
    elif f.startswith(("tears_of_steel", "tos_")):
        r = {"status": "cleared", "source": "Blender Foundation", "licence": "CC-BY-3.0", "permitted_uses": ["commercial", "editorial", "marketing"],
             "channels": [], "territories": ["WW"], "attribution": "(CC) Blender Foundation | mango.blender.org", "model_release": "unlimited"}
    elif f.startswith("netflix_meridian") or f.startswith("netflix_sparks"):
        r = {"status": "cleared", "source": "Netflix Open Content", "licence": "CC-BY-4.0", "permitted_uses": ["editorial", "educational", "internal"],
             "channels": ["web", "internal", "presentation"], "territories": ["WW"], "attribution": "Netflix Open Content, CC BY 4.0",
             "model_release": "unknown"}
    elif f.startswith("netflix_"):
        r = {"status": "restricted", "source": "Netflix test shots", "licence": "Unclear (CC BY vs CC BY-NC-ND notices)",
             "notes": "Conflicting licence notices; local evaluation only until legal review (OPEN_QUESTIONS Q5)."}
    elif f.startswith("pexels_"):
        r = {"status": "cleared", "source": "Pexels", "licence": "Pexels licence", "permitted_uses": ["commercial", "editorial", "marketing", "advertising"],
             "channels": ["social", "web", "online_advertising"], "territories": ["WW"], "model_release": "not_applicable"}
    elif f in ("goldeneye.mp4",):
        r = {"status": "not_cleared", "source": "Third-party trailer (test clip)", "notes": "Copyrighted; never use."}
    else:
        continue
    out = call("PUT", f"/api/rights/{a['uid']}", r)
    counts[out["badge"]] = counts.get(out["badge"], 0) + 1
print(counts)
