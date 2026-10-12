"""Fetch official Steam store images for each news item of an episode.

For every item that has "steam": "<exact game name>" (or "steam_appid": 123),
downloads the store header and the first screenshots into assets/<slug>/,
and writes assets/<slug>/manifest.json. Runs on GitHub Actions (needs internet).
"""
import json, os, re, sys, urllib.parse, urllib.request

UA = {"User-Agent": "scar-shorts/1.0"}

def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data if binary else json.loads(data.decode("utf-8"))

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def find_appid(name):
    res = get("https://store.steampowered.com/api/storesearch/?cc=sa&l=english&term=" + urllib.parse.quote(name))
    items = res.get("items", [])
    for it in items:                      # exact (normalized) title match only
        if norm(it["name"]) == norm(name):
            return it["id"], it["name"]
    print(f"  no exact match for {name!r}; candidates: {[i['name'] for i in items[:5]]}")
    return None, None

def main(ep_path):
    ep = json.load(open(ep_path, encoding="utf-8"))
    out = os.path.join("assets", ep["slug"]); os.makedirs(out, exist_ok=True)
    manifest = {}
    for idx, it in enumerate(ep["items"]):
        appid, name = it.get("steam_appid"), it.get("steam")
        if not appid and name:
            appid, name = find_appid(name)
        if not appid:
            continue
        det = get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=sa&l=english")
        data = det.get(str(appid), {}).get("data")
        if not data:
            print(f"  appdetails empty for {appid}"); continue
        entry = {"appid": appid, "name": data.get("name"), "files": {}}
        urls = {"header": data.get("header_image")}
        for k, s in enumerate((data.get("screenshots") or [])[:3]):
            urls[f"shot{k}"] = s.get("path_full")
        for key, url in urls.items():
            if not url: continue
            fn = f"{idx}_{key}.jpg"
            open(os.path.join(out, fn), "wb").write(get(url.split("?")[0], binary=True))
            entry["files"][key] = fn
        manifest[str(idx)] = entry
        print(f"  item {idx}: {entry['name']} ({appid}) -> {list(entry['files'])}")
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=2, ensure_ascii=False)

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p); main(p)
