# Brand assets — what was extracted, and what it is not

Everything in `apps/web/public/brand/` was extracted from the vector drawing inside `mesnium-executive-brandbook-revised-v3.pdf`, not redrawn by eye.

| What | Where it came from |
|---|---|
| The **symbol** (two forms) | Two filled paths on page 8 — a warm-white form and a crimson form, three curves each. Their coordinates land exactly on a **128 × 104 integer grid**, so the SVG is the clean original geometry |
| The **wordmark** `mesnium` | Real glyph outlines from the **DM Sans SemiBold** subset embedded in the PDF (page 7), converted to paths — no font needed to display it |
| **Lockup** proportions (symbol size, gap, baseline) | Measured from the page 7 lockup |
| **Colours, type scale, spacing, motion, icon rules** | The brandbook's text, in [`tokens.json`](tokens.json) and [`guidelines.md`](guidelines.md) |
| The **approved reference board** | The image embedded on page 41, saved as [`approved-reference-board.png`](approved-reference-board.png) |

## Files in `apps/web/public/brand/`

| File | Use |
|---|---|
| `mesnium-logo.svg` | Horizontal lockup on light surfaces (obsidian + crimson) |
| `mesnium-logo-reverse.svg` | Horizontal lockup on dark surfaces (warm white + crimson) — the primary expression |
| `mesnium-logo-mono-obsidian.svg`, `mesnium-logo-mono-white.svg` | One-ink lockups for `<img>` tags |
| `mesnium-logo-mono.svg` | One-ink lockup in `currentColor` — **only follows the text colour when inlined**; inside an `<img>` it renders black |
| `mesnium-symbol*.svg` | The symbol alone, same colourways as above |
| `mesnium-wordmark.svg`, `mesnium-wordmark-white.svg` | The lettering alone (`mesnium-wordmark.svg` is `currentColor`) |
| `mesnium-app-icon.svg` | App icon on obsidian (dark-first primary); `-light` and `-crimson` are the other two tiles on the board |
| `mesnium-app-icon-512.png`, `-192.png`, `apple-touch-icon.png` | Raster renders of the primary icon |
| `favicon.ico`, `favicon-32.png` | 16 / 32 / 48 px favicon, drawn with a larger symbol at small sizes |

## What this is not

- **Not the original master.** The brandbook says its symbols are "screen reproductions of the approved reference, not original vector masters", and its own asset cards read "source file not attached". These SVGs are a faithful extraction of that reproduction. If a designer holds the original SVG/AI file, that file wins — swap it in.
- **Wordmark discrepancy.** The approved board (page 41) shows custom lettering, but the brandbook text says that lettering "is not adopted" and the DM Sans wordmark is retained. These files follow the brandbook text (DM Sans SemiBold). Confirm that is the final decision.
- **The app-icon tiles are composed here.** The PDF does not draw them as vectors, so the rounded tile (about 22% radius, symbol at about 56% of the tile) is matched to the proportions on the board, not copied.
- **No stacked lockup.** The board shows one, but the PDF contains no vector for it, so none was made up.
- **Favicon at 16 px** (the brandbook asks for this to be tested): both forms stay distinct in colour, but the diagonal opening between them is only about one pixel wide there. Legible, but tight — worth a look on a real browser tab.
- **No trademark clearance.** The brandbook is explicit that it is "not legal clearance".

## Regenerating

The extraction scripts are not kept in the repository. The method, if it has to be repeated: read the page's drawing instructions with `pypdf`, track transforms, keep the filled paths of the right colour, and for the wordmark load the embedded font with `fontTools` and convert each glyph to a path.
