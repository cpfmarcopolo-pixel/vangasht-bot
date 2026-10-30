"""Vangasht Instagram bot.

Every day it publishes (through the official Instagram Graph API):
  11:00  story 1  -> today's exchange rates, read live from vangasht.com
                     (if the rates on the site are older than RATES_MAX_AGE_H hours,
                      a story from the library is used instead, so stale prices are never posted)
  17:00  story 2  -> the oldest photo/video you uploaded to the stories/ folder that is not published yet;
                     if the folder is empty, the next designed story from stories.json
  20:00  post     -> a fresh post written by Claude (ANTHROPIC_API_KEY); falls back to posts.json
  Designed stories are also written by Claude when the key is set.

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
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.load(r)
        txt = "".join(b.get("text", "") for b in out.get("content", []))
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        return json.loads(txt)
    except Exception as e:
        print("! AI writer failed, using the library instead:", e)
        return None

def inspo_text(st):
    ins = st.get("inspo") or {}
    lines = []
    if ins.get("own"):
        lines.append("پست‌های خود پیج ما که بیشترین لایک را گرفته‌اند (بفهم مخاطب ما چه دوست دارد):")
        lines += [f"- ❤{p['likes']} 💬{p['comments']}: {p['caption'][:220]}" for p in ins["own"][:4]]
    if ins.get("others"):
        lines.append("نمونه پست‌های موفق پیج‌های دیگر (فقط برای ایده گرفتن از سبک و قالب؛ کپی نکن):")
        lines += [f"- @{p['user']} ❤{p['likes']} 💬{p['comments']}: {p['caption'][:260]}" for p in ins["others"][:8]]
    return ("\n".join(lines) + "\n\n") if lines else ""

def refresh_inspo(ig, st):
    """Once a day, read (read-only) the best recent posts of our page and of the pages listed in inspiration.txt."""
    ins = st.get("inspo") or {}
    if ins.get("day") == dt.datetime.now(TR).strftime("%Y-%m-%d"):
        return
    F = "caption,like_count,comments_count"
    def rows(media, user=None):
        out = []
        for m in (media or {}).get("data", []):
            c = (m.get("caption") or "").strip()
            if len(c) > 30:
                out.append({"user": user, "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0), "caption": c.replace("\n", " / ")})
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

def commons_candidates(query, used):
    import html as _h, re as _re
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": "6", "gsrlimit": "40",
        "gsrsearch": f"filetype:bitmap {query}", "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": "1600"})
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

def pick_photos(key, topic, k, st):
    """Returns up to k (path, credit) pairs of fresh, beautiful photos for the subject; [] if none could be fetched."""
    used = set(st.get("photos_used", []))
    q = COMMONS_Q.get(key) or COMMONS_Q["lake"]
    try:
        cands = commons_candidates(q, used)[:9]
        if len(cands) < k:
            cands += [c for c in commons_candidates(COMMONS_Q["lake"], used) if c not in cands][: 9 - len(cands)]
    except Exception as e:
        print("! could not search photos:", e)
        return []
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
    print(f"photos: {len(res)} picked for '{topic}'")
    return res

# ---------------------------------------------------------------- carousel slides
def slide_html(sl, i, n, photo, v):
    img = ""
    if photo:
        img = f'<div style="position:absolute;left:0;right:0;top:0;height:640px;background:url({b64(photo[0], "image/jpeg")}) center/cover"></div><div class="cr" style="top:600px;bottom:auto">عکس: {photo[1]}</div>'
    top = 700 if photo else 240
    body = fill(sl.get("body", ""), v).replace("\n", "<br>")
    return f"""<div class="teal"></div>{img}{'' if photo else brand()}
<div style="position:absolute;right:70px;left:70px;top:{top}px">
<div style="display:flex;align-items:center;gap:22px"><span style="background:#f2ad3d;color:#12222a;font-weight:900;font-size:46px;border-radius:50%;width:84px;height:84px;display:grid;place-items:center">{fa(i)}</span>
<span style="font-size:28px;opacity:.7;font-weight:700">{fa(i)} از {fa(n)}</span></div>
<h1 style="font-size:{80 if photo else 90}px;font-weight:900;line-height:1.25;margin:26px 0 22px">{hl(sl, v)}</h1>
<p style="font-size:{44 if photo else 50}px;font-weight:600;line-height:1.6;opacity:.95">{body}</p></div>
<div style="position:absolute;left:70px;bottom:56px;font-size:30px;font-weight:800;color:#f2ad3d">ورق بزن ←</div>"""

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

def rates_video(d, v, st, dst):
    """25 s story (RATES_SECONDS) with music: a slow zoom over a beautiful Van photo, darkened, with the date, each rate row and the footer fading in."""
    import subprocess
    ff = ffmpeg_bin()
    if not ff:
        raise RuntimeError("ffmpeg not available")
    work = ROOT / "dl"; work.mkdir(exist_ok=True)
    ph = pick_photos(random.choice(["lake", "akdamar", "edremit", "suphan", "city"]), "منظرهٔ زیبای وان برای پس‌زمینهٔ استوری نرخ ارز", 1, st)
    bg = ph[0][0] if ph else A / "akdamar.jpg"
    parts = ["head"] + [f"row{i}" for i in range(len(rates_rows(d)))] + ["foot"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        for k in parts:
            pg.set_content(f"<html dir=rtl><head><meta charset=utf-8><style>{css()}html,body{{background:transparent}}body{{width:1080px;height:1920px}}</style></head><body>{rates_layer_html(d, v, k)}</body></html>")
            pg.wait_for_timeout(250)
            pg.screenshot(path=str(work / f"layer-{k}.png"), omit_background=True)
        b.close()
    T = int(os.environ.get("RATES_SECONDS", "25"))
    cmd = [ff, "-y", "-loop", "1", "-i", str(bg)]
    for k in parts:
        cmd += ["-loop", "1", "-t", str(T), "-i", str(work / f"layer-{k}.png")]
    f = (f"[0:v]scale=-2:2300,crop=1300:2300,zoompan=z='min(zoom+0.0006,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={T*30}:s=1080x1920:fps=30,"
         f"eq=brightness=-0.10:saturation=1.15,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.36:t=fill,fade=in:st=0:d=0.6[b0];")
    last = "b0"
    for i, k in enumerate(parts):
        st_ = 0.8 + i * 0.7
        f += f"[{i+1}:v]format=rgba,fade=in:st={st_:.2f}:d=0.5:alpha=1,fade=out:st={T-0.8}:d=0.6:alpha=1[l{i}];[{last}][l{i}]overlay=0:0[b{i+1}];"
        last = f"b{i+1}"
    f += f"[{last}]format=yuv420p[out]"
    # music: a random track from the music/ folder (royalty-free files you add), else a soft generated ambient pad
    tracks = [m for m in (ROOT / "music").glob("*") if m.suffix.lower() in (".mp3", ".m4a", ".aac", ".wav", ".ogg")] if (ROOT / "music").is_dir() else []
    n_in = 1 + len(parts)
    if tracks:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(tracks))]
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
    print("animated rates story ready")

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
        it = ai_item("post", d, v, st)
        if not it:
            lib = json.loads((C / "posts.json").read_text())
            it = lib[st["post"] % len(lib)]
            job["advance"] = "post"
        files = render_post(it, v, st, day)
        if len(files) > 1:
            job["files"] = files
        tags = "#وان #وان_ترکیه #سفر_به_وان #صرافی_وان #سوئیت_وان #تور_وان #خرید_از_وان #ترکیه #VanTurkey #Van #VanGölü #وان_گشت"
        job.update(caption=fill(it["caption"], v) + "\n\n" + tags, item=it["id"])
        ai_remember(st, it)
    elif slot == "story1" and rates_fresh(d):
        try:
            mp4 = ROOT / "dl" / f"{day}-rates.mp4"
            rates_video(d, v, st, mp4)
            job.update(file=None, video=str(mp4.relative_to(ROOT)), item="rates")
        except Exception as e:
            print("! animated rates story failed, using the still image:", str(e)[:300])
            render_html(rates_html(d, v), 1080, 1920, path)
            job.update(item="rates")
    elif slot == "story2" and (got := next_media(st)) and not (got[0].suffix.lower() in VID_EXT and not try_video(got, st, job)):
        m, mid, label = got
        if m.suffix.lower() in VID_EXT:
            print("using your video", label)
        else:
            story_image(m, path)
            job.update(item=label, media=mid)
            print("using your photo", label)
    else:
        if slot == "story1":
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
    try:
        _publish()
    except BaseException as e:
        st = load_state()
        job = json.loads((OUT / "pending.json").read_text())
        st["last_error"] = {"at": dt.datetime.now(TR).isoformat(timespec="minutes"), "slot": job.get("slot"),
                            "item": job.get("item"), "error": str(e)[:600]}
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
    jitter = random.randint(0, int(os.environ.get("JITTER_MAX_MIN", "12")) * 60)
    print(f"waiting {jitter // 60} min so posting time is not robotic"); time.sleep(jitter)
    repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/out/{job['file']}"
    ig = ig_user()
    if job.get("video"):
        cid = upload_video(ig, ROOT / job["video"])
    elif job.get("files"):
        base = f"https://raw.githubusercontent.com/{repo}/{ref}/out/"
        kids = [api("POST", f"{ig}/media", image_url=base + f, is_carousel_item="true")["id"] for f in job["files"]]
        cid = api("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(kids), caption=job["caption"])["id"]
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
