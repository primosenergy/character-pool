#!/usr/bin/env python3
"""One-shot tool: pull the Disney character list from a Reader's Digest article,
image-search each character, and save the top five images per character.

Usage:
    python3 character_pool.py                      # scrape article, search, download
    python3 character_pool.py --list-only          # just write characters.csv and stop
    python3 character_pool.py --csv characters.csv # skip scraping, use an (edited) CSV
    python3 character_pool.py --html saved.html    # parse a page you saved from your browser
"""
import argparse
import csv
import mimetypes
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from ddgs import DDGS

ARTICLE_URL = "https://www.rd.com/list/disney-characters-surprising-facts/"
IMAGES_PER_CHARACTER = 5
EXPECTED_COUNT = 405
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
ICLOUD_DRIVE = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"

# Headings in the article that are not characters.
NOT_CHARACTERS = re.compile(
    r"^(sources?|related|more|advertisement|newsletter|share|about|"
    r"read more|you might also like|get .* newsletter)\b",
    re.I,
)


def default_output_dir() -> Path:
    if ICLOUD_DRIVE.is_dir():
        return ICLOUD_DRIVE / "Disney Characters"
    return Path.home() / "Pictures" / "Disney Characters"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_numbering(text: str) -> str:
    # "12. Ariel", "12) Ariel", "12/405 Ariel", "No. 12: Ariel"
    return clean(re.sub(r"^(no\.\s*)?\d+\s*(/\s*\d+)?\s*[.):\-–—]?\s*", "", text, flags=re.I))


def split_heading(text: str) -> tuple[str, str]:
    """Pull a movie out of the heading itself, e.g. 'Ariel (The Little Mermaid)'
    or 'Ariel – The Little Mermaid'."""
    m = re.match(r"^(.*?)\s*\((.+?)\)\s*$", text)
    if m:
        return clean(m.group(1)), clean(m.group(2))
    m = re.match(r"^(.*?)\s+[–—:|]\s+(.+)$", text)
    if m:
        return clean(m.group(1)), clean(m.group(2))
    return text, ""


def movie_from_body(heading: Tag) -> str:
    """Film titles are italicized in the article body; take the first one
    between this heading and the next."""
    for el in heading.next_elements:
        if el is heading or isinstance(el, NavigableString):
            continue
        if isinstance(el, Tag) and el.name == heading.name:
            break
        if isinstance(el, Tag) and el.name in ("em", "i", "cite"):
            title = clean(el.get_text())
            if 2 < len(title) < 80:
                return title.strip(" ,.;:")
    return ""


def extract_characters(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select("script, style, nav, header, footer, aside"):
        junk.decompose()
    root = soup.find("article") or soup.body or soup

    # Use whichever heading level holds the most entries (the list items).
    best = []
    for level in ("h2", "h3", "h4"):
        found = [h for h in root.find_all(level) if clean(h.get_text())]
        if len(found) > len(best):
            best = found

    characters = []
    seen = set()
    for h in best:
        text = strip_numbering(clean(h.get_text()))
        if not text or NOT_CHARACTERS.match(text) or len(text) > 80:
            continue
        name, movie = split_heading(text)
        movie = movie or movie_from_body(h)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        characters.append((name, movie))
    return characters


def fetch_article() -> str:
    r = requests.get(ARTICLE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["character", "movie"])
        w.writerows(rows)


def read_csv(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [(r["character"].strip(), r.get("movie", "").strip()) for r in csv.DictReader(f)]


def safe_filename(text: str) -> str:
    return clean(re.sub(r'[\\/:*?"<>|]', "-", text)) or "Unknown"


def extension_for(response: requests.Response, url: str) -> str:
    ctype = response.headers.get("Content-Type", "").split(";")[0].strip()
    ext = mimetypes.guess_extension(ctype) if ctype.startswith("image/") else None
    if not ext:
        m = re.search(r"\.(jpe?g|png|gif|webp)(?:$|\?)", url, re.I)
        ext = "." + m.group(1).lower() if m else ".jpg"
    return ".jpg" if ext in (".jpe", ".jpeg") else ext


def search_images(query: str, tries: int = 4) -> list[str]:
    for attempt in range(tries):
        try:
            results = DDGS().images(query, max_results=25)
            return [r["image"] for r in results if r.get("image")]
        except Exception as e:  # rate limits show up as generic exceptions
            wait = 10 * (attempt + 1)
            print(f"    search failed ({e}); retrying in {wait}s")
            time.sleep(wait)
    return []


def download_top_images(name: str, movie: str, out_dir: Path) -> int:
    base = f"{safe_filename(name)} - {safe_filename(movie or 'Disney')}"
    existing = sorted(out_dir.glob(f"{glob_escape(base)} - [1-5].*"))
    if len(existing) >= IMAGES_PER_CHARACTER:
        return len(existing)

    urls = search_images(f"{name} Disney")
    saved = 0
    # Take the top results in order; if one won't download, move to the next.
    for url in urls:
        if saved == IMAGES_PER_CHARACTER:
            break
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if not r.headers.get("Content-Type", "").startswith("image/") or len(r.content) < 1024:
                continue
        except requests.RequestException:
            continue
        saved += 1
        path = out_dir / f"{base} - {saved}{extension_for(r, url)}"
        path.write_bytes(r.content)
    return saved


def glob_escape(text: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", text)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", type=Path, help="use this character list instead of scraping the article")
    p.add_argument("--html", type=Path, help="parse a saved copy of the article instead of downloading it")
    p.add_argument("--out", type=Path, default=default_output_dir(), help="where to save images")
    p.add_argument("--list-only", action="store_true", help="write characters.csv and stop")
    p.add_argument("--delay", type=float, default=2.0, help="seconds to wait between searches")
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.csv:
        characters = read_csv(args.csv)
    else:
        html = args.html.read_text(encoding="utf-8") if args.html else fetch_article()
        characters = extract_characters(html)
        csv_path = args.out / "characters.csv"
        write_csv(csv_path, characters)
        print(f"Found {len(characters)} characters -> {csv_path}")
        if len(characters) != EXPECTED_COUNT:
            print(f"  Note: expected {EXPECTED_COUNT}. Check the CSV; you can fix it and rerun with --csv.")
        missing = sum(1 for _, m in characters if not m)
        if missing:
            print(f"  {missing} characters have no movie; their files will say 'Disney' instead.")
    if args.list_only:
        return

    for i, (name, movie) in enumerate(characters, 1):
        print(f"[{i}/{len(characters)}] {name} ({movie or '?'})")
        n = download_top_images(name, movie, args.out)
        if n < IMAGES_PER_CHARACTER:
            print(f"    only got {n} images")
        time.sleep(args.delay)

    print(f"\nDone. Images are in: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped. Rerun the same command to pick up where you left off.")
