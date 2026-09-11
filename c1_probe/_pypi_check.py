import json
import urllib.request

for pkg in ("qasync",):
    try:
        d = json.load(urllib.request.urlopen("https://pypi.org/pypi/%s/json" % pkg))
        info = d["info"]
        ver = info["version"]
        files = d["releases"].get(ver, [])
        up = files[0]["upload_time"] if files else "?"
        print("%s: latest %s  %s" % (pkg, ver, up))
        print("  requires_python:", info.get("requires_python"))
        names = sorted({f["filename"] for f in files})
        print("  files:", names)
    except Exception as e:
        print("%s: ERR %s" % (pkg, e))
