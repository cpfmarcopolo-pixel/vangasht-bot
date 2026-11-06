"""Vangasht Instagram bot.

Every day it publishes (through the official Instagram Graph API), started by cron-job.org:
  s1 09:00 good morning      s2 11:00 exchange rates     p1 11:30 post (Reel)   s3 12:00 vlog
  s4 13:00 vangasht.com      s5 14:30 tours              s6 16:00 question      s7 17:30 vlog
  s8 19:00 a Van attraction  p2 20:00 post (Reel)        s9 21:00 today's posts s10 23:00 good night
Each one uses its own Drive sub-folder (S1 ... S10, P) for videos / photos / songs, see FOLDER_ALIASES.
Old names still work: story1=s2, story3=s3, story4=s9, post=p2, story2 = next file of the main Drive folder.

Usage:
  python bot.py render <s1..s10|p1|p2|testcards|...>   # builds the media in out/ and out/pending.json
  python bot.py publish                        # sends out/pending.json to Instagram
  python bot.py preview                        # renders every library item into preview/ (for checking)
"""
import base64, datetime as dt, json, os, random, re, sys, time, urllib.parse, urllib.request
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

COMMONS_Q = {"akdamar": "Akdamar island Lake Van", "lake": "Lake Van landscape", "fortress": "Van Fortress",
             "muradiye": "Muradiye waterfall", "cat": "Turkish Van cat", "hosap": "Hosap castle",
             "city": "Van Turkey city", "erek": "Erek mountain Van", "edremit": "Edremit Van lake", "suphan": "Mount Suphan"}

def css():
    font = b64(A / "Vazirmatn-var.woff2", "font/woff2")
    return f"""@font-face{{font-family:V;src:url({font})}}*{{margin:0;box-sizing:border-box}}
body{{font-family:V,'Noto Color Emoji';color:#fff;position:relative;overflow:hidden}}
.bg{{position:absolute;inset:0;background-size:cover;background-position:center}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,30,38,.05) 30%,rgba(10,40,50,.92) 75%)}}
.teal{{position:absolute;inset:0;background:#0b2f3a;overflow:hidden}}.teal:before{{content:"";position:absolute;width:900px;height:900px;left:-380px;bottom:-420px;border-radius:50%;background:#0d5b6f}}.teal:after{{content:"";position:absolute;width:520px;height:520px;right:-200px;top:-220px;border-radius:50%;border:40px solid rgba(242,173,61,.18)}}
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

def hl(it, v):
    t = fill(it["title"], v); h = (it.get("hl") or "").strip()
    if not h or h not in t:
        return t
    a = t.index(h); b = a + len(h)
    while b < len(t) and t[b] not in " ،,.!؟?:؛\u200c":   # never split a word (Persian letters must stay joined)
        b += 1
    while a > 0 and t[a - 1] not in " ،,.!؟?:؛":
        a -= 1
    return t[:a] + f'<span style="color:#f2ad3d">{t[a:b]}</span>' + t[b:]

def photo_html(it, H, v):
    ph = it.get("photo")
    if not it.get("photo_path") and ph not in PHOTOS:
        ph = "lake"
    src = b64(it["photo_path"], "image/jpeg") if it.get("photo_path") else b64(A / f"{ph}.jpg", "image/jpeg")
    credit = it.get("credit") if it.get("photo_path") else PHOTOS.get(ph)
    cr = f'<div class="cr">عکس: {credit}</div>' if credit else ""
    big = H > 1500
    wa = f'<p style="font-size:40px;margin-top:16px;font-weight:800">واتس‌اپ: <span dir=ltr>{v["wa"]}</span></p>' if it.get("wa") else ""
    return f"""<div class="bg" style="background-image:url({src});background-position:{'center 92%' if ph == 'lake' and not it.get('photo_path') else 'center'}"></div><div class="shade"></div>{brand()}
<div style="position:absolute;right:60px;left:60px;bottom:{110 if big else 80}px"><span class="tag" style="font-size:{34 if big else 30}px">{fill(it['tag'], v)}</span>
<h1 style="font-size:{104 if big else 88}px;font-weight:900;line-height:1.25;margin-top:22px;text-shadow:0 4px 24px rgba(0,0,0,.45)">{hl(it, v)}</h1>
<p style="font-size:{44 if big else 38}px;margin-top:14px;font-weight:600;line-height:1.5">{fill(it.get('sub', ''), v)}</p>{wa}
<p class="url" style="margin-top:28px">vangasht.com</p></div>{cr}"""

def design_html(it, H, v):
    big = H > 1500
    lis = "".join(f'<li style="background:rgba(255,255,255,.08);border:2px solid rgba(255,255,255,.14);border-radius:28px;padding:22px 26px"><i>{a}</i><span>{fill(b, v)}</span></li>' for a, b in it["items"])
    return f"""<div class="teal"></div>{brand()}<div style="position:absolute;right:70px;left:70px;top:{300 if big else 220}px">
<span class="tag" style="font-size:32px">{fill(it['tag'], v)}</span><h1 style="font-size:{104 if big else 88}px;font-weight:900;line-height:1.25;margin:28px 0 44px">{hl(it, v)}</h1>
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
    seen = set(st.get("media_seen", []))
    files = [f for f in files if "gdrive:" + f["id"] not in done and f"{f['name']}|{f.get('size')}" not in seen]
    print(f"{len(files)} photo/video(s) waiting in Google Drive")
    if not files:
        return None
    f = files[0]
    ext = Path(f["name"]).suffix.lower() or (".mp4" if f["mimeType"].startswith("video/") else ".mp3" if f["mimeType"].startswith("audio/") else ".jpg")
    dl = ROOT / "dl"; dl.mkdir(exist_ok=True)
    local = dl / (f["id"] + ext)
    src = f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&key={key}"
    with urllib.request.urlopen(src, timeout=600) as r, open(local, "wb") as w:
        while chunk := r.read(1 << 20):
            w.write(chunk)
    print("downloaded from Drive:", f["name"])
    st.setdefault("media_seen", []).append(f"{f['name']}|{f.get('size')}")
    st["media_seen"] = st["media_seen"][-500:]
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

def ffmpeg_bin():
    import shutil, subprocess
    b = shutil.which("ffmpeg")
    if b:
        return b
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"], check=False)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def story_video(src, dst):
    """Re-encode any phone video to what Instagram stories accept: H.264/AAC MP4, 1080x1920 (blurred fill), 30 fps, max 59 s."""
    import subprocess
    ff = ffmpeg_bin()
    if not ff:
        raise RuntimeError("ffmpeg not available")
    vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
          "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p")
    cmd = [ff, "-y", "-i", str(src), "-t", "59", "-filter_complex", vf, "-c:v", "libx264", "-preset", "veryfast",
           "-profile:v", "high", "-b:v", "5M", "-maxrate", "6M", "-bufsize", "10M", "-c:a", "aac", "-b:a", "128k",
           "-ar", "44100", "-ac", "2", "-movflags", "+faststart", "-shortest", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # video without an audio track: try again without audio mapping problems
        cmd2 = [c for c in cmd if c not in ("-shortest",)]
        r = subprocess.run(cmd2, capture_output=True, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError("ffmpeg failed: " + r.stderr[-400:])
    print(f"video re-encoded for Instagram ({Path(dst).stat().st_size // 1024 // 1024} MB)")

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

# ---------------------------------------------------------------- AI writer (Claude)
AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")
AI_ERROR = None
PHOTO_TOPICS = {"akdamar": "جزیرهٔ آکدامار و کلیسای تاریخی، دریاچهٔ وان", "lake": "دریاچهٔ وان، آب فیروزه‌ای و کوه",
                "fortress": "قلعهٔ وان روی صخره", "muradiye": "آبشار مرادیه", "cat": "گربهٔ سفید وان با چشم‌های دو رنگ",
                "hosap": "قلعهٔ هوشاپ", "suite": "داخل یکی از سوئیت‌های مبلهٔ وان گشت"}
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]

def ai_context(d, v):
    now = dt.datetime.now(TR)
    R = {r["code"]: r for r in d.get("rates", [])}
    rates = ", ".join(f"{c}: خرید {R[c]['buy']} فروش {R[c]['sell']}" for c in ("TRY", "USD", "EUR") if c in R)
    suites = "; ".join(f"{(s.get('name') or {}).get('fa', '')} ({s.get('price')} {s.get('currency', 'TRY')}/شب، تا {s.get('guests')} نفر)"
                       for s in d.get("suites", [])[:6])
    tours = "; ".join((t.get("title") or {}).get("fa", "") for t in d.get("tours", []) if t.get("title"))
    return (f"امروز: {WEEKDAYS[now.weekday()]} {jalali(now.date())} ({now:%Y-%m-%d})\n"
            f"خدمات وان گشت: صرافی با کارتخوان ایرانی (عضو شتاب) در شهر وان ترکیه، سوئیت مبله، تور، کارت تخفیف ۱۰٪ در مغازه‌های طرف قرارداد با اسکن QR و امتیاز.\n"
            f"آدرس دفتر: {v['address']} · ساعت کاری: {v['hours']} · واتس‌اپ: {v['wa']}\n"
            f"سوئیت‌ها: {suites or '—'}\nتورها: {tours or 'آکدامار، آبشار مرادیه، کشتی تفریحی'}\n"
            f"نرخ‌ها (فقط برای اطلاع؛ عدد نرخ را در متن ننویس): {rates or '—'}\n"
            "صفحه‌های سایت: vangasht.com ، vangasht.com/sarafi-van ، vangasht.com/suite-van ، vangasht.com/gardeshgari-van ، "
            "vangasht.com/rahnama-van ، vangasht.com/shahr-van ، vangasht.com/majale ، vangasht.com/tour")

AI_RULES = """تو ادمین خلاق و باتجربهٔ پیج اینستاگرام «وان گشت» هستی؛ مخاطب: مسافران ایرانی که به شهر وان ترکیه می‌آیند یا دارند برنامه می‌ریزند.
لحن و نوشتن:
- مثل پیج‌های پرطرفدار سفر فارسی بنویس: خودمانی و گرم، به زبان گفتاری درست («می‌خوای»، «بریم»، «حواست باشه»)، نه کتابی و نه رسمی. جمله‌ها کوتاه. هر خط یک ایده.
- خط اول کپشن «قلاب» است: یک جملهٔ کنجکاوکننده، سؤال، یا نکتهٔ غافلگیرکننده که آدم را نگه دارد (مثلاً «۹۰٪ مسافرا این اشتباهو تو وان می‌کنن 👇»).
- بدنه: ۳ تا ۵ نکتهٔ کاربردی و مشخص (با ایموجی یا شماره)، تجربه‌محور، طوری که آدم بخواهد سیو کند.
- آخرش یک دعوت به تعامل (سؤال از مخاطب، «سیوش کن»، «برای همسفرت بفرست») و یک لینک مرتبط سایت. تبلیغ خدمات را طبیعی و کوتاه بیاور، نه با هر پست.
- قالب‌ها را بچرخان: «۳ نکته قبل از…»، «اشتباه رایج»، «این یا اون؟»، «یه روز در وان»، «راز/دانستنی»، «چک‌لیست سفر»، «سؤال پرتکرار».
قانون‌ها:
- هیچ عدد نرخ ارز یا قیمت تور ننویس. ادعای «ارزان‌ترین/بهترین» نکن. فقط اطلاعات متن زمینه یا دانش عمومی مطمئن دربارهٔ وان (تاریخ، طبیعت، غذا، فرهنگ، خرید). اگر مطمئن نیستی، ننویس.
- دربارهٔ سیاست، مذهب، قوانین مهاجرت و ویزا هیچ ادعایی نکن.
- املای درست: «آکدامار» (نه آق‌تامار).
- موضوع امروز با موضوع‌های اخیر فرق داشته باشد؛ فصل و روز هفته را در نظر بگیر.
- اگر نمونه‌پست‌های موفق پیج‌های دیگر داده شد، فقط از سبک، قالب و نوع موضوعشان ایده بگیر؛ هرگز متنشان را کپی یا بازنویسی نزدیک نکن.
- در دو سوم موارد kind را "photo" بگذار. کلید photo موضوع عکسی است که برایش عکس زیبا پیدا می‌شود؛ یکی از: """ + ", ".join(COMMONS_Q) + """
- برای پست، بیشتر روزها format را "carousel" بگذار (پست چندصفحه‌ای مثل پیج‌های حرفه‌ای): کاور قلاب‌دار + ۳ تا ۵ اسلاید که هر کدام یک نکته است + اسلاید آخر دعوت. اسلایدها کوتاه: تیتر ۳ تا ۶ کلمه، متن حداکثر ۲ خط.
- برای قالب «این یا اون؟»، اسلایدها دو گزینه‌اند و کپشن می‌پرسد «کامنت کن: ۱ یا ۲؟» (اینستاگرام نظرسنجی واقعی را فقط دستی در استوری می‌دهد).
خروجی فقط یک شیء JSON معتبر، بدون هیچ متن دیگر."""

def claude(prompt):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": AI_MODEL, "max_tokens": 2500, "system": AI_RULES,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    global AI_ERROR
    for attempt in (1, 2, 3):   # retry: the API is sometimes briefly busy
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.load(r)
            txt = "".join(b.get("text", "") for b in out.get("content", []))
            txt = txt[txt.find("{"): txt.rfind("}") + 1]
            AI_ERROR = None
            return json.loads(txt)
        except urllib.error.HTTPError as e:
            AI_ERROR = f"HTTP {e.code}: " + e.read().decode("utf-8", "replace")[:400]
            if e.code in (400, 401, 403, 404):
                break   # e.g. no credit left / wrong key: retrying will not help
        except Exception as e:
            AI_ERROR = str(e)[:400]
        print(f"! AI writer failed (try {attempt}):", AI_ERROR)
        time.sleep(20 * attempt)
    print("! AI writer failed, using the library instead:", AI_ERROR)
    return None

def inspo_text(st):
    ins = st.get("inspo") or {}
    lines = []
    if ins.get("own"):
        lines.append("پست‌های خود پیج ما که بیشترین لایک را گرفته‌اند (بفهم مخاطب ما چه دوست دارد):")
        lines += [f"- [{p.get('type', '')}] ❤{p['likes']} 💬{p['comments']}: {p['caption'][:220]}" for p in ins["own"][:4]]
    if ins.get("others"):
        lines.append("نمونه پست‌های موفق پیج‌های دیگر (فقط برای ایده گرفتن از سبک و قالب؛ کپی نکن):")
        lines += [f"- @{p['user']} [{p.get('type', '')}] ❤{p['likes']} 💬{p['comments']}: {p['caption'][:260]}" for p in ins["others"][:8]]
    return ("\n".join(lines) + "\n\n") if lines else ""

def refresh_inspo(ig, st):
    """Once a day, read (read-only) the best recent posts of our page and of the pages listed in inspiration.txt."""
    ins = st.get("inspo") or {}
    if ins.get("day") == dt.datetime.now(TR).strftime("%Y-%m-%d"):
        return
    F = "caption,like_count,comments_count,media_type,media_product_type"
    def rows(media, user=None):
        out = []
        for m in (media or {}).get("data", []):
            c = (m.get("caption") or "").strip()
            if len(c) > 30:
                out.append({"user": user, "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0), "caption": c.replace("\n", " / "),
                            "type": "ریلز" if m.get("media_product_type") == "REELS" else ("کاروسل" if m.get("media_type") == "CAROUSEL_ALBUM" else "عکس")})
        return sorted(out, key=lambda p: p["likes"] + 3 * p["comments"], reverse=True)
    new = {"day": dt.datetime.now(TR).strftime("%Y-%m-%d"), "own": [], "others": []}
    try:
        new["own"] = rows(api("GET", f"{ig}/media", fields=F, limit="25"))[:4]
    except BaseException as e:
        print("! could not read our own posts:", str(e)[:200])
    names = []
    f = ROOT / "inspiration.txt"
    if f.exists():
        names = [x.strip().lstrip("@") for x in f.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]
    others = []
    for u in names[:10]:
        try:
            r = api("GET", ig, fields=f"business_discovery.username({u}){{media.limit(12){{{F}}}}}")
            others += rows(r.get("business_discovery", {}).get("media"), u)[:3]
        except BaseException as e:
            print(f"! could not read @{u} (it must be a public business/creator account):", str(e)[:160])
            new.setdefault("errors", {})[u] = str(e)[:300]
    new["others"] = sorted(others, key=lambda p: p["likes"] + 3 * p["comments"], reverse=True)[:8]
    st["inspo"] = new
    print(f"inspiration: {len(new['own'])} own, {len(new['others'])} from other pages")

def ai_item(slot, d, v, st):
    recent = [x["topic"] for x in st.get("ai_log", [])[-20:]]
    shape = ('{"topic": "موضوع کوتاه برای ثبت", "kind": "photo" یا "design", "photo": "یکی از کلیدها (برای kind=photo)", '
             '"tag": "برچسب ۲ تا ۳ کلمه", "title": "تیتر قلاب‌دار حداکثر ۶ کلمه، خودمانی", "hl": "یک یا دو کلمه از همان تیتر که با رنگ طلایی برجسته شود", "sub": "زیرتیتر حداکثر ۷۰ حرف (برای photo)", '
             '"items": [["ایموجی", "حداکثر ۴۰ حرف"], ... دقیقاً ۳ مورد (برای design)], "foot": "یک خط حداکثر ۵۰ حرف (برای design)"')
    if slot == "post":
        shape += (', "format": "carousel" یا "single", "slides": [{"title": "تیتر اسلاید", "hl": "کلمهٔ طلایی", "body": "متن کوتاه حداکثر ۲ خط"}, ... ۳ تا ۵ مورد، فقط برای carousel]'
                  ', "cta": "جملهٔ اسلاید آخر مثل «سیوش کن که تو سفر یادت نره»"')
        shape += ', "caption": "کپشن ۶ تا ۱۲ خط کوتاه: خط اول قلاب، بعد نکته‌ها، آخر دعوت به تعامل + یک لینک مرتبط vangasht.com و در صورت مناسب بودن «واتس‌اپ: {wa}»؛ بدون هشتگ"'
    shape += "}"
    what = "یک پست اینستاگرام (عکس ۴:۵ با متن روی آن + کپشن)" if slot == "post" else "یک استوری اینستاگرام (۹:۱۶، فقط متن روی عکس، بدون کپشن)"
    prompt = (f"{ai_context(d, v)}\n\nموضوع‌های اخیر (تکرار نکن): {'، '.join(recent) or '—'}\n\n{inspo_text(st)}"
              f"{what} برای امروز بساز. شکل خروجی:\n{shape}")
    it = claude(prompt)
    if not isinstance(it, dict):
        st["ai_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "slot": slot, "error": AI_ERROR or "answer was not JSON"}
        save_state(st)
        return None
    try:
        it["kind"] = "photo" if it.get("kind") == "photo" else "design"
        if it.get("photo") not in COMMONS_Q:
            it["photo"] = "lake"
        if it["kind"] == "photo":
            assert it.get("title")
        else:
            it["items"] = [[str(a)[:4], str(b)[:60]] for a, b in it["items"][:3]]
            assert len(it["items"]) == 3 and it.get("title")
        for k, n in (("tag", 30), ("title", 50), ("hl", 30), ("sub", 90), ("foot", 70)):
            if k in it:
                it[k] = str(it[k])[:n].replace("<", "").replace(">", "")
        if it.get("slides"):
            it["slides"] = [{k: str(x.get(k, ""))[:n].replace("<", "").replace(">", "") for k, n in (("title", 60), ("hl", 30), ("body", 160))}
                            for x in it["slides"][:5] if isinstance(x, dict) and x.get("title")]
        if "cta" in it:
            it["cta"] = str(it["cta"])[:60].replace("<", "").replace(">", "")
        if slot == "post":
            assert len(it.get("caption", "")) > 40
            it["caption"] = it["caption"].replace("<", "").replace(">", "")
        it["id"] = "ai:" + str(it.get("topic", it["title"]))[:40]
        print("AI wrote:", it["id"])
        return it
    except Exception as e:
        print("! AI answer was not usable, using the library instead:", e)
        st["ai_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "slot": slot, "error": "unusable answer: " + repr(e)[:200]}
        save_state(st)
        return None

def ai_remember(st, it):
    if it and str(it.get("id", "")).startswith("ai:"):
        st.setdefault("ai_log", []).append({"day": dt.datetime.now(TR).strftime("%Y-%m-%d"), "topic": it["id"][3:]})
        st["ai_log"] = st["ai_log"][-40:]
        save_state(st)

def try_video(got, st, job):
    m, mid, label = got
    dst = ROOT / "dl" / (m.stem + "-ig.mp4")
    try:
        dst.parent.mkdir(exist_ok=True)
        story_video(m, dst)
        job.update(file=None, video=str(dst.relative_to(ROOT)), item=label, media=mid)
        return True
    except Exception as e:
        print("! could not prepare the video, skipping it:", e)
        st.setdefault("media_done", []).append(mid)
        st.setdefault("media_failed", []).append({"media": mid, "item": label, "error": str(e)[:300]})
        save_state(st)
        return False

# ---------------------------------------------------------------- beautiful photos (Wikimedia Commons, free licences)
UA = {"User-Agent": "VangashtBot/1.0 (https://vangasht.com; instagram content bot)"}

def _get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()

VAN_WORDS = ("lake van", "van gölü", "van golu", "lake_van", "akdamar", "akhtamar", "aghtamar", "ahtamar", "van province",
             "van, turkey", "van (turkey)", "van fortress", "van kalesi", "fortress of van", "muradiye", "hoşap", "hosap", "hoshap",
             "van cat", "van kedisi", "turkish van", "erek", "süphan", "suphan", "edremit", "tushpa", "tuşba", "tusba", "ipekyolu",
             "gevaş", "gevas", "çaldıran", "caldiran", "van city", "van ili", "province of van")

NOT_PHOTO = ("satellite", "sentinel", "copernicus", "landsat", "nasa", "iss0", "from space", "astronaut", "earth observatory",
             "map", "harita", "karte", "diagram", "plan of", "drawing", "engraving", "postcard", "1900", "19th century")

def commons_candidates(query, used):
    import html as _h, re as _re
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": "6", "gsrlimit": "40",
        "gsrsearch": f"filetype:bitmap {query} Van Turkey", "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": "1600"})
    pages = json.loads(_get(url)).get("query", {}).get("pages", {}).values()
    out = []
    for pg in pages:
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}).get("value") or "").strip()
        okl = lic.upper().startswith(("CC BY", "CC-BY", "CC0")) or "public domain" in lic.lower()
        if not okl or "NC" in lic.upper() or "ND" in lic.upper():
            continue
        if ii.get("width", 0) < 1500 or ii.get("height", 0) < 1000 or pg["title"] in used or not ii.get("thumburl"):
            continue
        about = (pg["title"] + " " + _re.sub(r"<[^>]+>", " ", _h.unescape((md.get("ImageDescription", {}).get("value") or "")))
                 + " " + (md.get("Categories", {}).get("value") or "")).lower()
        if not any(k in about for k in VAN_WORDS):
            continue   # only photos that are really from Van (no Alps or Himalaya)
        if any(k in about for k in NOT_PHOTO):
            continue   # no satellite / space / map images: they look bad on a post
        artist = _re.sub(r"<[^>]+>", "", _h.unescape(md.get("Artist", {}).get("value") or "")).strip()[:40] or "Wikimedia Commons"
        out.append({"title": pg["title"], "url": ii["thumburl"], "credit": f"{artist} · {lic}"})
    random.shuffle(out)
    return out

def claude_pick(cands, topic, k):
    """Let Claude look at small previews and choose the most beautiful, Instagram-worthy photos for the topic."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or len(cands) <= k:
        return list(range(min(k, len(cands))))
    content = []
    for i, c in enumerate(cands):
        try:
            small = _get(c["url"].replace("/1600px-", "/400px-"), 30)
            content += [{"type": "text", "text": f"عکس {i}"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(small).decode()}}]
        except Exception:
            pass
    content.append({"type": "text", "text": (
        f"موضوع پست: {topic}\nاز بین این عکس‌ها {k} عکسِ زیبا، چشم‌گیر و حرفه‌ای (نور خوب، رنگ زنده، ترکیب‌بندی قوی، بدون نوشته و واترمارک، "
        f"بدون صورت واضح آدم‌ها، تار و تاریخی و سیاه‌سفید نباشد) را که به موضوع می‌خورد انتخاب کن. "
        f"عکس باید حتماً از شهر یا استان وان ترکیه باشد (دریاچهٔ وان، آکدامار، قلعهٔ وان، مرادیه، گربهٔ وان…)؛ کوه‌های آلپ، هیمالیا یا جاهای دیگر را هرگز انتخاب نکن. عکس ماهواره‌ای، عکس از فضا، نقشه یا عکس تاریک شب را هم انتخاب نکن. "
        f'فقط JSON: {{"pick": [شماره‌ها به ترتیب بهترین]}}')})
    body = json.dumps({"model": AI_MODEL, "max_tokens": 200, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = "".join(b.get("text", "") for b in json.load(r).get("content", []))
        picks = [int(x) for x in json.loads(txt[txt.find("{"): txt.rfind("}") + 1])["pick"] if 0 <= int(x) < len(cands)]
        return list(dict.fromkeys(picks))[:k] or list(range(k))
    except Exception as e:
        print("! photo picking by AI failed, taking the first ones:", e)
        return list(range(k))

def pick_photos(key, topic, k, st, query=None):
    """Returns up to k (path, credit) pairs of fresh, beautiful Van photos; tops up with our own Van photos."""
    used = set(st.get("photos_used", []))
    q = query or COMMONS_Q.get(key) or COMMONS_Q["lake"]
    try:
        cands = commons_candidates(q, used)[:9]
        if len(cands) < k:
            cands += [c for c in commons_candidates(COMMONS_Q["lake"], used) if c["title"] not in {x["title"] for x in cands}][: 9 - len(cands)]
    except Exception as e:
        print("! could not search photos:", e)
        cands = []
    res = []
    dl = ROOT / "dl"; dl.mkdir(exist_ok=True)
    for i in claude_pick(cands, topic, k):
        c = cands[i]
        try:
            f = dl / f"photo-{len(res)}-{abs(hash(c['title'])) % 10**8}.jpg"
            from PIL import Image
            import io as _io
            im = Image.open(_io.BytesIO(_get(c["url"]))).convert("RGB")
            im.save(f, "JPEG", quality=90)
            res.append((f, c["credit"]))
            st.setdefault("photos_used", []).append(c["title"])
        except Exception as e:
            print("! photo download failed:", e)
    st["photos_used"] = st.get("photos_used", [])[-300:]
    for loc in ["akdamar", "lake", "fortress", "muradiye", "hosap", "cat"]:   # top up with our own Van photos, never random places
        if len(res) >= k:
            break
        if not any(str(r[0]).endswith(f"{loc}.jpg") for r in res):
            res.append((A / f"{loc}.jpg", PHOTOS[loc]))
    print(f"photos: {len(res)} picked for '{topic}'")
    return res

# ---------------------------------------------------------------- carousel slides
def slide_html(sl, i, n, photo, v):
    body = fill(sl.get("body", ""), v).replace("\n", "<br>")
    head = f"""<div style="display:flex;align-items:center;gap:22px"><span style="background:#f2ad3d;color:#12222a;font-weight:900;font-size:56px;border-radius:50%;width:104px;height:104px;display:grid;place-items:center">{fa(i)}</span>
<span style="font-size:30px;opacity:.85;font-weight:800">{fa(i)} از {fa(n)}</span></div>
<h1 style="font-size:92px;font-weight:900;line-height:1.2;margin:28px 0 24px;text-shadow:0 4px 24px rgba(0,0,0,.5)">{hl(sl, v)}</h1>
<p style="font-size:50px;font-weight:700;line-height:1.55;text-shadow:0 2px 14px rgba(0,0,0,.6)">{body}</p>"""
    if photo:
        return f"""<div class="bg" style="background-image:url({b64(photo[0], "image/jpeg")})"></div>
<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(8,30,38,.10) 0%,rgba(8,30,38,.25) 35%,rgba(8,30,38,.92) 72%)"></div>{brand()}
<div style="position:absolute;right:70px;left:70px;bottom:150px">{head}</div>
<div style="position:absolute;left:70px;bottom:62px;font-size:34px;font-weight:900;color:#f2ad3d">ورق بزن ←</div><div class="cr">عکس: {photo[1]}</div>"""
    return f"""<div class="teal"></div>{brand()}<div style="position:absolute;right:70px;left:70px;top:330px">{head}</div>
<div style="position:absolute;left:70px;bottom:62px;font-size:34px;font-weight:900;color:#f2ad3d">ورق بزن ←</div>"""

def cta_html(it, v):
    cta = fill(it.get("cta") or "سیوش کن که تو سفر یادت نره", v)
    return f"""<div class="teal"></div>{brand()}<div style="position:absolute;right:70px;left:70px;top:330px;text-align:center">
<div style="font-size:120px;line-height:1">🔖</div>
<h1 style="font-size:78px;font-weight:900;line-height:1.3;margin:30px 0 24px">{cta}</h1>
<p style="font-size:42px;font-weight:600;line-height:1.6">برای همسفرت هم بفرست 💌<br>سؤال داری؟ تو کامنت بپرس</p>
<p class="url" style="margin-top:60px;font-size:54px">vangasht.com</p>
<p style="font-size:36px;font-weight:800;margin-top:18px">واتس‌اپ <span dir=ltr>{v['wa']}</span></p></div>"""

def render_post(it, v, st, day):
    """Single image or a carousel (cover + 3-5 slides + CTA). Returns list of file names in out/."""
    slides = it.get("slides") if it.get("format") == "carousel" else None
    if slides and not (2 <= len(slides) <= 6):
        slides = None
    want = str(it.get("id", "")).startswith("ai:") and it.get("photo") != "suite" and (it["kind"] == "photo" or slides)
    photos = pick_photos(it.get("photo", "lake"), it.get("topic", it["title"]), (1 + len(slides)) if slides else 1, st) if want else []
    if photos:
        it["photo_path"], it["credit"] = photos[0]
        it["kind"] = "photo"
    files = []
    f0 = OUT / f"{day}-post.jpg"
    render_html((photo_html if it["kind"] == "photo" else design_html)(it, 1350, v).replace(
        '<p class="url" style="margin-top:28px">vangasht.com</p>',
        '<p class="url" style="margin-top:28px">' + ("ورق بزن ←" if slides else "vangasht.com") + '</p>'), 1080, 1350, f0)
    files.append(f0.name)
    if slides:
        n = len(slides)
        for i, sl in enumerate(slides, 1):
            f = OUT / f"{day}-post-{i}.jpg"
            render_html(slide_html(sl, i, n, photos[i] if i < len(photos) else None, v), 1080, 1350, f)
            files.append(f.name)
        f = OUT / f"{day}-post-cta.jpg"
        render_html(cta_html(it, v), 1080, 1350, f)
        files.append(f.name)
    return files

# ---------------------------------------------------------------- animated rates story (video)
FLAGS = {"TRY": "🇹🇷", "IRT": "🇮🇷", "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧"}
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

def rates_rows(d):
    R = {r["code"]: r for r in d.get("rates", [])}
    rows = []
    if "TRY" in R:
        rows.append(("TRY", "لیر ترکیه", "تومان", R["TRY"]))
    for c in ("USD", "EUR"):
        if c in R:
            rows.append((c, NAMES[c], "لیر", R[c]))
    if "GBP" in R:
        rows.append(("GBP", NAMES["GBP"], "لیر", R["GBP"]))
    return rows[:4]

def rates_layer_html(d, v, show):
    """One transparent 1080x1920 layer of the rates story; `show` = which part is visible
    ('head', 'row0'..'rowN', 'foot') so ffmpeg can fade them in one after another."""
    now = dt.datetime.now(TR)
    vis = lambda k: "visible" if (show == "all" or show == k) else "hidden"
    rows = ""
    for i, (code, name, unit, r) in enumerate(rates_rows(d)):
        rows += f"""<div style="visibility:{vis(f'row{i}')};display:grid;grid-template-columns:1fr 210px 210px;align-items:center;gap:18px;padding:26px 0;border-bottom:2px solid rgba(255,255,255,.14)">
<div style="display:flex;align-items:center;gap:22px"><div style="width:86px;height:86px;border-radius:50%;overflow:hidden;display:grid;place-items:center;box-shadow:0 0 0 4px rgba(255,255,255,.85);flex-shrink:0"><span style="font-size:104px;line-height:1">{FLAGS[code]}</span></div>
<span style="font-size:50px;font-weight:800">{name}</span></div>
<div style="text-align:center"><div style="font-size:56px;font-weight:900">{num(r['buy'])}</div><div style="font-size:24px;opacity:.75">{unit}</div></div>
<div style="text-align:center"><div style="font-size:56px;font-weight:900;color:#f2ad3d">{num(r['sell'])}</div><div style="font-size:24px;opacity:.75">{unit}</div></div></div>"""
    return f"""<div style="position:absolute;inset:0;color:#fff;text-shadow:0 3px 18px rgba(0,0,0,.55)">
<div style="visibility:{vis('head')};position:absolute;top:250px;left:0;right:0;text-align:center">
<div style="font:700 64px Georgia,serif;direction:ltr">{now.day} {EN_MONTHS[now.month - 1]} {now.year}</div>
<div style="font-size:52px;font-weight:800;margin-top:10px">{WEEKDAYS[now.weekday()]} {jalali(now.date())}</div>
<div style="display:inline-block;margin-top:34px;background:#f2ad3d;color:#12222a;text-shadow:none;font-size:40px;font-weight:900;border-radius:20px;padding:10px 34px">نرخ امروز صرافی وان گشت</div></div>
<div style="position:absolute;top:620px;left:70px;right:70px">
<div style="visibility:{vis('head')};display:grid;grid-template-columns:1fr 210px 210px;gap:18px;font-size:34px;font-weight:800;opacity:.85"><span></span><span style="text-align:center">خرید ما</span><span style="text-align:center">فروش ما</span></div>
{rows}</div>
<div style="visibility:{vis('foot')};position:absolute;bottom:230px;left:0;right:0;text-align:center">
<div style="display:inline-flex;align-items:center;gap:16px;background:#fff;color:#0d5b6f;text-shadow:none;border-radius:60px;padding:22px 48px;font-size:46px;font-weight:900">💱 خرید و فروش ارز · <span dir=ltr>vangasht.com</span></div>
<div style="font-size:34px;font-weight:700;margin-top:26px">💳 کارتخوان ایرانی در دفتر · واتس‌اپ <span dir=ltr>{v['wa']}</span></div></div>
<div style="visibility:{vis('foot')};position:absolute;bottom:90px;left:0;right:0;display:flex;justify-content:center">{brand().replace('right:48px;top:44px', 'position:static')}</div></div>"""

def rates_assets(st):
    """Background video/photo + song (+ clip info) for the rates story: Drive folder "S2 ..." (or the old "Rates"), each used in turn."""
    return folder_assets("S2", st, full=True)

def layered_video(layers, bg, bg_video, song, st, dst, T, info=None):
    """Story video: background video (looped) or photo (slow zoom), darkened; transparent HTML layers fade in one
    after another; music = `song`, else the Drive "Music" folder, else a soft generated pad."""
    import subprocess
    ff = ffmpeg_bin()
    if not ff:
        raise RuntimeError("ffmpeg not available")
    work = ROOT / "dl"; work.mkdir(exist_ok=True)
    pngs = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        for i, html in enumerate(layers):
            pg.set_content(f"<html dir=rtl><head><meta charset=utf-8><style>{css()}html,body{{background:transparent}}body{{width:1080px;height:1920px}}</style></head><body>{html}</body></html>")
            pg.wait_for_timeout(250)
            o = work / f"layer-{i}.png"; pg.screenshot(path=str(o), omit_background=True); pngs.append(o)
        b.close()
    if bg_video:
        cmd = [ff, "-y", "-stream_loop", "-1", "-t", str(T), "-i", str(bg)]
        base = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,"
    else:
        cmd = [ff, "-y", "-loop", "1", "-i", str(bg)]
        base = f"[0:v]scale=1300:2300:force_original_aspect_ratio=increase,crop=1300:2300,setsar=1,zoompan=z='min(zoom+0.0006,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={T*30}:s=1080x1920:fps=30,"
    cov = cover_png(info, "cover-story")
    if cov and not bg_video:   # a photo with our own mark: no slow zoom, so the label stays exactly on the mark
        cmd = [ff, "-y", "-loop", "1", "-t", str(T), "-i", str(bg)]
        base = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,"
    for o in pngs:
        cmd += ["-loop", "1", "-t", str(T), "-i", str(o)]
    f = (base + "eq=brightness=-0.06:saturation=1.15,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.30:t=fill,fade=in:st=0:d=0.6[b0];")
    if cov:
        cmd += ["-loop", "1", "-t", str(T), "-i", str(cov)]
        f = f.replace("[b0];", "[b00];") + f"[{1 + len(pngs)}:v]format=rgba[cv];[b00][cv]overlay=0:0[b0];"
    last = "b0"
    for i in range(len(pngs)):
        st_ = 0.8 + i * 0.7
        f += f"[{i+1}:v]format=rgba,fade=in:st={st_:.2f}:d=0.5:alpha=1,fade=out:st={T-0.8}:d=0.6:alpha=1[l{i}];[{last}][l{i}]overlay=0:0[b{i+1}];"
        last = f"b{i+1}"
    f += f"[{last}]format=yuv420p[out]"
    n_in = 1 + len(pngs) + (1 if cov else 0)
    if song == "KEEP" and bg_video:   # the background video already has music -> keep it
        f += f";[0:a]atrim=0:{T},afade=t=in:st=0:d=0.5,afade=t=out:st={T-1.5}:d=1.5[aout]"
        tracks = None
    else:
        tracks = [song] if song and song != "KEEP" else music_tracks(st)
    if tracks is None:
        pass
    elif tracks:
        cmd += music_input(tracks, st)
        f += f";[{n_in}:a]atrim=0:{T},afade=t=in:st=0:d=1,afade=t=out:st={T-2}:d=2,volume=0.9[aout]"
    else:
        pad = "+".join(f"0.06*sin(2*PI*{hz}*t)" for hz in (110, 164.81, 220, 261.63, 329.63)) + "+0.025*sin(2*PI*392*t)*(0.5+0.5*sin(2*PI*0.25*t))"
        cmd += ["-f", "lavfi", "-t", str(T), "-i", f"aevalsrc='({pad})*(0.7+0.3*sin(2*PI*0.1*t))':s=44100"]
        f += f";[{n_in}:a]lowpass=f=1800,aecho=0.8:0.7:400|700:0.25|0.18,afade=t=in:st=0:d=2,afade=t=out:st={T-2.5}:d=2.5,volume=3.2[aout]"
    cmd += ["-filter_complex", f, "-map", "[out]", "-map", "[aout]", "-t", str(T), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError("ffmpeg failed: " + r.stderr[-500:])

def rates_video(d, v, st, dst):
    """25 s story (RATES_SECONDS) with music: a slow zoom over a beautiful Van photo, darkened, with the date, each rate row and the footer fading in."""
    # your own background videos/photos + songs from the Drive folder "S2" (or "Rates"), used in turn
    bg, bg_video, rates_song, info = rates_assets(st)
    if not bg:
        ph = pick_photos(random.choice(["lake", "akdamar", "edremit", "suphan", "city"]), "منظرهٔ زیبای وان برای پس‌زمینهٔ استوری نرخ ارز", 1, st)
        bg, bg_video = (ph[0][0] if ph else A / "akdamar.jpg"), False
    parts = ["head"] + [f"row{i}" for i in range(len(rates_rows(d)))] + ["foot"]
    layered_video([rates_layer_html(d, v, k) for k in parts], bg, bg_video, rates_song, st, dst, int(os.environ.get("RATES_SECONDS", "25")), info)
    print("animated rates story ready")

# ---------------------------------------------------------------- Reels: short edited videos from real footage
# Footage, in this order: 1) your own videos/photos in the Drive sub-folder "Reels" (also videos you got
# PERMISSION to repost: put the page name in the file name, e.g. "@vanbuyuksehir65 akdamar.mp4" -> it is credited),
# 2) free Pexels / Pixabay videos (PEXELS_KEY or PIXABAY_KEY secret, free accounts), 3) beautiful Van photos with a slow zoom.
REEL_W, REEL_H, FPS = 1080, 1920, 30

def vid_duration(ff, f):
    import subprocess, re
    r = subprocess.run([ff, "-i", str(f)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0

def drive_list(parent, key):
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
        {"q": f"'{parent}' in parents and trashed=false", "orderBy": "createdTime", "pageSize": 300, "key": key,
         "fields": "files(id,name,mimeType,createdTime,size)"})
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r).get("files", [])

def drive_reel_files(code=None):
    if code:   # the story's / posts' own folder (S3, S7, P ...), else the old "Reels" folder
        return folder_files(code, "visual")
    key, folder = os.environ.get("GDRIVE_KEY"), os.environ.get("GDRIVE_FOLDER")
    if not key or not folder:
        return []
    try:
        sub = [f for f in drive_list(folder, key) if f["mimeType"] == "application/vnd.google-apps.folder" and f["name"].strip().lower() == "reels"]
        if not sub:
            print("no 'Reels' folder in Drive yet"); return []
        return [f for f in drive_list(sub[0]["id"], key) if f["mimeType"].startswith(("video/", "image/"))]
    except Exception as e:
        print("! could not read the Drive Reels folder:", str(e)[:200]); return []

def drive_download(f):
    key = os.environ.get("GDRIVE_KEY")
    ext = Path(f["name"]).suffix.lower() or (".mp4" if f["mimeType"].startswith("video/") else ".mp3" if f["mimeType"].startswith("audio/") else ".jpg")
    dl = ROOT / "dl"; dl.mkdir(exist_ok=True)
    local = dl / ("r_" + f["id"] + ext)
    if not local.exists():
        with urllib.request.urlopen(f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&key={key}", timeout=600) as r, open(local, "wb") as w:
            while chunk := r.read(1 << 20):
                w.write(chunk)
    if ext == ".heic":
        from PIL import Image, ImageOps
        from pillow_heif import register_heif_opener; register_heif_opener()
        jpg = local.with_suffix(".jpg"); ImageOps.exif_transpose(Image.open(local)).convert("RGB").save(jpg, quality=92); local = jpg
    return local

def credit_of(name):
    import re
    m = re.search(r"@([A-Za-z0-9_.]{2,30})", name)
    return "@" + m.group(1).rstrip(".") if m else None

def pexels_video(query, used):
    key = os.environ.get("PEXELS_KEY")
    if not key:
        return None
    try:
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 20})
        req = urllib.request.Request(url, headers={"Authorization": key, **UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            vids = json.load(r).get("videos", [])
    except Exception as e:
        print("! Pexels search failed:", str(e)[:150]); return None
    for v_ in vids:
        if str(v_["id"]) in used or not (4 <= v_.get("duration", 0) <= 60):
            continue
        files = [f for f in v_.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height", 0) >= 1280 and f.get("width", 1) < f.get("height", 0)]
        if not files:
            continue
        f = min(files, key=lambda f: abs(f["height"] - 1920))
        dst = ROOT / "dl" / f"px_{v_['id']}.mp4"; dst.parent.mkdir(exist_ok=True)
        try:
            dst.write_bytes(_get(f["link"], timeout=180))
        except Exception:
            continue
        return dst, str(v_["id"])
    return None

def clip_vision_pick(thumbs, scene):
    """Claude looks at clip previews and picks one that is real (not CGI/AI), fits the scene and does not show another country's city. -1 = none."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not thumbs:
        return 0 if thumbs else -1
    content = []
    for i, u in enumerate(thumbs):
        try:
            content += [{"type": "text", "text": f"ویدیو {i}"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(_get(u, 30)).decode()}}]
        except Exception:
            pass
    content.append({"type": "text", "text": (
        f"این‌ها پیش‌نمایش ویدیوهای رایگان برای یک صحنه از ریلز پیج گردشگری «وان ترکیه» است. متن صحنه: «{scene}».\n"
        "یکی را انتخاب کن که: ۱) فیلم واقعی باشد، نه انیمیشن/CGI/تصویر ساخت هوش مصنوعی یا منظرهٔ خیالی و اغراق‌شده؛ "
        "۲) هیچ شهر، ساختمان یا منظرهٔ شناختنیِ کشور دیگری (مثل شهرهای اروپایی، ونیز، دریاچه‌های ایتالیا، کوه‌های آلپ، ساحل گرمسیری) نشان ندهد — "
        "صحنه‌های عمومی مثل سطح آب، موج، غروب، قایق، چای، صبحانه، دست‌ها، جاده، آسمان، کوه خشک و ساده خوب است؛ ۳) زیبا و حرفه‌ای باشد و به متن بخورد. "
        'اگر هیچ‌کدام مناسب نیست -1 بده. فقط JSON: {"pick": شماره}')})
    body = json.dumps({"model": AI_MODEL, "max_tokens": 60, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            txt = "".join(b.get("text", "") for b in json.load(r).get("content", []))
        n = int(json.loads(txt[txt.find("{"): txt.rfind("}") + 1])["pick"])
        return n if -1 <= n < len(thumbs) else -1
    except Exception as e:
        print("! clip check failed:", str(e)[:120]); return -1

def pixabay_video(query, used, scene=""):
    """Free Pixabay videos (PIXABAY_KEY secret). Only real film footage that Claude approved for a Van page."""
    key = os.environ.get("PIXABAY_KEY")
    if not key:
        return None
    try:
        url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": key, "q": query[:90], "per_page": 40, "safesearch": "true", "video_type": "film"})
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            hits = json.load(r).get("hits", [])
    except Exception as e:
        print("! Pixabay search failed:", str(e)[:150]); return None
    ok = []
    for h in hits:
        if "x" + str(h["id"]) in used or h.get("type", "film") != "film" or not (4 <= h.get("duration", 0) <= 60):
            continue
        vs = h.get("videos", {})
        c = [vs.get(k) for k in ("large", "medium") if vs.get(k, {}).get("url") and vs[k].get("height", 0) >= 1080 and vs[k].get("size", 0) < 80_000_000]
        if c:
            thumb = next((vs[k].get("thumbnail") for k in ("small", "medium", "tiny", "large") if vs.get(k, {}).get("thumbnail")), None)
            ok.append((h, c[0], thumb))
    random.shuffle(ok)
    ok = ok[:6]
    if not ok:
        return None
    if all(t for _, _, t in ok):
        i = clip_vision_pick([t for _, _, t in ok], scene or query)
        if i < 0:
            print(f"  no suitable clip for '{query}'"); return None
        ok = [ok[i]]
    h, f, _ = ok[0]
    dst = ROOT / "dl" / f"pb_{h['id']}.mp4"; dst.parent.mkdir(exist_ok=True)
    try:
        dst.write_bytes(_get(f["url"], timeout=300))
    except Exception:
        return None
    return dst, "x" + str(h["id"])

AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg")

# ---------------------------------------------------------------- one Drive sub-folder per story / for the posts
# Inside the Drive folder "Vangasht Stories" make sub-folders whose names START with the code, e.g.
#   "S1 صبح بخیر", "S2 نرخ ارز", "S3 ولاگ ظهر", "S4 سایت", "S5 تورها", "S6 سؤال", "S7 ولاگ عصر",
#   "S8 جاذبه", "S9 پست های امروز", "S10 شب بخیر", "P پست ها"
# and put that story's videos, photos and songs in it. Each story uses only its own folder, one file at a time, in turn.
# If a folder is missing or empty, the old folders below are used, then free Van photos / the "Music" folder.
FOLDER_ALIASES = {"S2": ("rates", "نرخ"), "S3": ("reels",), "S7": ("reels",), "P": ("reels",)}
_SUBS, _LS = None, {}

def drive_subfolders():
    global _SUBS
    if _SUBS is None:
        _SUBS = []
        key, folder = os.environ.get("GDRIVE_KEY"), os.environ.get("GDRIVE_FOLDER")
        if key and folder:
            try:
                _SUBS = [f for f in drive_list(folder, key) if f["mimeType"] == "application/vnd.google-apps.folder"]
            except Exception as e:
                print("! could not read the Drive folders:", str(e)[:150])
    return _SUBS

def folder_code(name):
    """'S1 صبح بخیر' -> 'S1', 's 10' -> 'S10', 'P پست ها' / 'Posts' / 'پست ها' -> 'P' (Persian digits work too)."""
    n = name.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).upper()
    m = re.match(r"S\s*-?\s*(\d{1,2})(?!\d)", n)
    if m:
        return f"S{int(m.group(1))}"
    if re.match(r"P(?![A-Z0-9])", n) or n.startswith(("POST", "پست")):
        return "P"
    return None

def _is_vis(x):
    return x["mimeType"].startswith(("video/", "image/")) and int(x.get("size") or 0) < 300_000_000

def _is_aud(x):
    return x["mimeType"].startswith("audio/") or Path(x["name"]).suffix.lower() in AUDIO_EXT

def folder_files(code, kind="visual"):
    """Files ("visual" = videos+photos, "audio" = songs) of the folder for `code`; own folder first, then its old alias.
    Each file gets f["_own"] = True when it comes from the story's own folder."""
    key = os.environ.get("GDRIVE_KEY")
    subs = drive_subfolders()
    own = [f for f in subs if folder_code(f["name"]) == code]
    alias = [f for f in subs if f["name"].strip().lower() in FOLDER_ALIASES.get(code, ())]
    for fo in own + alias:
        try:
            if fo["id"] not in _LS:
                _LS[fo["id"]] = drive_list(fo["id"], key)
            got = [dict(x, _own=fo in own) for x in _LS[fo["id"]] if (_is_vis(x) if kind == "visual" else _is_aud(x))]
        except Exception as e:
            print(f"! could not read Drive folder '{fo['name']}':", str(e)[:150]); continue
        if got:
            print(f"{code}: {len(got)} {kind} file(s) in Drive folder '{fo['name']}'")
            return got
    return []

# Instagram pages that belong to US: their names/watermarks on a clip are covered with "vangasht.com" (comma list, without @)
OWN_PAGES = [x.strip().lstrip("@") for x in os.environ.get("OWN_PAGES", "vangasht.van,vangasht.com,van.gasht.turkiye").split(",") if x.strip()]

def has_own_music(f, name=""):
    """Does a video already carry music / loud sound? File name wins: "music"/"موزیک"/"آهنگ" = keep, "mute"/"بی صدا" = replace.
    Otherwise measured: mean loudness above CLIP_MUSIC_DB (raw phone footage is usually quieter)."""
    import subprocess
    n = name.lower()
    if any(w in n for w in ("music", "موزیک", "آهنگ", "اهنگ", "#sound")):
        return True
    if any(w in n for w in ("mute", "بی صدا", "بیصدا", "بی‌صدا", "#nosound")):
        return False
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-t", "40", "-i", str(f), "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return bool(m) and float(m.group(1)) > float(os.environ.get("CLIP_MUSIC_DB", "-27"))

def clip_info(path, is_video, fid, name, st):
    """Claude looks at 3 frames of your file (once; the answer is saved): text already written on it, a greeting,
    another page's watermark/logo; plus whether it already has music. Cached in state.json -> clip_info."""
    cache = st.setdefault("clip_info", {})
    if fid in cache and cache[fid].get("v") == 4:
        return cache[fid]
    import subprocess
    info = {"text": "", "greeting": "", "other_page": False, "page": "", "music": False, "own_boxes": [], "ar": 0.5625, "scene": "", "place": "", "text_pos": "", "dur": 0, "v": 4}
    if is_video:
        try:
            info["music"] = has_own_music(path, name)
        except Exception as e:
            print("! sound check failed:", str(e)[:100])
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        ff = ffmpeg_bin(); work = ROOT / "dl"; frames = []
        L = vid_duration(ff, path) if is_video else 0
        info["dur"] = L
        for i, t in enumerate([L * x for x in (0.05, 0.2, 0.4, 0.6, 0.8, 0.95)] if is_video and L else [0]):
            o = work / f"ci_{fid}_{i}.jpg"
            subprocess.run([ff, "-y", *(["-ss", f"{t:.2f}"] if is_video else []), "-i", str(path), "-frames:v", "1", "-vf", "scale=720:-2", str(o)], capture_output=True)
            if o.exists():
                frames.append(o)
        if frames:
            from PIL import Image
            w_, h_ = Image.open(frames[0]).size; info["ar"] = w_ / h_
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(fr.read_bytes()).decode()}} for fr in frames]
        content.append({"type": "text", "text": (
            f"این چند فریم از یک ویدیو/عکس است که پیج اینستاگرام ما می‌خواهد در استوری بگذارد. پیج‌های خود ما فقط دقیقاً این‌هاست: {', '.join('@' + x for x in OWN_PAGES)}. "
            "هر آیدی یا برند دیگری حتی اگر شبیه باشد مال پیج دیگری است. همهٔ گوشه‌ها و لبه‌ها را با دقت نگاه کن و بگو:\n"
            "text: هر نوشته‌ای که روی تصویر اضافه شده (کپشن، تیتر، جمله، شعر، خوشنویسی، استیکر متنی) — حتی کم‌رنگ، کوچک یا فقط در یکی از فریم‌ها؛ نه تابلوی مغازه یا نوشتهٔ طبیعی محیط؛ اگر نیست خالی.\n"
            "text_pos: نوشتهٔ اضافه‌شده بیشتر کجای تصویر است: \"top\" یا \"middle\" یا \"bottom\" (اگر نیست خالی).\n"
            "scene: یک جملهٔ کوتاه فارسی (حداکثر ۱۲۰ حرف) که دقیقاً بگوید در ویدیو چه دیده می‌شود (مکان، آدم‌ها، حال و هوا، روز یا شب).\n"
            "place: اگر با اطمینان یکی از جاهای شناخته‌شدهٔ استان وان است (مثل جزیرهٔ آکدامار، قلعهٔ وان، آبشار مرادیه، قلعهٔ هوشاپ، ساحل ادرمیت، جزیرهٔ چارپاناک، کوه اِرِک، خانهٔ گربه‌های وان) نامش را بنویس؛ "
            "از نوشتهٔ روی ویدیو هم کمک بگیر؛ اگر مطمئن نیستی خالی.\n"
            "greeting: اگر نوشته صبح‌بخیر است \"morning\"، اگر شب‌بخیر است \"night\"، وگرنه خالی.\n"
            "other_page: true اگر واترمارک، لوگو، امضا یا آیدی/اسم هر پیج یا برند دیگری روی تصویر هست (حتی کوچک و کم‌رنگ در گوشه)، "
            "یا اگر ضبط صفحهٔ اینستاگرام/تیک‌تاکِ یک پیج دیگر است؛ page = همان اسم یا آیدی. آرم یا آیدی پیج‌های خود ما other_page نیست.\n"
            "own_boxes: جای هر آرم، آیدی یا واترمارکِ پیج‌های خود ما، و اگر ضبط صفحهٔ اینستاگرامِ پیج خودمان است جای نوار بالای صفحه (اسم کاربری، زمان، نوار پیشرفت) — "
            "هر کدام به شکل [x, y, w, h] با عددهای ۰ تا ۱ نسبت به عرض و ارتفاع تصویر (x,y = گوشهٔ بالا-چپ). کمی بزرگ‌تر از خود نوشته بگیر. اگر نیست [].\n"
            'فقط JSON: {"text": "", "text_pos": "", "scene": "", "place": "", "greeting": "", "other_page": false, "page": "", "own_boxes": []}')})
        body = json.dumps({"model": AI_MODEL, "max_tokens": 400, "messages": [{"role": "user", "content": content}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                txt = "".join(b.get("text", "") for b in json.load(r).get("content", []))
            a = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            clean_ = lambda x, n: str(x or "")[:n].replace("<", "").replace(">", "").replace("آق‌تامار", "آکدامار")
            info.update(scene=clean_(a.get("scene"), 140), place=clean_(a.get("place"), 50),
                        text_pos=str(a.get("text_pos") or "") if a.get("text") else "")
            info.update(text=str(a.get("text") or "")[:120].replace("<", "").replace(">", ""), greeting=str(a.get("greeting") or ""),
                        other_page=bool(a.get("other_page")), page=str(a.get("page") or "")[:40])
            boxes = []
            for b_ in (a.get("own_boxes") or [])[:4]:
                try:
                    x, y, w, h = [min(1.0, max(0.0, float(z))) for z in b_[:4]]
                    if w > 0.01 and h > 0.005 and w * h < 0.25:
                        boxes.append([x, y, w, h])
                except Exception:
                    pass
            info["own_boxes"] = boxes
            if info["other_page"] and any(o.lower() in info["page"].lower().lstrip("@") for o in OWN_PAGES):
                info["other_page"] = False   # it is one of our own pages
        except Exception as e:
            print("! clip check failed:", str(e)[:120])
            return info   # not cached: try again next time
    cache[fid] = info
    if len(cache) > 600:
        for k in list(cache)[:100]:
            del cache[k]
    print(f"clip check {name}: place='{info['place']}' scene='{info['scene'][:60]}' text='{info['text'][:40]}' other_page={info['other_page']} {info['page']} music={info['music']} own marks={len(info['own_boxes'])}")
    return info

def cover_png(info, name="cover"):
    """Transparent 1080x1920 PNG that hides the name/watermark of OUR OWN other pages with a "vangasht.com" label
    (the clip is scaled to fill 1080x1920 and centre-cropped, so the boxes are mapped the same way). None if nothing to cover."""
    boxes = (info or {}).get("own_boxes") or []
    if not boxes:
        return None
    ar = info.get("ar") or 0.5625
    W, H = (1920 * ar, 1920) if ar >= 1080 / 1920 else (1080, 1080 / ar)
    ox, oy = (W - 1080) / 2, (H - 1920) / 2
    html = ""
    for x, y, w, h in boxes:
        px, py, pw, ph = x * W - ox, y * H - oy, w * W, h * H
        pad = max(14, ph * 0.35)
        px, py, pw, ph = max(0, px - pad), max(0, py - pad), min(1080, pw + 2 * pad), max(56, ph + 2 * pad)
        fs = max(22, min(44, ph * 0.45))
        html += (f'<div style="position:absolute;left:{px:.0f}px;top:{py:.0f}px;width:{pw:.0f}px;height:{ph:.0f}px;background:rgba(11,47,58,.94);'
                 f'border-radius:{min(ph / 2, 40):.0f}px;display:flex;align-items:center;justify-content:center;color:#fff;font:700 {fs:.0f}px Georgia,serif;'
                 f'direction:ltr;white-space:nowrap;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.35)">vangasht<span style="color:#f2ad3d">.com</span></div>')
    out = ROOT / "dl" / f"{name}.png"; out.parent.mkdir(exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1920})
        pg.set_content(f"<html><head><meta charset=utf-8><style>{css()}html,body{{background:transparent}}body{{width:1080px;height:1920px}}</style></head><body>{html}</body></html>")
        pg.wait_for_timeout(150); pg.screenshot(path=str(out), omit_background=True); b.close()
    print(f"covering {len(boxes)} mark(s) of our own pages with vangasht.com")
    return out

def usable(f, info, st):
    """Files with another page's watermark/logo are NOT used (we don't remove or cover other people's marks).
    Exception: you got permission and put the page name in the file name, e.g. "@vanbuyuksehir65 akdamar.mp4" -> it is credited."""
    if info.get("other_page") and not credit_of(f["name"]):
        print(f"! skipped '{f['name']}': it has another page's mark ({info.get('page') or '?'}). Use your own footage, or put @page in the name if you have permission.")
        sk = st.setdefault("skipped_files", {}); sk[f["name"]] = info.get("page") or "?"
        return False
    return True

def lru_take(files, st):
    """The file used least recently (then the oldest), downloaded -> (local path, drive file) or None."""
    if not files:
        return None
    last = st.setdefault("rates_last", {})
    f = min(files, key=lambda x: (last.get(x["id"], ""), x["createdTime"]))
    last[f["id"]] = dt.datetime.now(TR).isoformat(timespec="minutes")
    try:
        return drive_download(f), f
    except Exception as e:
        print("! download failed:", str(e)[:120]); return None

def folder_assets(code, st, full=False):
    """-> (background path or None, background is a video?, song path or None[, clip info]) from the folder of `code`.
    If the video already has music, no song is added (its own sound is kept)."""
    vis = folder_files(code, "visual")
    v_, info = None, {}
    for _ in range(min(5, len(vis))):
        got = lru_take(vis, st)
        if not got:
            break
        is_v = got[1]["mimeType"].startswith("video/")
        info = clip_info(got[0], is_v, got[1]["id"], got[1]["name"], st)
        if usable(got[1], info, st):
            v_ = got; break
        vis = [x for x in vis if x["id"] != got[1]["id"]]; info = {}
    is_v = bool(v_ and v_[1]["mimeType"].startswith("video/"))
    keep = is_v and info.get("music")
    a_ = None if keep else lru_take(folder_files(code, "audio"), st)
    print(f"{code} background:", v_[1]["name"] if v_ else "-", "| song:", "own sound of the video" if keep else (a_[1]["name"] if a_ else "-"))
    out = ((v_[0] if v_ else None), is_v, ("KEEP" if keep else (a_[0] if a_ else None)))
    return out + (info,) if full else out

def music_tracks(st):
    """Royalty-free songs: the Drive sub-folder "Music" (easiest: upload from your phone) plus the repo's music/ folder."""
    tracks = [m for m in (ROOT / "music").glob("*") if m.suffix.lower() in AUDIO_EXT] if (ROOT / "music").is_dir() else []
    key, folder = os.environ.get("GDRIVE_KEY"), os.environ.get("GDRIVE_FOLDER")
    if key and folder:
        try:
            sub = [f for f in drive_list(folder, key) if f["mimeType"] == "application/vnd.google-apps.folder" and f["name"].strip().lower() == "music"]
            if sub:
                files = [f for f in drive_list(sub[0]["id"], key) if f["mimeType"].startswith("audio/") or Path(f["name"]).suffix.lower() in AUDIO_EXT]
                # least recently used first, so the same song does not repeat day after day
                last = st.get("music_last", {})
                files.sort(key=lambda f: last.get(f["id"], ""))
                for f in files[:3]:
                    d_ = ROOT / "dl" / ("m_" + f["id"] + (Path(f["name"]).suffix.lower() or ".mp3")); d_.parent.mkdir(exist_ok=True)
                    if not d_.exists():
                        with urllib.request.urlopen(f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&key={key}", timeout=300) as r:
                            d_.write_bytes(r.read())
                    tracks.append(d_)
                print(f"music: {len(files)} song(s) in Drive/Music")
        except Exception as e:
            print("! could not read Drive/Music:", str(e)[:150])
    return tracks

def music_input(tracks, st):
    """Pick the song used least recently; skip a long intro so the reel starts on the lively part."""
    last = st.setdefault("music_last", {})
    t = min(tracks, key=lambda m: last.get(m.stem.replace("m_", ""), ""))
    last[t.stem.replace("m_", "")] = dt.datetime.now(TR).isoformat(timespec="minutes")
    L = vid_duration(ffmpeg_bin(), t)
    start = 12 if L > 90 else (6 if L > 45 else 0)
    print("music:", t.name, f"(from {start}s)")
    return ["-ss", str(start), "-stream_loop", "-1", "-i", str(t)]

def reel_overlay_html(kind, text, hl_word, v, i=0, n=0, credit=None):
    t = html_escape(text)
    if hl_word and hl_word in text:
        t = t.replace(html_escape(hl_word), f'<span style="color:#f2ad3d">{html_escape(hl_word)}</span>', 1)
    cr = f'<div style="position:absolute;left:40px;bottom:70px;font-size:28px;color:#fff;opacity:.85;direction:ltr">🎥 {html_escape(credit)}</div>' if credit else ""
    if kind == "pin":
        return f"""<div style="position:absolute;left:0;right:0;top:330px;text-align:center;font-size:64px;font-weight:900;letter-spacing:4px;color:#fff;text-shadow:0 3px 16px rgba(0,0,0,.75);direction:ltr">📍 VAN</div>
<div style="position:absolute;left:0;right:0;top:1150px;text-align:center;font-size:30px;font-weight:700;color:rgba(255,255,255,.8);text-shadow:0 2px 8px rgba(0,0,0,.7);direction:ltr">@vangasht.van</div>{cr}"""
    if kind == "hook":
        return f"""<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.0) 35%,rgba(0,0,0,.55) 100%)"></div>{brand()}
<div style="position:absolute;left:60px;right:60px;top:1060px;text-align:center"><h1 style="font-size:104px;line-height:1.25;font-weight:900;margin:0;color:#fff;text-shadow:0 6px 30px rgba(0,0,0,.6)">{t}</h1></div>{cr}"""
    if kind == "end":
        return f"""<div style="position:absolute;inset:0;background:rgba(9,38,46,.78)"></div>
<div style="position:absolute;left:70px;right:70px;top:620px;text-align:center;color:#fff">
<img src="{b64(C / 'logo.svg', 'image/svg+xml')}" style="width:150px;height:170px;background:#fff;border-radius:34px;padding:16px">
<h1 style="font-size:76px;line-height:1.35;font-weight:900;margin:40px 0 24px">{t}</h1>
<p style="font-size:50px;font-weight:900;color:#f2ad3d;margin:0;direction:ltr">vangasht.com</p>
<p style="font-size:40px;font-weight:700;margin:18px 0 0;opacity:.95">واتس‌اپ: <span dir=ltr>{v['wa']}</span></p></div>"""
    return f"""<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 50%,rgba(0,0,0,.6) 100%)"></div>{brand()}
<div style="position:absolute;left:60px;right:60px;bottom:250px;text-align:center"><span style="display:inline-block;background:rgba(9,38,46,.82);color:#fff;font-size:68px;line-height:1.4;font-weight:900;padding:22px 40px;border-radius:30px;box-shadow:0 10px 40px rgba(0,0,0,.35)">{t}</span></div>{cr}"""

def html_escape(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def reel_segment(ff, src, is_video, dur, overlay_png, dst, start=0.0, cover=None):
    import subprocess
    grade = "eq=contrast=1.06:saturation=1.15:brightness=0.01"
    if is_video:
        inp = ["-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src)]
        base = f"[0:v]scale={REEL_W}:{REEL_H}:force_original_aspect_ratio=increase,crop={REEL_W}:{REEL_H},fps={FPS},{grade},setsar=1[bg]"
    else:
        inp = ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(src)]
        frames = int(dur * FPS)
        zoom_in = random.random() < 0.6
        z = "min(1.0+0.0009*on,1.12)" if zoom_in else "max(1.12-0.0009*on,1.0)"
        if cover:
            z = "1.0"   # keep the label exactly on our own page's mark
        base = (f"[0:v]scale=-2:2400,crop='min(iw,1350)':2400,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={REEL_W}x{REEL_H}:fps={FPS},"
                f"{grade},setsar=1[bg]")
    extra = []
    if cover:
        base = base.replace("[bg]", "[bg0]") + f";[2:v]format=rgba[cv];[bg0][cv]overlay=0:0[bg]"
        extra = ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(cover)]
    f = base + f";[1:v]format=rgba,fade=in:st=0.25:d=0.35:alpha=1[ov];[bg][ov]overlay=0:0,format=yuv420p[out]"
    cmd = [ff, "-y", *inp, "-loop", "1", "-t", f"{dur:.2f}", "-i", str(overlay_png), *extra, "-filter_complex", f, "-map", "[out]", "-an",
           "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", str(FPS), str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError("segment failed: " + r.stderr[-400:])

def assign_drive(thumbs, scenes):
    """For each scene pick one of your own Drive files that fits it (or -1). Each file is used at most once."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return list(range(min(len(thumbs), len(scenes)))) + [-1] * max(0, len(scenes) - len(thumbs))
    content = []
    for i, t in enumerate(thumbs):
        content += [{"type": "text", "text": f"فایل {i}"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(Path(t).read_bytes()).decode()}}]
    sc = "\n".join(f"صحنه {i}: {t}" for i, t in enumerate(scenes))
    content.append({"type": "text", "text": (
        "این‌ها فایل‌های خود پیج «وان گشت» (گردشگری و صرافی در وان ترکیه) است و این‌ها صحنه‌های یک ریلز:\n" + sc + "\n"
        "برای هر صحنه فایلی را انتخاب کن که واقعاً به متن آن صحنه بخورد و زیبا باشد. قوانین: سلفی یا عکسی که صورت یک آدم سوژهٔ اصلی است را انتخاب نکن؛ "
        "طرح تبلیغاتی یا عکس پر از نوشته را انتخاب نکن؛ عکسی که معلوم است مال وان نیست (مثل جنگل برفی یا شهر دیگر) را برای صحنه‌ای دربارهٔ وان انتخاب نکن؛ "
        "هر فایل حداکثر یک بار. اگر برای صحنه‌ای فایل مناسب نیست -1 بگذار (ما برایش ویدیوی دیگری پیدا می‌کنیم). "
        'فقط JSON: {"assign": [شمارهٔ فایل برای صحنهٔ ۰، برای صحنهٔ ۱، ...]}')})
    body = json.dumps({"model": AI_MODEL, "max_tokens": 120, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = "".join(b.get("text", "") for b in json.load(r).get("content", []))
        a = [int(x) for x in json.loads(txt[txt.find("{"): txt.rfind("}") + 1])["assign"]][:len(scenes)]
        seen, out = set(), []
        for x in a + [-1] * (len(scenes) - len(a)):
            out.append(x if 0 <= x < len(thumbs) and x not in seen else -1); seen.add(x)
        return out
    except Exception as e:
        print("! matching your files failed:", str(e)[:120]); return [-1] * len(scenes)

def make_reel(plan, v, st, dst, style="text", folder=None):
    """style "text" = tips with captions; "vlog" = real footage, fast cuts, only a 📍 VAN pin (like van.gasht.turkiye stories).
    plan = {"hook", "hl", "scenes": [{"text", "hl", "query"}], "cta"} -> edited 1080x1920 Reel with music."""
    import subprocess
    ff = ffmpeg_bin()
    if not ff:
        raise RuntimeError("ffmpeg not available")
    work = ROOT / "dl"; work.mkdir(exist_ok=True)
    used = st.setdefault("reel_used", {})
    drive = drive_reel_files(folder)
    # own / permitted footage first: least used, then oldest
    drive.sort(key=lambda f: (used.get("d:" + f["id"], 0), f["createdTime"]))
    if style == "vlog":
        scenes = [dict(x, kind="pin") for x in plan["scenes"][:8]]
    else:
        scenes = [{"text": plan["hook"], "hl": plan.get("hl", ""), "query": plan["scenes"][0].get("query", "Lake Van"), "kind": "hook"}]
        scenes += [dict(x, kind="scene") for x in plan["scenes"][:5]]
    clips, credits, px_used, covers = [], set(), set(st.get("pexels_used", [])), {}
    # look at up to 10 of your Drive files and let AI match them to the scenes (no selfies / ads / unrelated shots)
    pool = []
    for f in [f for f in drive if int(f.get("size") or 0) < 200_000_000][:10]:
        try:
            loc = drive_download(f); is_v = f["mimeType"].startswith("video/")
            th = work / f"th_{f['id']}.jpg"
            subprocess.run([ff, "-y", *(["-ss", "1"] if is_v else []), "-i", str(loc), "-frames:v", "1", "-vf", "scale=400:-2", str(th)], capture_output=True)
            info = clip_info(loc, is_v, f["id"], f["name"], st)
            if th.exists() and usable(f, info, st):
                pool.append((loc, is_v, credit_of(f["name"]), "d:" + f["id"], th, info))
        except Exception as e:
            print("! Drive download failed:", str(e)[:120])
    own_pool = [f for f in drive if f.get("_own") and int(f.get("size") or 0) < 200_000_000][:10]
    if style == "vlog" and len(pool) >= 3 and len(own_pool) >= 3:
        # the story's own folder: everything in it is meant for this story -> use the files in turn, no AI filtering
        scenes = scenes[:len(pool)]
        assign = list(range(len(scenes)))
    else:
        assign = assign_drive([p_[4] for p_ in pool], [sc["text"] for sc in scenes]) if pool else [-1] * len(scenes)
    print("your Drive files used for scenes:", assign)
    for i, sc in enumerate(scenes):
        src = None
        if i < len(assign) and 0 <= assign[i] < len(pool):
            src = pool[assign[i]][:4]
            covers[i] = cover_png(pool[assign[i]][5], f"cover-{i}")
            if pool[assign[i]][5].get("text") and sc["kind"] == "scene":
                sc = dict(sc, kind="pin")   # the clip already has words on it -> don't write over them
        if not src:
            q = sc.get("query") or "Turkey lake"
            got = (pexels_video(q, px_used) or pixabay_video(q, px_used, sc["text"])
                   or pixabay_video(" ".join(q.split()[:2]), px_used, sc["text"]) or pixabay_video("lake water sunset", px_used, sc["text"]))
            if got:
                px_used.add(got[1]); src = (got[0], True, None, "p:" + got[1])
        if not src:
            ph = pick_photos(random.choice(list(COMMONS_Q)), sc["text"], 1, st)
            seen_src = {str(c[1]) for c in clips}
            if ph and str(ph[0][0]) not in seen_src:
                src = (ph[0][0], False, None, "c")
            else:   # never repeat the same picture inside one reel
                left = [A / x for x in ("lake.jpg", "fortress.jpg", "muradiye.jpg", "hosap.jpg", "akdamar.jpg", "cat.jpg") if str(A / x) not in seen_src]
                src = (random.choice(left or [A / "lake.jpg"]), False, None, "c")
        clips.append((sc, *src))
    # overlays (transparent PNGs drawn with the browser so Persian text is perfect)
    from playwright.sync_api import sync_playwright
    over = []
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": REEL_W, "height": REEL_H})
        items = [(sc["kind"], sc["text"], sc.get("hl", ""), cr) for sc, _, _, cr, _ in clips] + ([] if style == "vlog" else [("end", plan.get("cta") or "سیوش کن و برای همسفرت بفرست", "", None)])
        for i, (k, t, h, cr) in enumerate(items):
            pg.set_content(f"<html dir=rtl><head><meta charset=utf-8><style>{css()}html,body{{background:transparent}}body{{width:{REEL_W}px;height:{REEL_H}px}}</style></head><body>{reel_overlay_html(k, t, h, v, credit=cr)}</body></html>")
            pg.wait_for_timeout(200)
            o = work / f"ov{i}.png"; pg.screenshot(path=str(o), omit_background=True); over.append(o)
        b.close()
    segs, durs = [], []
    for i, (sc, src, is_vid, cr, uid) in enumerate(clips):
        dur = 2.2 if sc["kind"] == "pin" else (2.6 if sc["kind"] == "hook" else 3.0)
        start = 0.0
        if is_vid:
            L = vid_duration(ff, src)
            if L and L > dur + 0.5:
                start = random.uniform(min(0.8, L * 0.1), max(min(0.8, L * 0.1), L - dur - 0.3))
            elif L:
                dur = max(1.5, L - 0.1)
        seg = work / f"seg{i}.mp4"
        reel_segment(ff, src, is_vid, dur, over[i], seg, start, covers.get(i))
        segs.append(seg); durs.append(dur)
        if cr: credits.add(cr)
        if uid.startswith("d:"): used[uid] = used.get(uid, 0) + 1
    # end card over the last clip's frame, blurred (not for the vlog style)
    endbg = work / "endbg.jpg"
    if style == "vlog":
        endbg = None   # blurred frame of the first clip, without any text on it
    first_src, first_vid = clips[0][1], clips[0][2]
    if endbg is not None:
      subprocess.run([ff, "-y", *(["-ss", "1"] if first_vid else []), "-i", str(first_src), "-frames:v", "1",
                    "-vf", f"scale={REEL_W}:{REEL_H}:force_original_aspect_ratio=increase,crop={REEL_W}:{REEL_H},boxblur=30:2", str(endbg)], capture_output=True)
      if not endbg.exists():
          endbg = A / "lake.jpg"
      seg = work / "seg_end.mp4"; reel_segment(ff, endbg, False, 2.8, over[-1], seg); segs.append(seg); durs.append(2.8)
    # join with short crossfades
    X = 0.35
    cmd = [ff, "-y"]
    for sgm in segs:
        cmd += ["-i", str(sgm)]
    f, last, off = "", "0:v", 0.0
    for i in range(1, len(segs)):
        off += durs[i - 1] - X
        f += f"[{last}][{i}:v]xfade=transition={'fade' if style == 'vlog' else random.choice(['fade', 'smoothleft', 'fadeblack', 'circleopen'])}:duration={X}:offset={off:.2f}[x{i}];"
        last = f"x{i}"
    T = sum(durs) - X * (len(segs) - 1)
    f += f"[{last}]format=yuv420p[vout]"
    song = lru_take(folder_files(folder, "audio"), st) if folder else None
    tracks = [song[0]] if song else music_tracks(st)
    n = len(segs)
    if tracks:
        cmd += music_input(tracks, st)
        f += f";[{n}:a]atrim=0:{T:.2f},afade=t=in:st=0:d=0.5,afade=t=out:st={T-1.5:.2f}:d=1.5,volume=0.9[aout]"
    else:
        pad = "+".join(f"0.06*sin(2*PI*{hz}*t)" for hz in (130.81, 196, 261.63, 329.63)) + "+0.03*sin(2*PI*392*t)*(0.5+0.5*sin(2*PI*2*t))"
        cmd += ["-f", "lavfi", "-t", f"{T:.2f}", "-i", f"aevalsrc='({pad})':s=44100"]
        f += f";[{n}:a]lowpass=f=2200,aecho=0.8:0.6:300|600:0.2|0.15,afade=t=in:st=0:d=1,afade=t=out:st={T-1.5:.2f}:d=1.5,volume=3[aout]"
    cmd += ["-filter_complex", f, "-map", "[vout]", "-map", "[aout]", "-t", f"{T:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError("reel join failed: " + r.stderr[-500:])
    st["pexels_used"] = list(px_used)[-400:]
    print(f"reel ready: {T:.1f}s, {len(clips)} scenes, credits: {credits or '-'}")
    return T, sorted(credits)

def ai_reel(d, v, st):
    recent = [x["topic"] for x in st.get("ai_log", [])[-20:]]
    shape = ('{"topic": "موضوع کوتاه برای ثبت", "hook": "جملهٔ قلاب ۳ تا ۶ کلمه که آدم را نگه دارد", "hl": "یک کلمه از هوک برای رنگ طلایی", '
             '"scenes": [{"text": "متن روی صحنه، حداکثر ۷ کلمه، خودمانی", "hl": "", "query": "2-3 English stock-video words for a GENERIC scene with no recognizable city, e.g. lake water waves / tea glass / breakfast table / boat sunset / mountain road"}, ... دقیقاً ۵ صحنه], '
             '"cta": "جملهٔ کارت آخر، حداکثر ۷ کلمه", "caption": "کپشن ۵ تا ۱۰ خط کوتاه، خط اول قلاب، آخر دعوت به کامنت/سیو + لینک vangasht.com؛ بدون هشتگ"}')
    prompt = (f"{ai_context(d, v)}\n\nموضوع‌های اخیر (تکرار نکن): {'، '.join(recent) or '—'}\n\n{inspo_text(st)}"
              "یک ریلز ۱۵ تا ۲۰ ثانیه‌ای اینستاگرام برای امروز طراحی کن، با همان ریتم و سبک پست‌های موفق بالا (به‌خصوص ریلزها): "
              "هوک قوی در ۲ ثانیهٔ اول، هر صحنه یک نکتهٔ کوتاه، پایان با دعوت به سیو/اشتراک. متن‌ها باید روی ویدیو خوانا و کوتاه باشند. "
              f"شکل خروجی (فقط JSON):\n{shape}")
    it = claude(prompt)
    try:
        assert isinstance(it, dict) and it.get("hook") and len(it.get("scenes", [])) >= 3 and len(it.get("caption", "")) > 30
        clean = lambda x, n: str(x or "")[:n].replace("<", "").replace(">", "")
        it["hook"], it["hl"], it["cta"] = clean(it["hook"], 60), clean(it.get("hl"), 25), clean(it.get("cta"), 60)
        it["scenes"] = [{"text": clean(x.get("text"), 60), "hl": clean(x.get("hl"), 25), "query": clean(x.get("query"), 60)} for x in it["scenes"][:5] if isinstance(x, dict) and x.get("text")]
        it["caption"] = it["caption"].replace("<", "").replace(">", "")
        it["id"] = "ai:" + clean(it.get("topic") or it["hook"], 40)
        print("AI reel plan:", it["id"])
        return it
    except Exception as e:
        st["ai_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "slot": "reel", "error": AI_ERROR or ("unusable reel plan: " + repr(e)[:150])}
        return None

REEL_DAYS = {int(x) for x in os.environ.get("REEL_DAYS", "0,1,2,3,4,5,6").split(",") if x.strip().isdigit()}   # Mon=0 ... Sun=6

VLOG_SCENES = [("خیابان‌های شلوغ و نورانی وان در شب", "city street night lights"), ("آدم‌ها در حال قدم زدن در خیابان خرید", "people walking shopping street night"),
               ("غذای خیابانی و آشپز در حال پخت", "street food cooking grill"), ("کافه و رستوران با نور گرم", "cafe terrace night lights"),
               ("ساحل دریاچهٔ وان و آب", "lake shore waves sunset"), ("جادهٔ کوهستانی و طبیعت اطراف وان", "mountain road drive"),
               ("بازار و مغازه‌های رنگارنگ", "bazaar shops colorful"), ("صبحانهٔ مفصل ترکی روی میز", "turkish breakfast table"),
               ("قلعهٔ قدیمی و چشم‌انداز شهر", "old castle city view"), ("غروب آفتاب روی دریاچه", "sunset over lake")]

def build_vlog_story(v, st, day, code="S3"):
    """14:00 story in the style of van.gasht.turkiye: real Van footage, fast cuts, only a 📍 VAN pin, music."""
    try:
        k = st.get("vlog_i", 0) % len(VLOG_SCENES)
        picks = (VLOG_SCENES[k:] + VLOG_SCENES[:k])[:8]
        st["vlog_i"] = k + 3
        plan = {"id": "vlog", "scenes": [{"text": t, "hl": "", "query": q} for t, q in picks]}
        mp4 = ROOT / "dl" / f"{day}-vlog-{code}.mp4"; mp4.parent.mkdir(exist_ok=True)
        T, credits = make_reel(plan, v, st, mp4, style="vlog", folder=code)
        return {"video": str(mp4.relative_to(ROOT)), "reel": False, "caption": None, "item": "vlog", "file": None}
    except Exception as e:
        print("! vlog story failed:", str(e)[:400])
        st["reel_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "slot": code, "error": str(e)[:400]}
        return None

def build_reel(d, v, st, day, test):
    """Plan with AI, edit the video, save a cover. Returns job fields, or None (then a carousel is made instead)."""
    try:
        plan = ai_reel(d, v, st)
        if not plan:
            return None
        mp4 = (OUT if test else ROOT / "dl") / f"{day}-reel.mp4"; mp4.parent.mkdir(exist_ok=True)
        T, credits = make_reel(plan, v, st, mp4, folder="P")
        import subprocess
        subprocess.run([ffmpeg_bin(), "-y", "-ss", "1.2", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(OUT / f"{day}-post.jpg")], capture_output=True)
        tags = "#وان #وان_ترکیه #سفر_به_وان #صرافی_وان #سوئیت_وان #تور_وان #خرید_از_وان #ترکیه #VanTurkey #Van #VanGölü #وان_گشت"
        cap = fill(plan["caption"], v) + ("\n\n🎥 ویدیو: " + " ".join(credits) if credits else "") + "\n\n" + tags
        if test:
            (OUT / f"{day}-caption.txt").write_text(cap)
        return {"video": str(mp4.relative_to(ROOT)), "reel": True, "caption": cap, "item": plan["id"], "file": None, "done": True if test else None}
    except Exception as e:
        print("! reel failed, making a carousel instead:", str(e)[:400])
        st["reel_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "error": str(e)[:400]}
        return None

# ---------------------------------------------------------------- designed video stories (S1, S4, S5, S6, S8, S10)
CARD_SLOTS = ("s1", "s4", "s5", "s6", "s8", "s10")
POST_SLOTS = ("p1", "p2")
ATTRACTIONS = [("جزیرهٔ آکدامار", "Akdamar island", "گواش، حدود ۴۵ کیلومتری وان", "جزیره‌ای وسط دریاچهٔ وان با کلیسای صلیب مقدس از قرن دهم میلادی و نقش‌برجسته‌های سنگی."),
               ("قلعهٔ وان", "Van Fortress", "توشبا، نزدیک مرکز شهر", "قلعه‌ای باستانی روی صخره‌ای بلند کنار دریاچه، از دوران اورارتو؛ غروبش معروف است."),
               ("آبشار مرادیه", "Muradiye waterfall", "مرادیه، حدود ۸۰ کیلومتری وان", "آبشاری خروشان با پل معلق چوبی و رستوران‌های کنار رودخانه."),
               ("قلعهٔ هوشاپ", "Hosap castle", "گورپینار، جنوب شرقی وان", "قلعه‌ای قرون وسطایی روی تپه، با دیوارها و برج‌های سنگی."),
               ("کوه اِرِک", "Erek mountain Van", "شرق شهر وان", "کوهی بلند که از دامنه‌اش منظرهٔ کامل شهر و دریاچه پیداست."),
               ("ساحل اِدرِمیت", "Edremit Van lake", "اِدرِمیت، جنوب شهر وان", "ساحلی آرام کنار دریاچه با کافه‌ها و رستوران‌ها؛ برای قدم زدن و غروب عالی است."),
               ("خانهٔ گربه‌های وان", "Turkish Van cat", "دانشگاه یوزونجو ییل", "گربه‌های معروف وان با چشم‌های دو رنگ؛ نماد شهر وان."),
               ("کوه سوبهان", "Mount Suphan", "شمال دریاچهٔ وان", "دومین کوه بلند ترکیه با قله‌ای برفی که از ساحل دریاچه پیداست."),
               ("خیابان صبحانهٔ وان", "Van breakfast", "مرکز شهر وان", "خیابانی پر از صبحانه‌خانه با صبحانهٔ معروف وانی: پنیر، عسل، کره و ده‌ها مزه.")]

def _fa(x):
    t = ((x or {}).get("fa") if isinstance(x, dict) else x) or ""
    return t.replace("آق‌تامار", "آکدامار").replace("آق تامار", "آکدامار")

def card_subject(code, d, st):
    """What today's S4 / S5 / S8 story is about (in turn, from the site's own content)."""
    def turn(items, k):
        if not items:
            return None
        i = st.get(k, 0) % len(items); st[k] = i + 1
        return items[i]
    if code == "s4":
        L = [("صرافی وان گشت", "خرید و فروش ارز با کارتخوان ایرانی (عضو شتاب) در دفتر وان گشت؛ نرخ روز همیشه در سایت.", "vangasht.com/sarafi-van"),
             ("سوئیت‌های مبلهٔ وان", "سوئیت‌های تمیز و مبله برای خانواده‌ها و گروه‌ها: " + "، ".join(_fa(x.get("name")) for x in d.get("suites", [])[:5]), "vangasht.com/suite-van"),
             ("کارت تخفیف وان گشت", "۱۰٪ تخفیف در مغازه‌های طرف قرارداد با اسکن QR و جمع کردن امتیاز.", "vangasht.com"),
             ("راهنمای سفر به وان", "همه چیز دربارهٔ شهر وان: جاهای دیدنی، خرید، غذا و رفت‌وآمد.", "vangasht.com/rahnama-van"),
             ("جاهای دیدنی وان", "معرفی جاذبه‌ها و تورهای گردشگری وان.", "vangasht.com/gardeshgari-van")]
        L += [(_fa(x.get("title")), _fa(x.get("excerpt")), "vangasht.com/majale") for x in d.get("posts", []) if x.get("published", 1) and _fa(x.get("title"))]
        t, desc, url = turn(L, "s4_i")
        return {"name": t, "info": desc, "url": url, "query": None}
    if code == "s5":
        T = [(_fa(x.get("title")), _fa(x.get("short")) + " " + _fa(x.get("desc"))[:400], f"vangasht.com/tour/{x.get('slug')}", x.get("photo"))
             for x in d.get("tours", []) if _fa(x.get("title"))]
        T = T or [("تور جزیرهٔ آکدامار", "قایق تا جزیره و کلیسای هزارساله، با هماهنگی فارسی.", "vangasht.com/tour", "akdamar"),
                  ("تور کشتی تفریحی دریاچهٔ وان", "گشت دریاچه با کشتی بزرگ و تماشای غروب.", "vangasht.com/tour", "lake"),
                  ("تور آبشار مرادیه", "آبشار خروشان و پل معلق، یک نیم‌روز در طبیعت.", "vangasht.com/tour", "muradiye")]
        t, desc, url, ph = turn(T, "s5_i")
        return {"name": t, "info": desc, "url": url, "photo": ph if ph in COMMONS_Q else "lake"}
    if code == "s8":
        F = [(_fa(x.get("title")), (x.get("title") or {}).get("en", "") if isinstance(x.get("title"), dict) else "", _fa(x.get("meta")), _fa(x.get("desc")))
             for x in d.get("fun", []) if _fa(x.get("title"))]
        names = {f[0] for f in F}
        F += [a for a in ATTRACTIONS if a[0] not in names and not any(a[1].split()[0].lower() in (f[1] or "").lower() for f in F)]
        t, en, meta, desc = turn(F, "s8_i")
        return {"name": t, "info": f"{meta}. {desc}", "url": "vangasht.com/gardeshgari-van", "query": (en + " Van") if en and "van" not in en.lower() else (en or "Lake Van")}
    return {}

CARD_ASK = {
    "s1": "استوری «صبح بخیر» ساعت ۹ صبح. tag = «صبح بخیر» یا خالی. title یک سلام صبحگاهی ظریف و تازه (هر روز متفاوت)، sub یک جملهٔ انرژی‌بخش و صمیمی دربارهٔ سفر یا یک روز خوب در وان، "
          "lines صفر یا یک مورد: یک پیشنهاد کوچک برای امروز (مثلاً صبحانهٔ وانی، قدم زدن کنار دریاچه). دربارهٔ هوای امروز ادعا نکن. foot خالی.",
    "s4": "استوری معرفی و تبلیغ سایت vangasht.com؛ موضوع امروز را از اطلاعات زیر بگیر و جذاب معرفی کن تا مخاطب برود سایت را ببیند. tag = «تو سایت ما»، "
          "lines دقیقاً ۳ مزیت یا نکتهٔ کوتاه، foot یک جملهٔ دعوت کوتاه مثل «لینک تو بیو 👆 سر بزن».",
    "s5": "استوری تبلیغ تور گردشگری؛ تور امروز را از اطلاعات زیر معرفی کن، هیجان‌انگیز ولی صادق. tag = «تور وان گشت»، lines خالی (ویدیو باید دیده شود؛ همه‌چیز را در title و یک sub کوتاه بگو). "
          "قیمت ننویس. foot مثل «برای رزرو تو دایرکت پیام بده».",
    "s6": "استوری تعاملی که مخاطب جواب بدهد (جوابش به دایرکت ما می‌رسد). یکی از این قالب‌ها را انتخاب کن و با روزهای قبل فرق داشته باشد: "
          "«آیا می‌دانید؟» (یک دانستنی مطمئن و جالب دربارهٔ وان و در آخر یک سؤال)، «کیا دوست دارن…؟»، «این یا اون؟» (دو گزینه در lines)، «حدس بزن…»، «سؤال از شما» (مثلاً اولین کارت تو وان چیه؟). "
          "سؤال باید دربارهٔ همان چیزی باشد که در ویدیوی پس‌زمینه دیده می‌شود. tag = نام قالب، title خود سؤال یا دانستنی کوتاه، sub توضیح یا ادامهٔ سؤال، lines صفر تا دو مورد (برای «این یا اون؟» دو گزینه با ایموجی ۱️⃣ و ۲️⃣)، foot خالی.",
    "s8": "استوری معرفی یک جاذبهٔ وان (جاذبهٔ امروز پایین آمده). tag = «جاذبهٔ امروز وان»، title نام جاذبه با یک صفت جذاب، sub یک جمله دربارهٔ اینکه چرا باید دید، "
          "lines خالی (ویدیو باید دیده شود). sub حداکثر ۷۰ حرف و فقط چیزهای مطمئن. foot مثل «سیوش کن برای سفرت 🔖».",
    "s10": "استوری «شب بخیر» ساعت ۱۱ شب. tag خالی. title یک شب‌بخیر ظریف و شاعرانه (مثل حس «شبتون نیلوفری» یا «تاریکی به کام»، ولی هر شب جملهٔ تازه)، "
           "sub یک جملهٔ آرام و دلنشین دربارهٔ شب، دریاچه یا سفر، lines خالی. foot خالی.",
}
MINIMAL_SLOTS = ("s1", "s5", "s8", "s10")
CARD_STYLE = ("سبک نوشتن: کوتاه، ظریف و دلنشین، مثل پیج‌های حرفه‌ای و شیک؛ کمی ادبی و شاعرانه ولی ساده و امروزی. "
              "نمونهٔ حس و حال (عیناً تکرار نکن، هر روز جملهٔ تازه بساز): «شبتون نیلوفری»، «تاریکی به کام»، «صبحتون به روشنی آب دریاچه»، «یه فنجون چای و یه عالمه آرامش». "
              "از جمله‌های کلیشه‌ای و بی‌مزه مثل «شب بخیر وانی‌ها» یا «صبح بخیر دوستان» پرهیز کن. title حداکثر ۵ کلمه. ایموجی کم و بجا (حداکثر یکی در title).")
CARD_FALLBACK = {
    "s1": [("صبحتون به روشنی دریاچه ☀️", "روشنی", "یه فنجون چای، یه نفس عمیق، یه روز تازه", []),
           ("سلام به صبحی تازه", "تازه", "امروزت پر از اتفاق‌های قشنگ", [["☕", "چای ترکی کنار دریاچه می‌چسبه"]])],
    "s6": [("کیا دوست دارن این روزا وان باشن؟ 🙋", "وان", "جوابتو بفرست، دوست داریم بدونیم 💬", []),
           ("آیا می‌دانید؟ 🤔", "می‌دانید", "دریاچهٔ وان بزرگ‌ترین دریاچهٔ ترکیه است. شما تا حالا دیدینش؟", []),
           ("این یا اون؟", "اون", "کدومو بیشتر دوست داری؟", [["1️⃣", "صبحانهٔ وانی"], ["2️⃣", "غروب کنار دریاچه"]])],
    "s10": [("شبتون نیلوفری 🌙", "نیلوفری", "چراغ‌های ساحل روشنه و شهر آروم خوابیده", []),
            ("تاریکی به کام", "به کام", "خوابت آروم، فردات روشن", [])],
}

def card_content(code, d, v, st, ci=None):
    ci = ci or {}
    clip_text, scene, place = ci.get("text", ""), ci.get("scene", ""), ci.get("place", "")
    subj = card_subject(code, d, st)
    if code == "s8" and (place or scene or clip_text):   # introduce the place the VIDEO shows, so text and picture match
        subj = dict(subj, name=place or (clip_text.split("\n")[0][:60] if clip_text else "همان جایی که در ویدیو دیده می‌شود"),
                    info=f"ویدیو: {scene}. {clip_text}", query=None, url="vangasht.com/gardeshgari-van")
    if code == "s5" and (place or scene):   # pick the tour that fits the video
        tours = [x for x in d.get("tours", []) if _fa(x.get("title"))]
        lst = "\n".join(f"- {x.get('slug')}: {_fa(x.get('title'))} — {_fa(x.get('short'))}" for x in tours)
        subj = {"name": "توری که به این ویدیو می‌خورد", "url": "vangasht.com/tour", "photo": "lake",
                "info": f"ویدیو این را نشان می‌دهد: {place} {scene}\nتورهای ما:\n{lst}\nتوری را انتخاب کن که دقیقاً به همین ویدیو مربوط است و اسلاگش را در فیلد tour بده؛ اگر هیچ‌کدام نمی‌خورد tour خالی و کلی دربارهٔ تورهای وان گشت با حال‌وهوای همین ویدیو بنویس."}
    log = st.setdefault("card_log", {}).setdefault(code, [])
    shape = ('{"topic": "موضوع کوتاه برای ثبت", "tag": "برچسب ۲ تا ۴ کلمه", "title": "تیتر حداکثر ۷ کلمه، خودمانی", "hl": "یک یا دو کلمه از همان تیتر برای رنگ طلایی", '
             '"sub": "یک جمله حداکثر ۹۰ حرف", "lines": [["ایموجی", "حداکثر ۴۵ حرف"], ...], "foot": "حداکثر ۵۰ حرف یا خالی"}')
    info = f"\nموضوع امروز: {subj['name']}\nاطلاعات: {subj['info']}\n" if subj else ""
    if scene or place:
        info += f"\nپس‌زمینهٔ این استوری ویدیویی است که این را نشان می‌دهد: {place + '؛ ' if place else ''}{scene}\nمتن باید دقیقاً با همین ویدیو جور باشد و دربارهٔ چیز دیگری حرف نزند.\n"
    if clip_text:
        info += f"\nروی خود ویدیو از قبل این نوشته هست: «{clip_text}» — آن را تکرار نکن؛ متن ما کوتاه‌تر باشد و کاملش کند.\n"
    shp = shape[:-1] + ', "tour": "اسلاگ تور یا خالی"}' if code == "s5" else shape
    prompt = (f"{ai_context(d, v)}\n\nموضوع‌های اخیر همین استوری (تکرار نکن): {'، '.join(log[-12:]) or '—'}\n\n{inspo_text(st)}"
              f"{CARD_ASK[code]}{info}\n{CARD_STYLE}\nشکل خروجی (فقط JSON):\n{shp}")
    it = claude(prompt)
    clean = lambda x, n: str(x or "")[:n].replace("<", "").replace(">", "").replace("آق‌تامار", "آکدامار").replace("آق تامار", "آکدامار")
    c = None
    try:
        assert isinstance(it, dict) and it.get("title")
        c = {k: clean(it.get(k), n) for k, n in (("tag", 30), ("title", 60), ("hl", 30), ("sub", 110), ("foot", 60))}
        c["lines"] = [[clean(a, 4), clean(b, 60)] for a, b in (it.get("lines") or [])[:3] if b]
        log.append(clean(it.get("topic") or c["title"], 40)); del log[:-20]
        print(f"AI wrote {code}:", c["title"])
    except Exception as e:
        print(f"! AI text for {code} failed, using a simple text:", AI_ERROR or repr(e)[:150])
        if code in CARD_FALLBACK:
            t, h, sub, lines = random.choice(CARD_FALLBACK[code])
            c = {"tag": {"s1": "صبح بخیر", "s6": "سؤال امروز", "s10": "شب بخیر"}[code], "title": t, "hl": h, "sub": sub, "lines": lines, "foot": ""}
        else:
            c = {"tag": {"s4": "تو سایت ما", "s5": "تور وان گشت", "s8": "جاذبهٔ امروز وان"}[code], "title": clean(subj["name"], 60), "hl": "",
                 "sub": clean(subj["info"], 110), "lines": [], "foot": "سیوش کن برای سفرت 🔖" if code == "s8" else "برای اطلاعات بیشتر پیام بده"}
    c["code"], c["subj"] = code, subj
    c["url"] = subj.get("url") if code in ("s4", "s5") else None
    if code == "s5" and isinstance(it, dict) and it.get("tour") and any(str(x.get("slug")) == str(it["tour"]) for x in d.get("tours", [])):
        c["url"] = f"vangasht.com/tour/{it['tour']}"
    if code in MINIMAL_SLOTS:   # let the video be seen: one short title + one line, no boxes
        c["lines"] = []
    c["answer"] = code == "s6"
    c["date"] = code in ("s1", "s10")
    return c

def card_layer_html(c, show, v):
    """One transparent layer of a designed story; `show` = 'head', 'l0'.., 'foot' (or 'all')."""
    vis = lambda k: "visible" if show in ("all", k) else "hidden"
    now = dt.datetime.now(TR)
    date = (f'<div style="font-size:30px;font-weight:600;opacity:.9;margin-bottom:22px;letter-spacing:.5px">{WEEKDAYS[now.weekday()]} {jalali(now.date())}'
            f' · <span dir=ltr>{now.day} {EN_MONTHS[now.month - 1]}</span></div>') if c.get("date") else ""
    lines = "".join(f'<div style="visibility:{vis(f"l{i}")};display:flex;align-items:center;gap:22px;background:rgba(10,30,38,.55);border:2px solid rgba(255,255,255,.22);'
                    f'border-radius:26px;padding:{16 if c.get("compact") else 20}px 30px;margin-top:18px;font-size:{32 if c.get("compact") else 37}px;font-weight:700;text-align:right"><span style="font-size:44px">{e}</span><span>{fill(t, v)}</span></div>'
                    for i, (e, t) in enumerate(c["lines"]))
    if c.get("answer"):
        foot = ('<div style="background:#fff;color:#0d5b6f;text-shadow:none;border-radius:34px;padding:34px 40px;box-shadow:0 18px 50px rgba(0,0,0,.35)">'
                '<div style="font-size:34px;font-weight:800;opacity:.75;margin-bottom:14px">✍️ جوابتو همین پایین بنویس و بفرست</div>'
                '<div style="border:3px dashed rgba(13,91,111,.45);border-radius:22px;padding:26px;font-size:42px;font-weight:700;color:rgba(13,91,111,.55)">جواب شما…</div></div>'
                '<div style="font-size:90px;margin-top:6px;line-height:1">👇</div>')
    else:
        foot = ""
        if c.get("foot"):
            foot += f'<div style="font-size:34px;font-weight:700;margin-bottom:20px">{fill(c["foot"], v)}</div>'
        if c.get("url"):
            foot += f'<div style="display:inline-block;background:#fff;color:#0d5b6f;text-shadow:none;border-radius:60px;padding:16px 40px;font:700 36px Georgia,serif;direction:ltr">{c["url"]}</div>'
        if c["code"] in ("s4", "s5"):
            foot += f'<div style="font-size:28px;font-weight:600;margin-top:18px">💬 واتس‌اپ <span dir=ltr>{v["wa"]}</span></div>'
    sub = f'<p style="font-size:{34 if c.get("compact") else 40}px;font-weight:500;line-height:1.6;margin:22px 0 0;opacity:.95">{fill(c["sub"], v)}</p>' if c.get("sub") else ""
    tag = f'<span class="tag" style="font-size:30px;padding:6px 20px;text-shadow:none">{c["tag"]}</span>' if c.get("tag") else ""
    tsize = (56 if c.get("compact") else 70) if len(c["title"]) < 28 else (48 if c.get("compact") else 60)
    title = f'<h1 style="font-size:{tsize}px;font-weight:800;line-height:1.35;margin:{24 if tag else 0}px 0 0;letter-spacing:-.5px">{hl(c, v)}</h1>' if c.get("title") else ""
    return f"""<div style="position:absolute;inset:0;color:#fff;text-shadow:0 3px 18px rgba(0,0,0,.6)">
<div style="visibility:{vis('head')};position:absolute;top:230px;left:0;right:0;display:flex;justify-content:center">{brand().replace('right:48px;top:44px', 'position:static')}</div>
<div style="position:absolute;left:90px;right:90px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:{dict(top='flex-start', bottom='flex-end').get(c.get('pos'), 'center')};text-align:center;padding:{'400px 0 380px' if c.get('pos') == 'top' else '300px 0 380px'}">
<div style="visibility:{vis('head')}">{date}{tag}{title}{sub}</div>
{lines}
<div style="visibility:{vis('foot')};margin-top:60px">{foot}</div></div></div>"""

def card_story(code, d, v, st, dst):
    """S1/S4/S5/S6/S8/S10: AI text over a video/photo from the story's own Drive folder, layers fading in, with music."""
    bg, bg_video, song, info = folder_assets(code.upper(), st, full=True)
    c = card_content(code, d, v, st, info)
    if info.get("text") and (code in ("s1", "s10") or (info.get("greeting") == "morning" and code == "s1")):
        c.update(title="", sub="", lines=[], tag="")   # the clip already says good morning / good night -> only date + logo
    c["compact"] = bool(info.get("text")) or code in MINIMAL_SLOTS
    c["pos"] = "top" if info.get("text_pos") in ("bottom", "middle") else "bottom" if (info.get("text") or code in MINIMAL_SLOTS) else "center"
    if not bg:
        subj = c["subj"]
        if code == "s8":
            ph = pick_photos("lake", f"عکس زیبا و واقعی از {subj['name']} در وان", 1, st, query=subj.get("query"))
        elif code == "s5":
            ph = pick_photos(subj.get("photo", "lake"), f"عکس زیبا برای تبلیغ {subj['name']}", 1, st)
        elif code == "s4" and "سوئیت" in subj.get("name", ""):
            ph = [(A / "suite.jpg", "")]
        else:
            key = {"s1": random.choice(["lake", "edremit", "suphan"]), "s10": random.choice(["lake", "fortress", "city"])}.get(code, random.choice(["lake", "akdamar", "city", "edremit"]))
            ph = pick_photos(key, "منظرهٔ زیبای وان برای پس‌زمینهٔ استوری" + (" صبحگاهی" if code == "s1" else " شبانه" if code == "s10" else ""), 1, st)
        bg, bg_video = (ph[0][0] if ph else A / "lake.jpg"), False
    parts = ["head"] + [f"l{i}" for i in range(len(c["lines"]))] + ["foot"]
    T = int(os.environ.get("CARD_SECONDS", "15"))
    if bg_video and code in MINIMAL_SLOTS + ("s6",):   # play the whole clip (Instagram stories: max 60 s)
        L = info.get("dur") or vid_duration(ffmpeg_bin(), bg)
        T = int(max(8, min(59, L or T)))
    layered_video([card_layer_html(c, k, v) for k in parts], bg, bg_video, song, st, dst, T, info)
    print(f"{code} story ready:", c["title"])
    return c

def todayposts_layer_html(covers, show, v):
    vis = lambda k: "visible" if show in ("all", k) else "hidden"
    n = len(covers)
    W, H = (420, 620) if n > 1 else (540, 780)
    imgs = "".join(f'<img src="{b64(cv, "image/jpeg")}" style="width:{W}px;height:{H}px;object-fit:cover;border-radius:34px;border:8px solid #fff;'
                   f'box-shadow:0 30px 70px rgba(0,0,0,.55);transform:rotate({(-4, 4)[i % 2] if n > 1 else 0}deg)">' for i, cv in enumerate(covers))
    return f"""<div style="position:absolute;inset:0;color:#fff;text-shadow:0 3px 18px rgba(0,0,0,.6);text-align:center">
<div style="visibility:{vis('head')};position:absolute;top:230px;left:0;right:0;display:flex;justify-content:center">{brand().replace('right:48px;top:44px', 'position:static')}</div>
<div style="visibility:{vis('head')};position:absolute;top:330px;left:60px;right:60px"><span class="tag" style="font-size:40px;text-shadow:none">{'پست‌های امروز' if n > 1 else 'پست امروز'}</span>
<h1 style="font-size:80px;font-weight:900;margin:30px 0 0">{'پست‌های امروز رو دیدین؟' if n > 1 else 'پست امروز رو دیدی؟'} 👀</h1></div>
<div style="visibility:{vis('covers')};position:absolute;top:{640 if n > 1 else 560}px;left:0;right:0;display:flex;justify-content:center;gap:40px">{imgs}</div>
<div style="visibility:{vis('foot')};position:absolute;bottom:330px;left:60px;right:60px">
<div style="display:inline-block;background:#fff;color:#0d5b6f;text-shadow:none;border-radius:60px;padding:22px 50px;font-size:46px;font-weight:900">برو تو پیج و ببین 👆</div>
<div style="font-size:40px;font-weight:700;margin-top:26px">برای همسفرت هم بفرست 💌</div></div></div>"""

def todayposts_story(d, v, st, day, dst):
    """S9 (21:00): shows the covers of today's posts (p1 at 11:30, p2 at 20:00) that were really published."""
    done = {x.get("slot") for x in st.get("log", []) if str(x.get("at", "")).startswith(day)}
    covers = [OUT / f"{day}-{k}-post.jpg" for k in POST_SLOTS if k in done or ("post" in done and k == "p2")]
    covers = [c for c in covers if c.exists()]
    if not covers:
        return None
    bg, bg_video, song, info = folder_assets("S9", st, full=True)
    if not bg:
        from PIL import Image, ImageFilter
        bg = ROOT / "dl" / f"{day}-s9-bg.jpg"; bg.parent.mkdir(exist_ok=True)
        Image.open(covers[-1]).convert("RGB").filter(ImageFilter.GaussianBlur(40)).save(bg, quality=88)
        bg_video = False
    layered_video([todayposts_layer_html(covers, k, v) for k in ("head", "covers", "foot")], bg, bg_video, song, st, dst, int(os.environ.get("CARD_SECONDS", "15")), info)
    print("s9 story ready with", len(covers), "post cover(s)")
    return covers

def newpost_story_html(cover, v):
    """Story that points followers to tonight's new post (the API cannot press Instagram's Repost button)."""
    img = b64(cover, "image/jpeg")
    return f"""<div class="bg" style="background-image:url({img});filter:blur(38px) brightness(.55);transform:scale(1.2)"></div>{brand()}
<div style="position:absolute;left:0;right:0;top:250px;text-align:center"><span class="tag" style="font-size:40px">پست جدید</span></div>
<img src="{img}" style="position:absolute;left:150px;top:390px;width:780px;height:975px;object-fit:cover;border-radius:36px;box-shadow:0 30px 80px rgba(0,0,0,.55);border:8px solid #fff">
<div style="position:absolute;left:60px;right:60px;top:1430px;text-align:center;color:#fff">
<p style="font-size:62px;font-weight:900;margin:0;text-shadow:0 4px 20px rgba(0,0,0,.5)">پست امشب رو دیدی؟ 👆</p>
<p style="font-size:42px;font-weight:700;margin:18px 0 0;opacity:.95">برو صفحه رو ببین و برای همسفرت بفرست</p></div>"""

def _safe(fn, *a):
    """Run one story builder; on any error print it, remember it, and return None (then a simpler story is made)."""
    try:
        return fn(*a)
    except Exception as e:
        print(f"! {fn.__name__} failed:", str(e)[:400])
        st = a[3] if fn is card_story else a[2]
        st["story_error"] = {"at": dt.datetime.now(TR).strftime("%Y-%m-%dT%H:%M"), "step": fn.__name__, "error": str(e)[:400]}
        return None

def render(slot):
    d, st = site(), load_state()
    v = vars_for(d)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.jpg"):  # keep the repo small: images are only needed until Instagram has copied them
        if time.time() - old.stat().st_mtime > 7 * 86400:
            old.unlink()
    day = dt.datetime.now(TR).strftime("%Y-%m-%d")
    slot = {"story1": "s2", "story3": "s3", "story4": "s9", "post": "p2"}.get(slot, slot)   # old names still work
    test = slot in ("test", "testreel")   # test = make a post now, but do NOT publish it
    want_reel = slot == "testreel" or (slot in POST_SLOTS and dt.datetime.now(TR).weekday() in REEL_DAYS)
    if test:
        slot, day = "p2", day + "-test"
    for old in list(OUT.glob("*.mp4")):
        if time.time() - old.stat().st_mtime > 3 * 86400:
            old.unlink()
    tag = f"{day}-{slot}"
    path = OUT / f"{day}-{slot}.jpg"
    vid = ROOT / "dl" / f"{day}-{slot}.mp4"; vid.parent.mkdir(exist_ok=True)
    job = {"slot": slot, "file": path.name, "caption": None, "advance": None, "item": None}
    if slot == "testcards":
        # test only: make every designed story of the day into out/ (nothing is published)
        made = []
        for code in CARD_SLOTS:
            try:
                mp4 = OUT / f"{day}-test-{code}.mp4"
                card_story(code, d, v, st, mp4); made.append(mp4.name)
            except Exception as e:
                print(f"! {code} failed:", str(e)[:400])
        job.update(file=None, video=f"out/{made[0]}" if made else None, item="cards-test", done=True)
        print("TEST ONLY - not published:", made)
    elif slot == "s9" and (got := _safe(todayposts_story, d, v, st, day, vid)):
        job.update(file=None, video=str(vid.relative_to(ROOT)), item="todayposts")
    elif slot in ("s3", "s7") and (reel := build_vlog_story(v, st, day, slot.upper())):
        # a short edited video (real footage + music), like the stories of the inspiration pages
        reel.update(reel=False, caption=None, done=None)
        job.update(reel)
    elif slot in POST_SLOTS and want_reel and (reel := build_reel(d, v, st, tag, test)):
        job.update(reel)
        if not test:
            ai_remember(st, {"id": reel["item"]})
    elif slot in POST_SLOTS:
        it = ai_item("post", d, v, st)
        if not it:
            lib = json.loads((C / "posts.json").read_text())
            it = lib[st["post"] % len(lib)]
            job["advance"] = "post"
        files = render_post(it, v, st, tag)
        job["file"] = files[0]
        if len(files) > 1:
            job["files"] = files
        tags = "#وان #وان_ترکیه #سفر_به_وان #صرافی_وان #سوئیت_وان #تور_وان #خرید_از_وان #ترکیه #VanTurkey #Van #VanGölü #وان_گشت"
        job.update(caption=fill(it["caption"], v) + "\n\n" + tags, item=it["id"])
        if test:
            job.update(done=True, advance=None)
            (OUT / f"{tag}-caption.txt").write_text(job["caption"])
            print("TEST ONLY - not published. Files:", files)
        else:
            ai_remember(st, it)
    elif slot == "testvlog" and (reel := build_vlog_story(v, st, day + "-test", "S3")):
        mp4 = ROOT / reel["video"]; dst_ = OUT / mp4.name; mp4.replace(dst_)
        job.update(file=None, video=str(dst_.relative_to(ROOT)), item="vlog-test", done=True)
        print("TEST ONLY - not published:", dst_.name)
    elif slot == "testrates":
        # test only: make the morning rates video now (from Drive/S2 or Rates) without publishing it
        mp4 = OUT / f"{day}-test-rates.mp4"
        rates_video(d, v, st, mp4)
        job.update(file=None, video=str(mp4.relative_to(ROOT)), item="rates-test", done=True)
        print("TEST ONLY - not published:", mp4.name)
    elif slot == "s2" and rates_fresh(d):
        try:
            rates_video(d, v, st, vid)
            job.update(file=None, video=str(vid.relative_to(ROOT)), item="rates")
        except Exception as e:
            print("! animated rates story failed, using the still image:", str(e)[:300])
            render_html(rates_html(d, v), 1080, 1920, path)
            job.update(item="rates")
    elif slot in CARD_SLOTS and (c := _safe(card_story, slot, d, v, st, vid)):
        job.update(file=None, video=str(vid.relative_to(ROOT)), item=f"{slot}:{c['title'][:40]}")
    elif slot == "story2" and (got := next_media(st)) and not (got[0].suffix.lower() in VID_EXT and not try_video(got, st, job)):
        m, mid, label = got
        if m.suffix.lower() in VID_EXT:
            print("using your video", label)
        else:
            story_image(m, path)
            job.update(item=label, media=mid)
            print("using your photo", label)
    else:
        if slot == "s2":
            print("! rates on the site are old -> using a library story instead (update the rates in admin)")
        it = ai_item("story", d, v, st)
        if not it:
            lib = json.loads((C / "stories.json").read_text())
            it = lib[st["story"] % len(lib)]
            job["advance"] = "story"
        if it["kind"] == "photo" and str(it.get("id", "")).startswith("ai:") and it.get("photo") != "suite":
            ph = pick_photos(it.get("photo", "lake"), it.get("topic", it["title"]), 1, st)
            if ph:
                it["photo_path"], it["credit"] = ph[0]
        html = (photo_html if it["kind"] == "photo" else design_html)(it, 1920, v)
        render_html(html, 1080, 1920, path)
        job.update(item=it["id"])
        ai_remember(st, it)
    if job.get("video") and not job.get("done"):
        src = ROOT / job["video"]
        dst = ROOT / "dl" / f"{day}-{slot}-ig.mp4"; dst.parent.mkdir(exist_ok=True)
        ig_normalize(src, dst)
        job["video"] = str(dst.relative_to(ROOT))
    save_state(st)
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

def ig_normalize(src, dst):
    """Re-encode to exactly what Instagram accepts best: H.264 High 4.1, 1080x1920, 30 fps CFR, yuv420p, BT.709,
    2 s closed GOPs, AAC 48 kHz stereo (silent track added if missing), max 59 s, moov atom first, no metadata."""
    import subprocess
    ff = ffmpeg_bin()
    probe = subprocess.run([ff, "-i", str(src)], capture_output=True, text=True).stderr
    has_audio = "Audio:" in probe
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
          "setsar=1,fps=30,format=yuv420p")
    cmd = [ff, "-y", "-i", str(src)]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0", "-vf", vf,
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1", "-preset", "veryfast", "-crf", "21",
            "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-t", "59", "-shortest",
            "-map_metadata", "-1", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError("could not prepare video for Instagram: " + r.stderr[-400:])
    print(f"video ready for Instagram: {Path(dst).name} ({Path(dst).stat().st_size // 1024} KB)")

def upload_video(ig, f, kind="STORIES", caption=None, url=None):
    """Instagram's resumable upload: the video goes straight from here to Meta, no public link needed."""
    size = f.stat().st_size
    print(f"uploading {kind.lower()} video {f.name} ({size // 1024 // 1024} MB)")
    extra = {"caption": caption, "share_to_feed": "true", "thumb_offset": "1200"} if kind == "REELS" else {}
    r = api("POST", f"{ig}/media", media_type=kind, upload_type="resumable", **extra)
    req = urllib.request.Request(r["uri"], data=f.read_bytes(), method="POST", headers={
        "Authorization": "OAuth " + os.environ["IG_TOKEN"], "offset": "0", "file_size": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            print("upload:", resp.read().decode(errors="replace")[:200])
        return r["id"]
    except urllib.error.HTTPError as e:
        err = f"Video upload failed {e.code}: {e.read().decode(errors='replace')}"
    if not url:
        raise SystemExit(err)
    print("! direct upload failed, trying a public link instead:", err[:200])
    try:   # put the file in the repository only now (keeps the repository small on normal days)
        import subprocess, shutil
        pub = OUT / f.name; shutil.copy(f, pub)
        for c in (["git", "add", str(pub)], ["git", "commit", "-m", "video for upload " + f.name], ["git", "pull", "--rebase", "-q"], ["git", "push", "-q"]):
            subprocess.run(c, cwd=ROOT, capture_output=True, text=True)
        repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
        url = f"https://raw.githubusercontent.com/{repo}/{ref}/out/{f.name}"
        time.sleep(30)
    except Exception as e2:
        raise SystemExit(err + " | fallback failed: " + str(e2)[:200])
    print("uploading from", url)
    return api("POST", f"{ig}/media", media_type=kind, video_url=url, **extra)["id"]

def publish():
    try:
        _publish()
    except BaseException as e:
        st = load_state()
        job = json.loads((OUT / "pending.json").read_text())
        st["last_error"] = {"at": dt.datetime.now(TR).isoformat(timespec="minutes"), "slot": job.get("slot"),
                            "item": job.get("item"), "error": str(e)[:600]}
        st["error_history"] = (st.get("error_history", []) + [st["last_error"]])[-20:]
        if job.get("media"):
            fails = st.setdefault("media_fail_count", {})
            fails[job["media"]] = fails.get(job["media"], 0) + 1
            if fails[job["media"]] >= 2:
                st.setdefault("media_done", []).append(job["media"])
                st.setdefault("media_failed", []).append({"media": job["media"], "item": job.get("item"), "error": str(e)[:300]})
        save_state(st)
        raise

def _publish():
    job = json.loads((OUT / "pending.json").read_text())
    st = load_state()
    if job.get("done"):
        print("already published"); return
    if not os.environ.get("IG_TOKEN"):
        print("IG_TOKEN not set -> dry run, nothing sent"); return
    jitter = random.randint(0, (4 if job.get("video") else int(os.environ.get("JITTER_MAX_MIN", "5"))) * 60)
    print(f"waiting {jitter // 60} min so posting time is not robotic"); time.sleep(jitter)
    repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/out/{job['file']}"
    ig = ig_user()
    if job.get("video"):
        cid = upload_video(ig, ROOT / job["video"], "REELS" if job.get("reel") else "STORIES", job.get("caption"), url=True)
    elif job.get("files"):
        base = f"https://raw.githubusercontent.com/{repo}/{ref}/out/"
        kids = [api("POST", f"{ig}/media", image_url=base + f, is_carousel_item="true")["id"] for f in job["files"]]
        cid = api("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(kids), caption=job["caption"])["id"]
    else:
        params = {"image_url": url}
        if job["slot"] in ("post",) + POST_SLOTS:
            params["caption"] = job["caption"]
        else:
            params["media_type"] = "STORIES"
        cid = api("POST", f"{ig}/media", **params)["id"]
    for _ in range(120):
        s = api("GET", cid, fields="status_code").get("status_code")
        if s == "FINISHED":
            break
        if s == "ERROR":
            raise SystemExit("Instagram could not process the media " + (job.get("video") or url) + " " + str(api("GET", cid, fields="status").get("status")))
        time.sleep(5)
    mid = api("POST", f"{ig}/media_publish", creation_id=cid)["id"]
    print("published media", mid)
    if job.get("advance"):
        st[job["advance"]] += 1
    if job.get("media"):
        st.setdefault("media_done", []).append(job["media"])
    st["log"].append({"at": dt.datetime.now(TR).isoformat(timespec="minutes"), "slot": job["slot"], "item": job["item"], "media": mid})
    try:
        refresh_inspo(ig, st)
    except BaseException as e:
        print("! inspiration step skipped:", str(e)[:200])
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
