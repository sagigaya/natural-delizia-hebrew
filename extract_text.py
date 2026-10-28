"""Extract all visible English text for translation."""
import re, json, html as htmlmod
from pathlib import Path
from collections import Counter

ROOT = Path.home() / "Desktop" / "natural-delizia-hebrew"
PAGES = sorted(p.name for p in ROOT.glob("*.html"))
SCRIPT_RE = re.compile(r'<(script|style|noscript)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')

phrases = Counter()
for fn in PAGES:
    txt = (ROOT / fn).read_text(encoding="utf-8")
    stripped = SCRIPT_RE.sub(' ', txt)
    stripped = TAG_RE.sub('\n', stripped)
    stripped = htmlmod.unescape(stripped)
    for line in stripped.split('\n'):
        line = WS_RE.sub(' ', line).strip()
        if len(line) < 2: continue
        if re.match(r'^[\s\d\W_]+$', line): continue
        if line.startswith('http'): continue
        if not re.search(r'[A-Za-z]', line): continue
        if re.search(r'[{};=]{2,}', line): continue
        phrases[line] += 1

sorted_p = sorted(phrases.items(), key=lambda x: (-len(x[0]), -x[1]))
out = ROOT / "_text_to_translate.txt"
with out.open("w", encoding="utf-8") as f:
    for p, c in sorted_p:
        f.write(f"[{c}x · {len(p)}ch]  {p}\n")

(ROOT / "_phrases.json").write_text(
    json.dumps([{"text": p, "count": c, "len": len(p)} for p, c in sorted_p], indent=2, ensure_ascii=False)
)
print(f"Unique phrases: {len(sorted_p)}  · Total occurrences: {sum(phrases.values())}")
