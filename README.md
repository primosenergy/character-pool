# character-pool

A one-time tool that gathers pictures of the 405 characters in Reader's Digest's
[Disney characters article](https://www.rd.com/list/disney-characters-surprising-facts/),
so you can see each character while you read.

What it does:

1. Reads the article and builds a two-column list (character, movie) saved as `characters.csv`.
2. Image-searches `<character> Disney` (DuckDuckGo, no account or API key needed).
3. Saves the top 5 images per character as `Character - Movie - 1.jpg` … `- 5.jpg`.
4. Puts everything in **iCloud Drive → Disney Characters** (falls back to `~/Pictures/Disney Characters`).

## Run it (Mac)

```sh
git clone https://github.com/primosenergy/character-pool.git
cd character-pool
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 character_pool.py
```

It takes roughly 30–60 minutes (405 searches, ~2,000 images). If it stops or you
press Ctrl‑C, run the same command again: characters that already have 5 images are skipped.

### If something looks off

- **Wrong count or bad names/movies:** run with `--list-only`, fix `characters.csv`
  in Numbers or Excel, then run `python3 character_pool.py --csv "<path to>/characters.csv"`.
- **The article won't download (403 error):** open the article in Safari, use
  File → Save As (Format: Page Source), then run `python3 character_pool.py --html ~/Downloads/<saved file>.html`.
- **Search errors / rate limits:** the script retries on its own; you can slow it down with `--delay 5`.

## Putting the images in an iCloud Shared Album

Apple doesn't let scripts add photos to Shared Albums, so this last step is manual:

1. Open **Photos** → File → Import… → choose the `Disney Characters` folder.
2. Select the imported photos → Share button → **Add to Shared Album**.

Or skip that and browse the folder in the **Files** app on your iPhone/iPad. Filenames
sort alphabetically by character, which makes them easy to find while reading.
