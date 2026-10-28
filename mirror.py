"""
Mirror naturalmentedelizia.it (WordPress + WPML, English version at ?lang=en).
Static HTML, straightforward urllib download.
"""
import os, re, hashlib, urllib.parse, urllib.request, ssl, json
import concurrent.futures
import threading
from pathlib import Path

ROOT = Path.home() / "Desktop" / "natural-delizia-hebrew"
BASE = "https://www.naturalmentedelizia.it"
IMG_DIR = ROOT / "images"
CSS_DIR = ROOT / "css"
JS_DIR = ROOT / "js"
FONT_DIR = ROOT / "fonts"
RAW_DIR = ROOT / "_raw_html"
for d in (ROOT, IMG_DIR, CSS_DIR, JS_DIR, FONT_DIR, RAW_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Nav pages (EN)
PAGES = {
    "/?lang=en": "index.html",
    "/company/?lang=en": "company.html",
    "/our-products/?lang=en": "products.html",
    "/naturalmente-delizia-catalog/?lang=en": "catalog.html",
    "/product-catalog/?lang=en": "product-catalog.html",
    "/contacts/?lang=en": "contacts.html",
    "/request-a-quote/?lang=en": "request-quote.html",
}

# Product categories (EN)
CATEGORIES = {
    "/catalogo-prodotti/artichokes/?lang=en": "category-artichokes.html",
    "/catalogo-prodotti/mushrooms/?lang=en": "category-mushrooms.html",
    "/catalogo-prodotti/olives/?lang=en": "category-olives.html",
    "/catalogo-prodotti/pickles/?lang=en": "category-pickles.html",
    "/catalogo-prodotti/speciality/?lang=en": "category-speciality.html",
    "/catalogo-prodotti/vegetables/?lang=en": "category-vegetables.html",
}
PAGES.update(CATEGORIES)

# Products (EN) - from sitemap, filter lang=en
PRODUCTS_URLS = Path("/tmp/natural-products-en.txt").read_text().strip().split("\n")
PRODUCT_MAP = {}
for url in PRODUCTS_URLS:
    # extract slug from /prodotto/<slug>/?lang=en
    m = re.search(r'/prodotto/([^/]+)/', url)
    if m:
        slug = m.group(1)
        route = f"/prodotto/{slug}/?lang=en"
        fname = f"product-{slug}.html"
        PAGES[route] = fname
        PRODUCT_MAP[slug] = fname

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15"}
downloaded = {}
dl_lock = threading.Lock()

def safe_name(url, ext_hint=None):
    p = urllib.parse.urlparse(url)
    base = os.path.basename(p.path.rstrip("/")) or "asset"
    base = base.split("?")[0]
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    name, ext = os.path.splitext(base)
    if not ext:
        ext = ext_hint or ".bin"
    return f"{name[:60]}_{h}{ext}"

def download(url, target_dir, ext_hint=None):
    with dl_lock:
        if url in downloaded:
            return downloaded[url]
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            data = r.read()
            ct = r.headers.get("content-type", "").lower()
        hint = ext_hint
        if not hint:
            if "jpeg" in ct or "jpg" in ct: hint = ".jpg"
            elif "png" in ct: hint = ".png"
            elif "gif" in ct: hint = ".gif"
            elif "webp" in ct: hint = ".webp"
            elif "svg" in ct: hint = ".svg"
            elif "css" in ct: hint = ".css"
            elif "javascript" in ct: hint = ".js"
            elif "woff2" in ct: hint = ".woff2"
            elif "woff" in ct: hint = ".woff"
            elif "ttf" in ct: hint = ".ttf"
        name = safe_name(url, ext_hint=hint)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / name).write_bytes(data)
        rel = f"{target_dir.name}/{name}"
        with dl_lock:
            downloaded[url] = rel
        return rel
    except Exception as e:
        print(f"  ✗ FAIL {url[:70]}: {e}", flush=True)
        with dl_lock:
            downloaded[url] = None
        return None

IMG_RE = re.compile(r'(?:src|data-src|data-original)=["\']([^"\'\s>]+\.(?:jpg|jpeg|png|gif|webp|svg)[^"\'\s>]*)["\']', re.IGNORECASE)
SRCSET_RE = re.compile(r'(?:srcset|data-srcset)=["\']([^"\']+)["\']')
CSS_RE = re.compile(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\']', re.IGNORECASE)
JS_RE = re.compile(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', re.IGNORECASE)
BG_RE = re.compile(r'url\(["\']?([^")]+\.(?:jpg|jpeg|png|gif|webp|svg)[^")]*)["\']?\)', re.IGNORECASE)
FONT_RE = re.compile(r'src:\s*url\(["\']?([^")]+\.(?:woff2|woff|ttf|otf|eot))', re.IGNORECASE)

def abs_url(src, page_url):
    if not src or src.startswith("data:"): return None
    if src.startswith("//"): return "https:" + src
    if src.startswith("http"): return src
    if src.startswith("/"): return BASE + src
    return urllib.parse.urljoin(page_url, src)

def mirror_page(route, filename):
    url = BASE + route
    print(f"→ {url}", flush=True)
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, context=CTX, timeout=45) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ✗ page fail: {e}")
        return
    (RAW_DIR / filename.replace(".html", ".raw.html")).write_text(html, encoding="utf-8")

    img_urls = set(IMG_RE.findall(html))
    for m in SRCSET_RE.finditer(html):
        for item in m.group(1).split(","):
            u = item.strip().split()[0]
            if u: img_urls.add(u)
    for m in BG_RE.finditer(html):
        img_urls.add(m.group(1))
    css_urls = set(CSS_RE.findall(html))
    js_urls = set(JS_RE.findall(html))
    font_urls = set(FONT_RE.findall(html))

    url_map = {}
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for u in img_urls:
            au = abs_url(u, url)
            if au:
                jobs.append((u, pool.submit(download, au, IMG_DIR)))
        for u in css_urls:
            au = abs_url(u, url)
            if au:
                jobs.append((u, pool.submit(download, au, CSS_DIR, ".css")))
        for u in js_urls:
            au = abs_url(u, url)
            if au:
                jobs.append((u, pool.submit(download, au, JS_DIR, ".js")))
        for u in font_urls:
            au = abs_url(u, url)
            if au:
                jobs.append((u, pool.submit(download, au, FONT_DIR)))
    for orig_u, fut in jobs:
        local = fut.result()
        if local: url_map[orig_u] = "/" + local

    for orig, local in sorted(url_map.items(), key=lambda x: -len(x[0])):
        html = html.replace(f'"{orig}"', f'"{local}"').replace(f"'{orig}'", f"'{local}'")

    # Rewrite nav links to local .html files
    nav_map = {
        '/company/?lang=en': '/company.html',
        '/our-products/?lang=en': '/products.html',
        '/naturalmente-delizia-catalog/?lang=en': '/catalog.html',
        '/product-catalog/?lang=en': '/product-catalog.html',
        '/contacts/?lang=en': '/contacts.html',
        '/request-a-quote/?lang=en': '/request-quote.html',
        '/?lang=en': '/',
        '/catalogo-prodotti/artichokes/?lang=en': '/category-artichokes.html',
        '/catalogo-prodotti/mushrooms/?lang=en': '/category-mushrooms.html',
        '/catalogo-prodotti/olives/?lang=en': '/category-olives.html',
        '/catalogo-prodotti/pickles/?lang=en': '/category-pickles.html',
        '/catalogo-prodotti/speciality/?lang=en': '/category-speciality.html',
        '/catalogo-prodotti/vegetables/?lang=en': '/category-vegetables.html',
    }
    for src, dst in nav_map.items():
        html = html.replace(f'href="{src}"', f'href="{dst}"')
        html = html.replace(f'href="{BASE}{src}"', f'href="{dst}"')
    # Products
    for slug, fname in PRODUCT_MAP.items():
        html = re.sub(rf'href="(?:{re.escape(BASE)})?/prodotto/{re.escape(slug)}/\?lang=en"', f'href="/{fname}"', html)

    (ROOT / filename).write_text(html, encoding="utf-8")
    print(f"  ✓ saved {filename} ({len(html)//1024}KB · imgs:{len(img_urls)} css:{len(css_urls)} js:{len(js_urls)})", flush=True)

for route, fn in list(PAGES.items()):
    mirror_page(route, fn)

print(f"\nTotal assets: {len([v for v in downloaded.values() if v])}")
print(f"  Images: {len(list(IMG_DIR.glob('*')))}")
print(f"  CSS: {len(list(CSS_DIR.glob('*')))}")
print(f"  JS: {len(list(JS_DIR.glob('*')))}")
print(f"  Fonts: {len(list(FONT_DIR.glob('*')))}")

(ROOT / "_asset_manifest.json").write_text(json.dumps(downloaded, indent=2, ensure_ascii=False))
