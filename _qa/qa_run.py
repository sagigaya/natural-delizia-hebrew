#!/usr/bin/env python3
"""QA runner for https://natural-delizia.vercel.app
- Checks all 80 pages for broken links/images, English leftovers, RTL issues.
- Produces _qa/report.json and screenshots for 5 key pages.
"""
import json, re, sys, time, pathlib, urllib.parse, concurrent.futures
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = "https://natural-delizia.vercel.app"
PROJ = pathlib.Path("/Users/sagie/Desktop/natural-delizia-hebrew")
QA   = PROJ / "_qa"
SHOT_PAGES = ["index", "catalog", "category-artichokes",
              "product-artichoke-petals", "contacts"]

ALLOWED_LATIN = {
    "Puglia","Naturalmente","Delizia","Delizia 2000","Trinitapoli",
    "Italia","Italy","Terralba","P.IVA","VAT","PEC","email","Email",
    "info","www","it","en","he","Via","@","naturalmentedelizia",
    "SEM","IGP","DOP","gaya","Gaya","foods","Foods",
}

slugs = (PROJ / "../").resolve()  # not used
page_slugs = [p.stem for p in sorted(PROJ.glob("*.html"))]
print(f"Pages to check: {len(page_slugs)}", flush=True)

report = {
    "pages": {},
    "broken_links_global": {},     # url -> status
    "broken_images_global": {},    # url -> reason
    "english_leftovers": {},       # slug -> [sentences]
    "font_issues": {},             # slug -> [notes]
}

def is_english_sentence(txt: str) -> bool:
    """Return True if txt looks like a real English sentence we didn't translate."""
    s = txt.strip()
    if not s or len(s) < 12:
        return False
    # Must be mostly ASCII letters
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    ascii_letters = [c for c in letters if ord(c) < 128]
    if len(ascii_letters) / len(letters) < 0.9:
        return False
    # Must contain at least 2 words of 3+ letters
    words = re.findall(r"[A-Za-z]{3,}", s)
    if len(words) < 3:
        return False
    # Strip allowed-latin tokens and see if anything meaningful remains
    stripped = s
    for tok in ALLOWED_LATIN:
        stripped = re.sub(rf"\b{re.escape(tok)}\b", "", stripped, flags=re.I)
    remaining_words = re.findall(r"[A-Za-z]{3,}", stripped)
    return len(remaining_words) >= 3

def check_response(ctx, url):
    try:
        r = ctx.request.head(url, timeout=10000)
        if r.status in (301,302,303,307,308):
            r2 = ctx.request.get(url, timeout=10000)
            return r2.status
        if r.status == 405:  # HEAD not allowed
            r2 = ctx.request.get(url, timeout=10000)
            return r2.status
        return r.status
    except Exception as e:
        return f"ERR:{type(e).__name__}"

def normalize_url(href, base):
    if not href: return None
    href = href.strip()
    if href.startswith(("mailto:","tel:","javascript:","#")):
        return None
    return urllib.parse.urljoin(base, href)

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width":1440,"height":900})
        checked_urls = {}      # url -> status (cache)

        for i, slug in enumerate(page_slugs, 1):
            url = f"{BASE}/{slug}.html" if slug != "index" else f"{BASE}/"
            print(f"[{i:>2}/{len(page_slugs)}] {slug}", flush=True)
            page_rec = {"url": url, "status": None, "broken_links": [],
                        "broken_images": [], "english": [],
                        "font_issues": [], "page_errors": []}
            page = ctx.new_page()
            page.on("pageerror", lambda e, rec=page_rec: rec["page_errors"].append(str(e)))

            try:
                resp = page.goto(url, timeout=25000, wait_until="domcontentloaded")
                page_rec["status"] = resp.status if resp else "no-resp"
            except Exception as e:
                page_rec["status"] = f"ERR:{type(e).__name__}:{e}"
                report["pages"][slug] = page_rec
                page.close()
                continue

            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # ---- English leftovers ----
            for tag in soup(["script","style","noscript"]):
                tag.decompose()
            body = soup.body
            if body:
                for node in body.find_all(string=True):
                    txt = str(node)
                    if is_english_sentence(txt):
                        page_rec["english"].append(txt.strip()[:180])
            page_rec["english"] = list(dict.fromkeys(page_rec["english"]))[:20]

            # ---- Links ----
            hrefs = set()
            for a in soup.find_all("a", href=True):
                u = normalize_url(a["href"], url)
                if u and u.startswith(BASE):
                    hrefs.add(u.split("#")[0])
            for u in hrefs:
                if u not in checked_urls:
                    checked_urls[u] = check_response(ctx, u)
                st = checked_urls[u]
                if isinstance(st,int) and st >= 400:
                    page_rec["broken_links"].append({"url":u,"status":st})
                elif isinstance(st,str) and st.startswith("ERR"):
                    page_rec["broken_links"].append({"url":u,"status":st})

            # ---- Images (via DOM to catch dynamic / CSS-driven) ----
            try:
                broken = page.evaluate("""
                  () => {
                    const imgs = Array.from(document.images);
                    return imgs
                      .filter(i => !i.complete || i.naturalWidth === 0)
                      .map(i => ({src: i.currentSrc || i.src,
                                   alt: i.alt || "",
                                   w: i.naturalWidth, h: i.naturalHeight}));
                  }
                """)
                for b in broken:
                    page_rec["broken_images"].append(b)
            except Exception as e:
                page_rec["page_errors"].append(f"img-eval:{e}")

            # ---- Font sanity on hebrew-containing elements ----
            try:
                font_issues = page.evaluate("""
                  () => {
                    const issues = [];
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    const seen = new Set();
                    let node;
                    while (node = walker.nextNode()) {
                      const txt = node.textContent.trim();
                      if (!txt) continue;
                      // Any hebrew char in this text?
                      if (!/[\\u0590-\\u05FF]/.test(txt)) continue;
                      const el = node.parentElement;
                      if (!el) continue;
                      const cs = getComputedStyle(el);
                      const ff = cs.fontFamily || "";
                      const dir = cs.direction || "";
                      const key = ff + "|" + dir;
                      if (seen.has(key)) continue;
                      seen.add(key);
                      const ok = /Heebo|Frank Ruhl|Rubik|Assistant|Arial|Helvetica|system-ui/i.test(ff);
                      if (!ok) {
                        issues.push({sample: txt.slice(0,60), font: ff, dir: dir, tag: el.tagName});
                      }
                      if (dir && dir !== "rtl") {
                        issues.push({sample: txt.slice(0,60), font: ff, dir: dir, tag: el.tagName, note:"non-rtl"});
                      }
                    }
                    return issues.slice(0, 10);
                  }
                """)
                page_rec["font_issues"] = font_issues
            except Exception as e:
                page_rec["page_errors"].append(f"font-eval:{e}")

            # ---- Screenshot for the 5 key pages ----
            if slug in SHOT_PAGES:
                try:
                    page.screenshot(path=str(QA / f"shot_{slug}.png"),
                                    full_page=True)
                except Exception as e:
                    page_rec["page_errors"].append(f"shot:{e}")

            report["pages"][slug] = page_rec
            page.close()

        # Aggregate
        for slug, rec in report["pages"].items():
            for bl in rec["broken_links"]:
                report["broken_links_global"][bl["url"]] = bl["status"]
            for bi in rec["broken_images"]:
                report["broken_images_global"][bi["src"]] = f"nw={bi['w']}"
            if rec["english"]:
                report["english_leftovers"][slug] = rec["english"]
            if rec["font_issues"]:
                report["font_issues"][slug] = rec["font_issues"]

        browser.close()

    (QA / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n=== SUMMARY ===", flush=True)
    print(f"Pages checked: {len(report['pages'])}")
    print(f"Pages with non-200: " + str([(s,r['status']) for s,r in report['pages'].items() if r['status'] != 200]))
    print(f"Unique broken links: {len(report['broken_links_global'])}")
    print(f"Unique broken images: {len(report['broken_images_global'])}")
    print(f"Pages with English leftovers: {len(report['english_leftovers'])}")
    print(f"Pages with font issues: {len(report['font_issues'])}")

if __name__ == "__main__":
    run()
