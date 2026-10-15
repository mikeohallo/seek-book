# Seek and Find

A seek-and-find game for a small child, starring her own family. Every busy picture hides the girl, Dad, Mum, Grandma, the uncle, the grandparents, her ballet shoes, her favourite toy Teddy and the unicorn from her Monster Book. Tap everyone you can find.

**Try it:** [seek.mikeohalloran.au](https://seek.mikeohalloran.au/)

Built with [Claude](https://claude.ai), alongside the printed book it goes with. It's the sister project of [monster-book](https://github.com/mikeohallo/monster-book).

![The home page, a page half found, and everyone found](docs/screenshot.png)

## The story

After the [Monster Book](https://monsters.mikeohalloran.au/), the girl is getting a second book: a seek-and-find where the people hiding in the crowd are her own family, drawn as the cartoon versions she already knows from her stickers. Ten busy places (a toy shop, a playground, a swimming pool, the airport, a zoo and more), each across a two-page spread, coil-bound so it lies flat. The pages are being made one at a time, and each one goes onto the website as it's finished. She already does serious Where's Wally-style books, so the pictures are dense: 150 or more people on every spread, with the family the same size as everyone else.

The website is the same book on a phone. Same pictures, same family, same hiding places, plus things paper can't do: it knows when you've found someone, it can give a clue, and it remembers how far you got.

1. **Pick a page.** Each page shows who you've already found as coloured dots, and a star once everyone's found.
2. **Look.** Drag to move around and pinch to zoom on a phone; drag and scroll-wheel on a laptop. A phone held upright fills the screen with the picture and you pan sideways, like holding the book close.
3. **Tap.** Find someone and they get a ring in their colour, a chime, some confetti and a tick on their face in the row along the bottom. Tap nothing and you just get a little wobble, no buzzer.
4. **Stuck?** Press and hold a face, and a soft glow lights up roughly where they are. It's deliberately off-centre, so it narrows the search without giving the answer away.
5. **Everyone found.** A celebration, then on to the next page.

A gift link like `?for=Max` makes it "Max's Seek and Find" on that device.

## How it's built

**The book and the website come from the same file.** That's the main design decision.

The pictures are painted by Google AI Studio, but AI image models can't be trusted with a seek-and-find. Asked to hide the girl once, the first test drew her five times, gave Dad's tattoo to a stranger and invented a second Grandma. So the scenes are painted with no family in them at all, and the family are added afterwards in code, as cut-outs, at positions written down in one file (`scenes.json`). From that one file:

- the print pages are built (A4, 300 ppi, each spread split across two pages with the coil gap allowed for);
- the answers pages at the back of the book are drawn;
- the website's data is exported: each find's box as fractions of the picture.

So the answer key is right by construction, and the website and the book always agree.

The site itself follows the monster site: **one HTML file plus pictures.** No framework, no server, no accounts, no analytics, hosted free on Cloudflare Pages. Progress lives in `localStorage` on the device. The chime is synthesised with Web Audio, so there are no sound files. Nothing anyone does leaves their phone; the only outside request is Google Fonts.

### Things that turned out to matter

- **Density first.** The first mock had 40 people and was far too easy. A test prompt asking for "at least 150 tiny people" came back with about 160, all crisp at print size, so one image per spread is enough and the difficulty comes from the crowd, not tricks.
- **Nobody stands in front of a find who shouldn't.** A pasted cut-out is always on top, so if a child in the crowd is nearer the viewer than the hidden Dad, Dad looks like he's standing on her head. `hide.py spots` suggests places where the floor just below the feet is open, so there's nobody in front. Flat roofs read as open floor too, so each scene can list no-go boxes.
- **Peeking needs a ledge.** Some cut-outs peek over a wall. AI Studio always draws the wall as a line, with fingers gripping over it. The cutter erases the line but keeps the fingers, finding the line from the columns that stick out past the figure on both sides.
- **Dad is never mirrored.** His tattoo is on one arm. Flip the cut-out and it's on the other, so the builder refuses a flipped Dad.
- **Fingers are bigger than hidden people.** A find on a phone can be a few millimetres tall. Taps count within a box 40% bigger than the find, and never smaller than a fingertip on screen.
- **A drag isn't a tap.** Moving more than a few pixels turns a touch into a pan, so looking around never counts as a guess.
- **Nothing to read.** The faces along the bottom are the to-do list. Found ones get a tick in their colour.
- **Progress belongs to a picture, not a page number.** When the toy shop replaced the test playground as page 1, a phone that had finished the playground showed the toy shop as already done. Each page now carries a key made from its picture and hiding places, so ticks from an old version never carry over, and picture links include a fingerprint so phones fetch a changed picture instead of a cached one.

## What's in this repo

| Path | What it is |
|---|---|
| `index.html` | The whole site: markup, styles and script in one file, as hosted |
| `tools/site_src.html` | The same page as written for the Claude preview, before `make_site.py` wraps it for hosting |
| `tools/hide.py` | The book builder: cuts figures out of AI Studio character sheets, suggests and checks hiding places, builds the print pages, the who's-hiding page, the answers and the PDF, and exports the website's pictures and data |
| `tools/gen.py` | Makes the character sheets and scenes with Google AI Studio's image model (needs your own API key) |
| `tools/prompts.json` | The prompts for every character sheet and scene |
| `tools/make_site.py` | Wraps the page for hosting (plain link says "My Seek and Find") and zips it for Cloudflare Pages |
| `tools/test_site.py` | Drives the site in Chromium at phone and laptop size: every find, misses, reload, the finale, start again, zoom, drag, clues |
| `docs/` | Screenshot |

The pictures aren't in the repo; they're the book. Everything else is.

## Running it locally

The page needs to be served, not opened from a file:

```
python3 -m http.server 8000
```

Then open `http://localhost:8000`. Without `data.json` and the pictures you'll get the page frame with nothing to play, which is enough to see how it's put together.

## Credits

Pictures generated with Google AI Studio. Fonts: [Fredoka](https://fonts.google.com/specimen/Fredoka) and [Nunito](https://fonts.google.com/specimen/Nunito), both Open Font Licence. Site and tools written with Claude.

Made for my daughter.
