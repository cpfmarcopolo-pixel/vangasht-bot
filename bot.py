"""Vangasht Instagram bot.

Every day it publishes (through the official Instagram Graph API):
  11:00  story 1  -> today's exchange rates, read live from vangasht.com
                     (if the rates on the site are older than RATES_MAX_AGE_H hours,
                      a story from the library is used instead, so stale prices are never posted)
  17:00  story 2  -> the oldest photo/video you uploaded to the stories/ folder that is not published yet;
                     if the folder is empty, the next designed story from stories.json
  20:00  post     -> next post (image + caption) from content/posts.json

Usage:
  python bot.py render <story1|story2|post>   # builds out/<date>-<slot>.jpg and out/pending.json
  python bot.py publish                        # sends out/pending.json to Instagram
  python bot.py preview                        # renders every library item into preview/ (for checking)
"""
import base64, datetime as dt, json, os, random, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
A, OUT, C = ROOT, ROOT / "out", ROOT
STATE = ROOT / "state.json"
SITE_JSON = os.environ.get("SITE_JSON", "https://vangasht.com/data/site.json")
GRAPH = "https://graph.facebook.com/v21.0"
RATES_MAX_AGE_H = float(os.environ.get("RATES_MAX_AGE_H", "30"))
TR = dt.timezone(dt.timedelta(hours=3))

# ---------------------------------------------------------------- site data
def site():
    try:
        u = SITE_JSON + ("?t=" + str(int(time.time())) if SITE_JSON.startswith("http") else "")
        req = urllib.request.Request(u, headers={"User-Agent": "vangasht-bot"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print("! could not read site.json:", e)
        return {}

def fa(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def wa_fmt(n):
    n = "".join(ch for ch in str(n or "") if ch.isdigit())
    if n.startswith("98") and len(n) == 12:
        return f"+98 {n[2:5]} {n[5:8]} {n[8:]}"
    if n.startswith("90") and len(n) == 12:
        return f"+90 {n[2:5]} {n[5:8]} {n[8:10]} {n[10:]}"
    return "+" + n if n else ""

def vars_for(d):
    h = d.get("hours") or {}
    return {
        "wa": wa_fmt(d.get("whatsapp", "989141472696")),
        "hours": fa(f"{h.get('open', '07:00')} تا {h.get('close', '22:00')}"),
        "address": d.get("address", "مرکز شهر وان"),
        "address_short": "دفتر وان گشت، مرکز شهر وان",
    }

def fill(s, v):
    for k, val in v.items():
        s = s.replace("{" + k + "}", val)
    return s

def jalali(g):
    gy, gm, gd = g.year, g.month, g.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    return f"{fa(jd)} {months[jm - 1]} {fa(jy)}"

# ---------------------------------------------------------------- design
def b64(p, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(p).read_bytes()).decode()

PHOTOS = {"akdamar": "Armenak Margarian · CC BY-SA 4.0", "lake": "Hazreti madem19 · CC BY-SA 4.0",
          "fortress": "Adam Jones · CC BY-SA 2.0", "muradiye": "TobiasGr · CC BY-SA 3.0",
          "cat": "Yusuf Bayezit · CC BY-SA 4.0", "hosap": "Leon Petrosyan · CC BY-SA 4.0", "suite": ""}

def css():
    font = b64(A / "Vazirmatn-var.woff2", "font/woff2")
    return f"""@font-face{{font-family:V;src:url({font})}}*{{margin:0;box-sizing:border-box}}
body{{font-family:V,'Noto Color Emoji';color:#fff;position:relative;overflow:hidden}}
.bg{{position:absolute;inset:0;background-size:cover;background-position:center}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,30,38,.05) 30%,rgba(10,40,50,.92) 75%)}}
.teal{{position:absolute;inset:0;background:radial-gradient(circle at 80% 10%,#1b7a90,#0d5b6f 45%,#0b2f3a)}}
.brand{{position:absolute;display:flex;align-items:center;gap:14px;direction:ltr}}
.brand .ic{{width:78px;height:78px;background:#fff;border-radius:20px;padding:7px;display:grid;place-items:center}}
.brand svg{{height:62px;width:auto}}
.brand b{{font:700 44px Georgia,serif;display:block;line-height:1}}
.brand span{{display:block;color:#f2ad3d;font-weight:800;font-size:24px;text-align:right}}
.cr{{position:absolute;left:24px;bottom:16px;font-size:18px;opacity:.7;direction:ltr}}
.url{{font:700 40px Georgia,serif;color:#f2ad3d;direction:ltr}}
.tag{{display:inline-block;background:#f2ad3d;color:#12222a;font-weight:900;border-radius:14px;padding:8px 22px}}
ul{{list-style:none;padding:0}}li{{margin:0 0 22px;display:flex;gap:18px;align-items:center}}li i{{font-style:normal;font-size:52px}}
table{{width:100%;border-collapse:collapse;font-weight:800}}
td,th{{padding:26px 10px;border-bottom:2px solid rgba(255,255,255,.18);text-align:center}}
th{{font-size:34px;color:#f2ad3d;font-weight:800}}td{{font-size:50px}}td:first-child{{text-align:right;font-size:44px}}
td small{{display:block;font-size:26px;opacity:.75;font-weight:600}}"""

def brand():
    logo = (A / "logo.svg").read_text()
    return f'<div class="brand" style="right:48px;top:44px"><div class="ic">{logo}</div><div><b>Vangasht</b><span>وان گشت</span></div></div>'

def photo_html(it, H, v):
    ph = it["photo"]
    src = b64(A / f"{ph}.jpg", "image/jpeg")
    cr = f'<div class="cr">عکس: {PHOTOS[ph]}</div>' if PHOTOS.get(ph) else ""
    big = H > 1500
    wa = f'<p style="font-size:40px;margin-top:16px;font-weight:800">واتس‌اپ: <span dir=ltr>{v["wa"]}</span></p>' if it.get("wa") else ""
    return f"""<div class="bg" style="background-image:url({src});background-position:{'center 92%' if ph == 'lake' else 'center'}"></div><div class="shade"></div>{brand()}
<div style="position:absolute;right:60px;left:60px;bottom:{110 if big else 80}px"><span class="tag" style="font-size:{34 if big else 30}px">{fill(it['tag'], v)}</span>
<h1 style="font-size:{92 if big else 78}px;font-weight:900;line-height:1.3;margin-top:22px">{fill(it['title'], v)}</h1>
<p style="font-size:{44 if big else 38}px;margin-top:14px;font-weight:600;line-height:1.5">{fill(it.get('sub', ''), v)}</p>{wa}
<p class="url" style="margin-top:28px">vangasht.com</p></div>{cr}"""

def design_html(it, H, v):
    big = H > 1500
    lis = "".join(f'<li><i>{a}</i><span>{fill(b, v)}</span></li>' for a, b in it["items"])
    return f"""<div class="teal"></div>{brand()}<div style="position:absolute;right:70px;left:70px;top:{300 if big else 220}px">
<span class="tag" style="font-size:32px">{fill(it['tag'], v)}</span><h1 style="font-size:{96 if big else 80}px;font-weight:900;line-height:1.3;margin:28px 0 48px">{fill(it['title'], v)}</h1>
<ul style="font-size:{50 if big else 42}px;font-weight:700">{lis}</ul></div>
<div style="position:absolute;right:70px;left:70px;bottom:{120 if big else 70}px"><p style="font-size:{40 if big else 34}px;font-weight:600;margin-bottom:10px">{fill(it.get('foot', ''), v)}</p><p class="url">vangasht.com</p></div>"""

NAMES = {"USD": "دلار آمریکا", "EUR": "یورو", "GBP": "پوند انگلیس"}

def num(x):
    x = float(x)
    s = f"{x:,.0f}" if x >= 1000 or x == int(x) else f"{x:,.2f}".rstrip("0").rstrip(".")
    return fa(s).replace(",", "٬")

def rates_html(d, v):
    R = {r["code"]: r for r in d.get("rates", [])}
    rows = []
    if "TRY" in R:
        rows.append(("۱ لیر ترکیه", "به تومان", R["TRY"]))
    if "IRT" in R:
        rows.append(("۱ میلیون تومان", "به لیر", R["IRT"]))
    for c in ("USD", "EUR", "GBP"):
        if c in R:
            rows.append((NAMES[c], "به لیر", R[c]))
    trs = "".join(f"<tr><td>{a}<small>{b}</small></td><td>{num(r['buy'])}</td><td>{num(r['sell'])}</td></tr>" for a, b, r in rows)
    today = jalali(dt.datetime.now(TR).date())
    return f"""<div class="teal"></div>{brand()}<div style="position:absolute;right:64px;left:64px;top:250px">
<span class="tag" style="font-size:34px">نرخ امروز · {today}</span>
<h1 style="font-size:84px;font-weight:900;line-height:1.3;margin:26px 0 30px">صرافی وان گشت 💱</h1>
<table><tr><th style="text-align:right">ارز</th><th>خرید ما</th><th>فروش ما</th></tr>{trs}</table>
<p style="font-size:30px;margin-top:26px;opacity:.85;font-weight:600">نرخ‌ها ممکن است در طول روز تغییر کنند؛ نرخ نهایی، نرخ پشت باجه است.</p></div>
<div style="position:absolute;right:64px;left:64px;bottom:120px"><p style="font-size:40px;font-weight:800;margin-bottom:10px">💳 کارتخوان ایرانی در دفتر · واتس‌اپ <span dir=ltr>{v['wa']}</span></p><p class="url">vangasht.com/sarafi-van</p></div>"""

def render_html(html, W, H, path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(f"<html dir=rtl><head><meta charset=utf-8><style>{css()}body{{width:{W}px;height:{H}px}}</style></head><body>{html}</body></html>")
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(path), type="jpeg", quality=92)
        b.close()

# ---------------------------------------------------------------- state
def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"post": 0, "story": 0, "log": []}

def save_state(s):
    s["log"] = s["log"][-60:]
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1))

def rates_fresh(d):
    try:
        t = dt.datetime.fromisoformat(d["updatedAt"].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
        print(f"rates updated {age:.1f} h ago")
        return bool(d.get("rates")) and not d.get("ratesSample") and age <= RATES_MAX_AGE_H
    except Exception:
        return False

MEDIA = ROOT / "stories"
IMG_EXT, VID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}, {".mp4", ".mov"}

def added_time(f):
    """When the file was first uploaded to the repo (needs full git history)."""
    try:
        import subprocess
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", str(f)],
                             cwd=ROOT, capture_output=True, text=True).stdout.split()
        return int(out[-1]) if out else int(f.stat().st_mtime)
    except Exception:
        return int(f.stat().st_mtime)

def drive_media(st):
    """Oldest unpublished photo/video in the shared Google Drive folder (downloaded to dl/)."""
    key, folder = os.environ.get("GDRIVE_KEY"), os.environ.get("GDRIVE_FOLDER")
    if not key or not folder:
        return None
    q = f"'{folder}' in parents and trashed=false and (mimeType contains 'image/' or mimeType contains 'video/')"
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
        {"q": q, "orderBy": "createdTime", "pageSize": 200, "key": key,
         "fields": "files(id,name,mimeType,createdTime,size)"})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            files = json.load(r).get("files", [])
    except urllib.error.HTTPError as e:
        print("! Google Drive error:", e.code, e.read().decode(errors="replace")[:300]); return None
    done = set(st.get("media_done", []))
    files = [f for f in files if "gdrive:" + f["id"] not in done]
    print(f"{len(files)} photo/video(s) waiting in Google Drive")
    if not files:
        return None
    f = files[0]
    ext = Path(f["name"]).suffix.lower() or (".mp4" if f["mimeType"].startswith("video/") else ".jpg")
    dl = ROOT / "dl"; dl.mkdir(exist_ok=True)
    local = dl / (f["id"] + ext)
    src = f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&key={key}"
    with urllib.request.urlopen(src, timeout=600) as r, open(local, "wb") as w:
        while chunk := r.read(1 << 20):
            w.write(chunk)
    print("downloaded from Drive:", f["name"])
    return local, "gdrive:" + f["id"], f["name"]

def next_media(st):
    got = drive_media(st)
    if got:
        return got
    if not MEDIA.is_dir():
        return None
    done = set(st.get("media_done", []))
    files = [f for f in MEDIA.iterdir() if f.suffix.lower() in IMG_EXT | VID_EXT and f.name not in done]
    files.sort(key=lambda f: (added_time(f), f.name))
    print(f"{len(files)} uploaded photo/video(s) waiting in stories/")
    return (files[0], files[0].name, files[0].name) if files else None

def story_image(src, dst):
    """Fit any photo into a 1080x1920 story; a blurred copy fills the empty space."""
    from PIL import Image, ImageOps, ImageFilter
    if src.suffix.lower() == ".heic":
        from pillow_heif import register_heif_opener; register_heif_opener()
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    W, H = 1080, 1920
    bg = ImageOps.fit(im, (W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (10, 30, 38)), 0.35)
    fg = im.copy(); fg.thumbnail((W, H))
    if abs(im.width / im.height - W / H) < 0.06:
        fg = ImageOps.fit(im, (W, H))
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    bg.save(dst, "JPEG", quality=92)

def render(slot):
    d, st = site(), load_state()
    v = vars_for(d)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.jpg"):  # keep the repo small: images are only needed until Instagram has copied them
        if time.time() - old.stat().st_mtime > 7 * 86400:
            old.unlink()
    day = dt.datetime.now(TR).strftime("%Y-%m-%d")
    path = OUT / f"{day}-{slot}.jpg"
    job = {"slot": slot, "file": path.name, "caption": None, "advance": None, "item": None}
    if slot == "post":
        lib = json.loads((C / "posts.json").read_text())
        it = lib[st["post"] % len(lib)]
        html = (photo_html if it["kind"] == "photo" else design_html)(it, 1350, v)
        render_html(html, 1080, 1350, path)
        tags = "#وان #وان_ترکیه #سفر_به_وان #صرافی_وان #سوئیت_وان #تور_وان #خرید_از_وان #ترکیه #VanTurkey #Van #VanGölü #وان_گشت"
        job.update(caption=fill(it["caption"], v) + "\n\n" + tags, advance="post", item=it["id"])
    elif slot == "story1" and rates_fresh(d):
        render_html(rates_html(d, v), 1080, 1920, path)
        job.update(item="rates")
    elif slot == "story2" and (got := next_media(st)):
        m, mid, label = got
        if m.suffix.lower() in VID_EXT:
            job.update(file=None, video=str(m.relative_to(ROOT)), item=label, media=mid)
            print("using your video", label)
        else:
            story_image(m, path)
            job.update(item=label, media=mid)
            print("using your photo", label)
    else:
        if slot == "story1":
            print("! rates on the site are old -> using a library story instead (update the rates in admin)")
        lib = json.loads((C / "stories.json").read_text())
        it = lib[st["story"] % len(lib)]
        html = (photo_html if it["kind"] == "photo" else design_html)(it, 1920, v)
        render_html(html, 1080, 1920, path)
        job.update(advance="story", item=it["id"])
    (OUT / "pending.json").write_text(json.dumps(job, ensure_ascii=False, indent=1))
    print("ready:", job["file"] or job.get("video"), "->", job["item"])

# ---------------------------------------------------------------- Instagram Graph API
def api(method, path, **params):
    params["access_token"] = os.environ["IG_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"Instagram API error {e.code} on {path}: {body}")

def ig_user():
    if os.environ.get("IG_USER_ID"):
        return os.environ["IG_USER_ID"]
    r = api("GET", "me/accounts", fields="name,instagram_business_account{id,username}")
    for p in r.get("data", []):
        ig = p.get("instagram_business_account")
        if ig:
            print(f"using Instagram @{ig.get('username')} (page {p['name']})")
            return ig["id"]
    raise SystemExit("No Instagram account found on this token. Check the Page and Instagram are assigned to the system user.")

def upload_video(ig, f):
    """Instagram's resumable upload: the video goes straight from here to Meta, no public link needed."""
    size = f.stat().st_size
    print(f"uploading video {f.name} ({size // 1024 // 1024} MB)")
    r = api("POST", f"{ig}/media", media_type="STORIES", upload_type="resumable")
    req = urllib.request.Request(r["uri"], data=f.read_bytes(), method="POST", headers={
        "Authorization": "OAuth " + os.environ["IG_TOKEN"], "offset": "0", "file_size": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            print("upload:", resp.read().decode(errors="replace")[:200])
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Video upload failed {e.code}: {e.read().decode(errors='replace')}")
    return r["id"]

def publish():
    job = json.loads((OUT / "pending.json").read_text())
    st = load_state()
    if job.get("done"):
        print("already published"); return
    if not os.environ.get("IG_TOKEN"):
        print("IG_TOKEN not set -> dry run, nothing sent"); return
    jitter = random.randint(0, int(os.environ.get("JITTER_MAX_MIN", "12")) * 60)
    print(f"waiting {jitter // 60} min so posting time is not robotic"); time.sleep(jitter)
    repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/out/{job['file']}"
    ig = ig_user()
    if job.get("video"):
        cid = upload_video(ig, ROOT / job["video"])
    else:
        params = {"image_url": url}
        if job["slot"] == "post":
            params["caption"] = job["caption"]
        else:
            params["media_type"] = "STORIES"
        cid = api("POST", f"{ig}/media", **params)["id"]
    for _ in range(120):
        s = api("GET", cid, fields="status_code").get("status_code")
        if s == "FINISHED":
            break
        if s == "ERROR":
            raise SystemExit("Instagram could not process the image " + url)
        time.sleep(5)
    mid = api("POST", f"{ig}/media_publish", creation_id=cid)["id"]
    print("published media", mid)
    if job.get("advance"):
        st[job["advance"]] += 1
    if job.get("media"):
        st.setdefault("media_done", []).append(job["media"])
    st["log"].append({"at": dt.datetime.now(TR).isoformat(timespec="minutes"), "slot": job["slot"], "item": job["item"], "media": mid})
    save_state(st)
    job["done"] = True
    (OUT / "pending.json").write_text(json.dumps(job, ensure_ascii=False, indent=1))

def preview():
    d = site(); v = vars_for(d); P = ROOT / "preview"; P.mkdir(exist_ok=True)
    for it in json.loads((C / "posts.json").read_text()):
        render_html((photo_html if it["kind"] == "photo" else design_html)(it, 1350, v), 1080, 1350, P / f"post-{it['id']}.jpg")
    for it in json.loads((C / "stories.json").read_text()):
        render_html((photo_html if it["kind"] == "photo" else design_html)(it, 1920, v), 1080, 1920, P / f"story-{it['id']}.jpg")
    if d.get("rates"):
        render_html(rates_html(d, v), 1080, 1920, P / "story-rates.jpg")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "render" and len(sys.argv) > 2:
        render(sys.argv[2])
    elif cmd == "publish":
        publish()
    elif cmd == "preview":
        preview()
    else:
        print(__doc__)
