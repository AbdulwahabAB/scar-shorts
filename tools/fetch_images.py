"""Fetch official Steam store images for each news item of an episode.

For every item that has "steam": "<exact game name>" (or "steam_appid": 123),
downloads the store header and the first screenshots into assets/<slug>/,
and writes assets/<slug>/manifest.json. Runs on GitHub Actions (needs internet).
"""
import json, os, re, subprocess, sys, urllib.parse, urllib.request

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

def movie_url(m):
    for k in ("mp4", "webm"):
        v = m.get(k)
        if isinstance(v, dict):
            for q in ("max", "480"):
                if v.get(q): return v[q]
    for k in ("hls_h264", "dash_h264", "dash_av1"):
        if m.get(k): return m[k]
    return None

def cut_clip(url, dst, start, dur=6.5):
    """Short, MUTED clip sized for the 960x430 card panel. Tries a few strategies (HLS/DASH/MP4)."""
    vf = "scale=960:430:force_original_aspect_ratio=increase,crop=960:430,fps=30"
    enc = ["-t", str(dur), "-an", "-vf", vf, "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", dst]
    common = ["-protocol_whitelist", "file,http,https,tcp,tls,crypto", "-allowed_extensions", "ALL"]
    tries = [
        ["ffmpeg", "-y", "-loglevel", "warning"] + common + ["-ss", str(start), "-i", url] + enc,
        ["ffmpeg", "-y", "-loglevel", "warning"] + common + ["-i", url, "-ss", str(start)] + enc,
        ["ffmpeg", "-y", "-loglevel", "warning", "-i", url, "-ss", str(start)] + enc,
    ]
    print(f"    trailer url: {url[:160]}")
    for i, cmd in enumerate(tries):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
        size = os.path.getsize(dst) if os.path.exists(dst) else 0
        print(f"    try {i}: rc={r.returncode} size={size} {r.stderr.strip()[-400:]}")
        if r.returncode == 0 and size > 50_000:
            return
    raise RuntimeError("all clip strategies failed")

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
        po = data.get("price_overview") or {}
        entry = {"appid": appid, "name": data.get("name"), "files": {},
                 "meta": {"developers": data.get("developers", []), "publishers": data.get("publishers", []),
                          "genres": [g.get("description") for g in data.get("genres", [])],
                          "is_free": data.get("is_free", False),
                          "price": po.get("final_formatted"), "currency": po.get("currency"),
                          "discount": po.get("discount_percent"),
                          "release_date": (data.get("release_date") or {}).get("date"),
                          "coming_soon": (data.get("release_date") or {}).get("coming_soon"),
                          "short_description": data.get("short_description")}}
        urls = {"header": data.get("header_image")}
        for k, s in enumerate((data.get("screenshots") or [])[:3]):
            urls[f"shot{k}"] = s.get("path_full")
        for key, url in urls.items():
            if not url: continue
            fn = f"{idx}_{key}.jpg"
            open(os.path.join(out, fn), "wb").write(get(url.split("?")[0], binary=True))
            entry["files"][key] = fn
        movies = data.get("movies") or []
        if movies and not it.get("no_clip"):
            want = (it.get("movie") or "").lower()
            pick = (next((m for m in movies if want and want in (m.get("name") or "").lower()), None)
                    or next((m for m in movies if "gameplay" in (m.get("name") or "").lower()), movies[0]))
            entry["movie"] = {"name": pick.get("name")}
            entry["movies"] = [m.get("name") for m in movies]
            url = movie_url(pick)
            if url:
                try:
                    fn = f"{idx}_clip.mp4"
                    cut_clip(url, os.path.join(out, fn), it.get("clip_start", 18))
                    entry["files"]["clip"] = fn
                except Exception as e:
                    print(f"  clip failed for {appid}: {e}")
        manifest[str(idx)] = entry
        print(f"  item {idx}: {entry['name']} ({appid}) -> {list(entry['files'])}")
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=2, ensure_ascii=False)

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p); main(p)
