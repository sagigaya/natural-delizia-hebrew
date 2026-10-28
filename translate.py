"""
HTML-aware translation for Natural Delizia site (WordPress + WPML EN).
Only translates text nodes (not JS/CSS). Preserves layout.
Injects RTL + Hebrew fonts (Heebo + Frank Ruhl Libre).
"""
import re, json
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Comment

ROOT = Path.home() / "Desktop" / "natural-delizia-hebrew"
translations = json.loads((ROOT / "_translations.json").read_text(encoding="utf-8"))

# UI extras likely to be needed
EXTRA = {
    "Home": "בית",
    "Company": "אודות",
    "About": "אודות",
    "About Us": "אודותינו",
    "About us": "אודותינו",
    "Products": "מוצרים",
    "Our Products": "המוצרים שלנו",
    "Our products": "המוצרים שלנו",
    "Browse Catalogue": "דפדפו בקטלוג",
    "Browse Catalog": "דפדפו בקטלוג",
    "Catalog": "קטלוג",
    "Catalogue": "קטלוג",
    "Contacts": "צור קשר",
    "Contact": "צור קשר",
    "Contact Us": "צור קשר",
    "Request a Quote": "בקשת הצעת מחיר",
    "Request a quote": "בקשת הצעת מחיר",
    "Get a Quote": "בקשת הצעת מחיר",
    "Read more": "קראו עוד",
    "Read More": "קראו עוד",
    "View all": "הצג הכל",
    "View All": "הצג הכל",
    "View details": "פרטים",
    "More": "עוד",
    "Previous": "הקודם",
    "Next": "הבא",
    "Search": "חיפוש",
    "Submit": "שלח",
    "Send": "שלח",
    "Name": "שם",
    "Email": "אימייל",
    "Phone": "טלפון",
    "Subject": "נושא",
    "Message": "הודעה",
    "Address": "כתובת",
    "Required": "חובה",
    "Thank you": "תודה",
    "Thank You": "תודה",
    "All rights reserved": "כל הזכויות שמורות",
    "Copyright": "זכויות יוצרים",
    "Follow us": "עקבו אחרינו",
    "Follow Us": "עקבו אחרינו",
    "Cookie Policy": "מדיניות עוגיות",
    "Privacy Policy": "מדיניות פרטיות",
    # Product categories
    "Artichokes": "ארטישוקים",
    "Mushrooms": "פטריות",
    "Olives": "זיתים",
    "Pickles": "חמוצים",
    "Speciality": "מיוחדים",
    "Specialities": "מיוחדים",
    "Vegetables": "ירקות",
    "Preserves": "קונסרבים",
    "Jars": "צנצנות",
    "Cans": "פחיות",
    # Food words
    "artichoke": "ארטישוק",
    "artichokes": "ארטישוקים",
    "mushroom": "פטרייה",
    "mushrooms": "פטריות",
    "olive": "זית",
    "olives": "זיתים",
    "pepper": "פלפל",
    "peppers": "פלפלים",
    "aubergine": "חציל",
    "aubergines": "חצילים",
    "eggplant": "חציל",
    "eggplants": "חצילים",
    "tomato": "עגבנייה",
    "tomatoes": "עגבניות",
}
for k, v in EXTRA.items():
    translations.setdefault(k, v)

(ROOT / "_translations.json").write_text(json.dumps(translations, indent=2, ensure_ascii=False))
print(f"Dict size (with UI additions): {len(translations)}")

NBSP_RE = re.compile(r'\xa0')
WS_RE = re.compile(r'[ \t]+')

def normalize_ws(s):
    s = NBSP_RE.sub(' ', s)
    s = WS_RE.sub(' ', s)
    return s

SHORT_WORD_RE_CACHE = {}
def is_short_common_word(k):
    return len(k) < 10 and ' ' not in k and k.replace("'", '').isalpha()

def make_wb_regex(w):
    if w not in SHORT_WORD_RE_CACHE:
        SHORT_WORD_RE_CACHE[w] = re.compile(r'(?<![A-Za-z])' + re.escape(w) + r'(?![A-Za-z])')
    return SHORT_WORD_RE_CACHE[w]

pairs = []
for k, v in translations.items():
    if not v or v == k: continue
    pairs.append((k, normalize_ws(k), v))
pairs.sort(key=lambda x: -len(x[1]))
print(f"Translation pairs: {len(pairs)}")

def apply_pairs(text):
    lead = ''
    trail = ''
    m = re.match(r'^(\s*)(.*?)(\s*)$', text, re.DOTALL)
    if m:
        lead, core, trail = m.group(1), m.group(2), m.group(3)
    else:
        core = text
    core_norm = normalize_ws(core)
    total = 0
    for _, en_norm, he in pairs:
        if is_short_common_word(en_norm):
            new, n = make_wb_regex(en_norm).subn(he, core_norm)
            if n:
                core_norm = new; total += n
        else:
            if en_norm in core_norm:
                n = core_norm.count(en_norm)
                core_norm = core_norm.replace(en_norm, he)
                total += n
    return lead + core_norm + trail, total

RTL_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@300;400;500;700;900&family=Heebo:wght@300;400;500;600;700;800;900&display=swap">
<style id="he-rtl-override">
  html, body { direction: rtl !important; }
  *, *::before, *::after {
    font-family: 'Heebo', 'Assistant', -apple-system, 'Segoe UI', Arial, sans-serif !important;
  }
  h1, h2, h3, h4 {
    font-family: 'Frank Ruhl Libre', 'Heebo', Georgia, serif !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
  }
  [lang="en"], .ltr-isolate { direction: ltr; unicode-bidi: isolate; }
  html, body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
</style>
"""

SKIP_PARENTS = {"script", "style", "noscript"}
TRANS_ATTRS = {"alt", "title", "placeholder", "aria-label"}
INPUT_VIS = {"submit", "button", "reset"}

PAGE_FILES = sorted(p.name for p in ROOT.glob("*.html"))
total_tx = 0

for fn in PAGE_FILES:
    p = ROOT / fn
    raw = p.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    if soup.html:
        soup.html["lang"] = "he"
        soup.html["dir"] = "rtl"
    count = 0
    for node in list(soup.find_all(string=True)):
        if isinstance(node, Comment): continue
        par = node.parent
        skip = False
        while par is not None:
            if getattr(par, "name", None) in SKIP_PARENTS:
                skip = True; break
            par = par.parent
        if skip: continue
        s = str(node)
        new, c = apply_pairs(s)
        if c or new != s:
            node.replace_with(NavigableString(new))
            count += max(c, 1 if new != s else 0)
    for tag in soup.find_all(True):
        for attr in TRANS_ATTRS:
            v = tag.get(attr)
            if isinstance(v, str):
                new, c = apply_pairs(v)
                if c:
                    tag[attr] = new; count += c
        if tag.name == "input" and tag.get("type", "").lower() in INPUT_VIS:
            v = tag.get("value")
            if isinstance(v, str):
                new, c = apply_pairs(v)
                if c:
                    tag["value"] = new; count += c
        if tag.name == "meta":
            prop = (tag.get("property") or tag.get("name") or "").lower()
            if any(x in prop for x in ["title", "description", "image:alt"]):
                v = tag.get("content")
                if isinstance(v, str):
                    new, c = apply_pairs(v)
                    if c:
                        tag["content"] = new; count += c
    head = soup.head
    if head and not head.find("style", {"id": "he-rtl-override"}):
        frag = BeautifulSoup(RTL_HEAD, "html.parser")
        for child in list(frag.contents):
            head.append(child)
    p.write_text(str(soup), encoding="utf-8")
    print(f"  {fn}: {count} translations")
    total_tx += count

print(f"\nTOTAL translations: {total_tx}")
