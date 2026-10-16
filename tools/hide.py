#!/usr/bin/env python3
"""hide.py: builder for the Seek-and-Find Book (A4 pages, A3 spreads, 300 ppi).

Folder layout (run from the book folder, e.g. C:\\Projects\\Seek and Find):
  hide.py, scenes.json        this script and the book data (every placement lives in scenes.json)
  fonts/Fredoka.ttf Nunito.ttf
  sheets/                     AI Studio character sheets (figures on plain white)
  cutouts/                    transparent PNG cut-outs made by `cut`
  scenes/                     AI Studio scene paintings, full size
  pages/                      finished A4 pages, pNN_*.jpg
  preview/                    things to look at before printing

Commands:
  python3 hide.py cut sheets/sheet_girl.jpg girl            poses default: stand,sit,walk,peek (reading order)
  python3 hide.py cut sheets/sheet_objects.jpg obj --poses shoes,teddy,unicorn
  python3 hide.py grid 1          preview/spread_01_grid.jpg: the fitted scene with a labelled 10 mm grid
  python3 hide.py spread 1        builds the two pages of spread 1 (plus a preview with answer circles)
  python3 hide.py check 1         checks every placement (prints warnings)
  python3 hide.py who             page 3: who to find
  python3 hide.py answers         pages 24-25
  python3 hide.py pdf             pages/*.jpg -> Seek_and_Find_All.pdf

Geometry (mm): A4 210 x 297. Outer margins 6 (Officeworks prints nothing within 5 of the edge).
Each spread is one continuous picture 420 x 249 across both pages; each page prints its half from
6 to 204 across and 6 to 255 down, so 12 mm of the picture (6 per page) falls under the coil.
Finds stay 20 mm clear of the coil edge (spread x 190-230). Key strip 258-291 down.
Even PDF pages are versos (coil on their right), odd pages rectos (coil on the left).
"""
import json, math, os, sys, argparse, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ---------------------------------------------------------------- geometry
PPI = 300
PAGE_W_MM, PAGE_H_MM = 210, 297
def mm(v): return int(round(v / 25.4 * PPI))
W, H = mm(PAGE_W_MM), mm(PAGE_H_MM)              # 2480 x 3508
MARGIN = 6
SCENE_TOP, SCENE_BOTTOM = 6, 255                 # scene band on every page
SCENE_H_MM = SCENE_BOTTOM - SCENE_TOP            # 249
SPREAD_W_MM = 2 * PAGE_W_MM                      # 420: the picture is continuous across both pages
COIL_CLEAR = 15                                  # key-strip elements stay this far from the coil edge
FIND_CLEAR = 20                                  # finds stay this far from the coil edge
KEY_TOP, KEY_BOTTOM = 257, 291
SPREAD_PX = (mm(SPREAD_W_MM), mm(SCENE_H_MM))    # 4961 x 2941

# ---------------------------------------------------------------- style (same as the Monster Book)
INK = (58, 40, 82)
CREAM = (255, 248, 236)
FAMILY = {'pink': (236, 106, 168), 'purple': (168, 128, 214), 'blue': (84, 166, 226),
          'green': (104, 178, 66), 'yellow': (242, 200, 40), 'orange': (244, 136, 44),
          'red': (232, 72, 72), 'teal': (54, 176, 170), 'plum': INK}
TITLE_CYCLE = ['pink', 'orange', 'yellow', 'green', 'blue', 'purple']
FREDOKA = os.path.join(HERE, 'fonts', 'Fredoka.ttf')
NUNITO = os.path.join(HERE, 'fonts', 'Nunito.ttf')

def font(path, size_px, weight):
    f = ImageFont.truetype(path, max(1, int(size_px)))
    try:
        f.set_variation_by_name(weight)
    except Exception:
        f.set_variation_by_name(weight.encode())
    return f

def rainbow_text(canvas, s, f, cx, baseline, stroke, colours=None, start=0, tilt=0.0, shadow=True):
    """Each letter in a family colour with a plum outline, centred at cx (px). Returns the width."""
    colours = colours or TITLE_CYCLE
    total = f.getlength(s)
    x = cx - total / 2
    asc, desc = f.getmetrics()
    k = start
    for ch in s:
        adv = f.getlength(ch)
        if ch.strip():
            pad = stroke * 3 + 20
            tile = Image.new('RGBA', (int(adv + 2 * pad), asc + desc + 2 * pad), (0, 0, 0, 0))
            d = ImageDraw.Draw(tile)
            col = FAMILY[colours[k % len(colours)]]
            d.text((pad, pad), ch, font=f, fill=col + (255,), stroke_width=stroke, stroke_fill=INK + (255,))
            if tilt:
                tile = tile.rotate(tilt if k % 2 else -tilt, resample=Image.BICUBIC, expand=False)
            px, py = int(x - pad), int(baseline - asc - pad)
            if shadow:
                a = tile.split()[-1].filter(ImageFilter.GaussianBlur(8)).point(lambda v: v * 55 // 255)
                sh = Image.new('RGBA', tile.size, INK + (0,)); sh.putalpha(a)
                canvas.alpha_composite(sh, (px + 5, py + 9))
            canvas.alpha_composite(tile, (px, py))
            k += 1
        x += adv
    return total

# ---------------------------------------------------------------- data
def load_book():
    with open('scenes.json', encoding='utf-8') as fh:
        return json.load(fh)

def save_book(book):
    with open('scenes.json', 'w', encoding='utf-8') as fh:
        json.dump(book, fh, indent=1, ensure_ascii=False)

def find_defs(book):
    return {f['id']: f for f in book['finds']}

def spread_def(book, n):
    for s in book['spreads']:
        if int(s['n']) == int(n):
            return s
    sys.exit(f'no spread {n} in scenes.json')

# ---------------------------------------------------------------- images
def resize_rgba(im, w, h):
    """Resize an RGBA image without light fringes (premultiplied alpha)."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    a = np.asarray(im.convert('RGBA')).astype(np.float32)
    alpha = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * alpha, a[..., 3:4]], axis=2)
    pm_im = Image.fromarray(pm.astype(np.uint8), 'RGBA').resize((w, h), Image.LANCZOS)
    b = np.asarray(pm_im).astype(np.float32)
    al = b[..., 3:4]
    rgb = np.where(al > 0, b[..., :3] * 255.0 / np.maximum(al, 1e-6), 0)
    out = np.concatenate([np.clip(rgb, 0, 255), al], axis=2).astype(np.uint8)
    return Image.fromarray(out, 'RGBA')

def alpha_bbox(im):
    a = np.asarray(im.split()[-1])
    ys, xs = np.where(a > 8)
    if len(xs) == 0:
        return (0, 0, im.width, im.height)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

def load_cut(name):
    p = os.path.join('cutouts', name + '.png')
    if not os.path.exists(p):
        sys.exit(f'missing cut-out {p}')
    im = Image.open(p).convert('RGBA')
    return im.crop(alpha_bbox(im))

def fit_scene(path, trim_top=1.0, trim_left=0.5):
    """Cover-fit the scene painting to the spread picture (4961 x 2941). trim_top: share of any
    vertical surplus removed from the top (1 = keep the bottom, drop sky). trim_left likewise."""
    im = Image.open(path).convert('RGB')
    tw, th = SPREAD_PX
    s = max(tw / im.width, th / im.height)
    nw, nh = int(math.ceil(im.width * s)), int(math.ceil(im.height * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    x0 = int(round((nw - tw) * trim_left)); y0 = int(round((nh - th) * trim_top))
    return im.crop((x0, y0, x0 + tw, y0 + th)), s

def place_px(p):
    """Pixel geometry of a placement: (x_centre, y_bottom, height) in spread px."""
    return mm(p['x']), mm(p['y']), mm(p['h'])

def render_spread(book, sd, with_finds=True):
    """The full spread picture (RGB, 4961 x 2941) with every placement composited."""
    scene, _ = fit_scene(os.path.join('scenes', sd['scene']), sd.get('trim_top', 1.0), sd.get('trim_left', 0.5))
    canvas = scene.convert('RGBA')
    if with_finds:
        for p in sd.get('places', []):
            cut = load_cut(p['cut'])
            if p.get('flip'):
                cut = ImageOps.mirror(cut)
            cx, by, hpx = place_px(p)
            s = hpx / cut.height
            cut = resize_rgba(cut, cut.width * s, hpx)
            if p.get('rotate'):
                cut = cut.rotate(p['rotate'], resample=Image.BICUBIC, expand=True)
            x = int(round(cx - cut.width / 2)); y = int(round(by - cut.height))
            canvas.alpha_composite(cut, (x, y))
    return canvas.convert('RGB')

def page_canvas():
    return Image.new('RGB', (W, H), (255, 255, 255))

def paste_scene_half(page, spread_im, side):
    """side 'L' = verso (spread x 0-210 -> page), 'R' = recto (spread x 210-420 -> page)."""
    off = 0 if side == 'L' else mm(PAGE_W_MM)
    x0, x1 = mm(MARGIN), mm(PAGE_W_MM - MARGIN)
    part = spread_im.crop((off + x0, 0, off + x1, spread_im.height))
    page.paste(part, (x0, mm(SCENE_TOP)))

# ---------------------------------------------------------------- key strip
def portrait(fd, diameter_px, ring_px):
    """Round portrait of a find: its cut-out cropped to the head, in a coloured ring."""
    cut = load_cut(fd['portrait'])
    bw, bh = cut.size
    box = fd.get('portrait_box')          # fractions of the cut-out's box: x0, y0, x1, y1
    if box:
        x0, y0, x1, y1 = box[0] * bw, box[1] * bh, box[2] * bw, box[3] * bh
    else:
        side = fd.get('portrait_zoom', 0.6) * bh
        x0, y0 = bw / 2 - side / 2, -0.03 * bh
        x1, y1 = x0 + side, y0 + side
    # the crop may run outside the cut-out: pad with transparent
    pad = int(max(0, -x0, -y0, x1 - bw, y1 - bh)) + 2
    padded = Image.new('RGBA', (bw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
    padded.alpha_composite(cut, (pad, pad))
    crop = padded.crop((int(x0 + pad), int(y0 + pad), int(x1 + pad), int(y1 + pad)))
    inner = diameter_px - 2 * ring_px
    if fd.get('portrait_fit') == 'contain':      # whole crop inside the ring (a pair, an object)
        s = inner * 0.9 / max(crop.width, crop.height)
    else:                                        # fill the ring (a single face)
        s = inner / min(crop.width, crop.height)
    crop = resize_rgba(crop, crop.width * s, crop.height * s)
    disc = Image.new('RGBA', (diameter_px, diameter_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(disc)
    d.ellipse([0, 0, diameter_px - 1, diameter_px - 1], fill=FAMILY[fd['colour']] + (255,))
    d.ellipse([ring_px, ring_px, diameter_px - 1 - ring_px, diameter_px - 1 - ring_px], fill=(255, 255, 255, 255))
    face = Image.new('RGBA', (diameter_px, diameter_px), (0, 0, 0, 0))
    face.alpha_composite(crop, (int((diameter_px - crop.width) / 2), int((diameter_px - crop.height) / 2)))
    mask = Image.new('L', (diameter_px, diameter_px), 0)
    ImageDraw.Draw(mask).ellipse([ring_px, ring_px, diameter_px - 1 - ring_px, diameter_px - 1 - ring_px], fill=255)
    face.putalpha(ImageOps.multiply(face.split()[-1], mask) if hasattr(ImageOps, 'multiply') else
                  Image.fromarray((np.asarray(face.split()[-1]).astype(np.uint16) * np.asarray(mask) // 255).astype(np.uint8)))
    disc.alpha_composite(face)
    d = ImageDraw.Draw(disc)
    d.ellipse([0, 0, diameter_px - 1, diameter_px - 1], outline=INK, width=max(2, mm(0.5)))
    return disc

def draw_key_strip(page, book, sd, side):
    """Portraits with names along the bottom of a page; the recto also carries the spread title."""
    finds = book['finds']
    nL = (len(finds) + 1) // 2
    group = finds[:nL] if side == 'L' else finds[nL:]
    dia = mm(book.get('portrait_mm', 23)); ring = mm(1.3)
    cy = mm(KEY_TOP) + dia // 2 + mm(0.5)
    can = page.convert('RGBA')
    d = ImageDraw.Draw(can)
    f_name = font(NUNITO, mm(4.4), 'Bold')
    if side == 'L':
        x0, x1 = MARGIN, PAGE_W_MM - COIL_CLEAR
        centres = [mm(x0 + (x1 - x0) * (i + 0.5) / len(group)) for i in range(len(group))]
    else:
        f_t = font(FREDOKA, mm(8.5), 'Bold')
        title = sd['title']
        tw = f_t.getlength(title)
        cx_t = mm(COIL_CLEAR + 3) + tw / 2
        rainbow_text(can, title, f_t, cx_t, cy + mm(3), stroke=mm(0.55), start=int(sd['n']) % 6, tilt=2.5)
        x0 = (cx_t + tw / 2) / mm(1) + 6
        x1 = PAGE_W_MM - MARGIN
        centres = [mm(x0 + (x1 - x0) * (i + 0.5) / len(group)) for i in range(len(group))]
    slot = (centres[1] - centres[0]) if len(centres) > 1 else mm(40)
    for fd, cx in zip(group, centres):
        pt = portrait(fd, dia, ring)
        can.alpha_composite(pt, (int(cx - dia / 2), int(cy - dia / 2)))
        label_lines(d, fd['label'], f_name, cx, cy + dia / 2 + mm(1.2), slot - mm(2), mm(5.0))
    page.paste(can.convert('RGB'))

def label_lines(d, text, f, cx, top, max_w, line_h):
    """Centred label, wrapped onto two lines when it doesn't fit (splitting after '&' if present)."""
    if f.getlength(text) <= max_w:
        d.text((cx, top), text, font=f, fill=INK, anchor='ma')
        return
    if ' & ' in text:
        a, b = text.split(' & ', 1)
        lines = [a + ' &', b]
    else:
        words = text.split()
        lines, cur = [], ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if f.getlength(t) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    for i, ln in enumerate(lines):
        d.text((cx, top + i * line_h), ln, font=f, fill=INK, anchor='ma')

# ---------------------------------------------------------------- commands
def page_names(n):
    n = int(n)
    return f'p{2 * n + 2:02d}_s{n:02d}L.jpg', f'p{2 * n + 3:02d}_s{n:02d}R.jpg'

def save_jpg(im, path, q=94):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    im.save(path, quality=q, dpi=(PPI, PPI), subsampling=0)

def cmd_spread(args):
    book = load_book(); sd = spread_def(book, args.n)
    sp = render_spread(book, sd)
    left, right = page_names(sd['n'])
    for side, name in (('L', left), ('R', right)):
        page = page_canvas()
        paste_scene_half(page, sp, side)
        draw_key_strip(page, book, sd, side)
        save_jpg(page, os.path.join('pages', name))
        print('saved pages/' + name)
    preview_book(book, sd, sp, answers=True)
    check(book, sd, sp)

def preview_book(book, sd, sp, answers=False, scale=4):
    """The open book at 1/scale, with answer circles if asked."""
    left, right = page_names(sd['n'])
    L = Image.open(os.path.join('pages', left)); R = Image.open(os.path.join('pages', right))
    gap = mm(4)
    book_im = Image.new('RGB', (2 * W + gap, H), (200, 200, 200))
    book_im.paste(L, (0, 0)); book_im.paste(R, (W + gap, 0))
    if answers:
        d = ImageDraw.Draw(book_im)
        fds = find_defs(book)
        for p in sd.get('places', []):
            if not p.get('find'):
                continue
            cx, by, hpx = place_px(p)
            cy = by - hpx / 2
            r = max(hpx * 0.9, mm(9))
            px = cx if p['x'] < PAGE_W_MM else cx + gap
            py = mm(SCENE_TOP) + cy
            col = FAMILY[fds[p['find']]['colour']]
            d.ellipse([px - r, py - r, px + r, py + r], outline=col, width=mm(1.6))
            d.ellipse([px - r - mm(1.6), py - r - mm(1.6), px + r + mm(1.6), py + r + mm(1.6)], outline=INK, width=mm(0.4))
    small = book_im.resize((book_im.width // scale, book_im.height // scale), Image.LANCZOS)
    os.makedirs('preview', exist_ok=True)
    out = f'preview/spread_{int(sd["n"]):02d}' + ('_answers' if answers else '') + '.jpg'
    small.save(out, quality=88)
    print('saved', out)
    if answers:                       # and the plain one
        plain = Image.new('RGB', (2 * W + gap, H), (200, 200, 200))
        plain.paste(L, (0, 0)); plain.paste(R, (W + gap, 0))
        plain.resize((plain.width // scale, plain.height // scale), Image.LANCZOS).save(
            f'preview/spread_{int(sd["n"]):02d}.jpg', quality=88)

def cmd_grid(args):
    """The fitted scene with a labelled 10 mm grid in spread coordinates, for picking placements."""
    book = load_book(); sd = spread_def(book, args.n)
    sp = render_spread(book, sd, with_finds=args.finds)
    scale = 2.5
    im = sp.resize((int(sp.width / scale), int(sp.height / scale)), Image.LANCZOS).convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = font(NUNITO, 22, 'Bold')
    for x in range(0, SPREAD_W_MM + 1, 10):
        px = mm(x) / scale
        major = x % 50 == 0
        d.line([(px, 0), (px, im.height)], fill=(255, 255, 255, 170 if major else 90), width=2 if major else 1)
        if major:
            d.text((px + 3, 3), str(x), font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for y in range(0, SCENE_H_MM + 1, 10):
        py = mm(y) / scale
        major = y % 50 == 0
        d.line([(0, py), (im.width, py)], fill=(255, 255, 255, 170 if major else 90), width=2 if major else 1)
        if major:
            d.text((3, py + 3), str(y), font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    # the coil zone and the unprintable strip
    d.rectangle([mm(PAGE_W_MM - FIND_CLEAR) / scale, 0, mm(PAGE_W_MM + FIND_CLEAR) / scale, im.height], fill=(255, 0, 0, 40))
    d.rectangle([mm(PAGE_W_MM - MARGIN) / scale, 0, mm(PAGE_W_MM + MARGIN) / scale, im.height], fill=(255, 0, 0, 110))
    im.alpha_composite(ov)
    os.makedirs('preview', exist_ok=True)
    out = f'preview/spread_{int(sd["n"]):02d}_grid.jpg'
    im.convert('RGB').save(out, quality=88)
    print('saved', out)

def check(book, sd, sp=None):
    fds = find_defs(book)
    places = sd.get('places', [])
    warn = []
    seen = {}
    for p in places:
        if p.get('find'):
            seen[p['find']] = seen.get(p['find'], 0) + 1
    for fid in fds:
        if seen.get(fid, 0) != 1:
            warn.append(f'{fid}: placed {seen.get(fid, 0)} times (want 1)')
    boxes = []
    for p in places:
        cut = load_cut(p['cut'])
        hmm = p['h']; wmm = hmm * cut.width / cut.height
        x0, x1 = p['x'] - wmm / 2, p['x'] + wmm / 2
        y0, y1 = p['y'] - hmm, p['y']
        tag = p.get('find') or p['cut']
        if p.get('find'):
            fd = fds[p['find']]
            if fd.get('noflip') and p.get('flip'):
                warn.append(f'{tag}: flipped, but this character must not be mirrored')
            lo, hi = sd.get('h_range', [12, 30])
            if not (lo <= hmm <= hi):
                warn.append(f'{tag}: height {hmm} mm outside this spread\'s range {lo}-{hi}')
            if x1 > PAGE_W_MM - FIND_CLEAR and x0 < PAGE_W_MM + FIND_CLEAR:
                warn.append(f'{tag}: within {FIND_CLEAR} mm of the coil (x {x0:.0f}-{x1:.0f})')
            if x0 < MARGIN + 2 or x1 > SPREAD_W_MM - MARGIN - 2 or y0 < 2 or y1 > SCENE_H_MM - 1:
                warn.append(f'{tag}: too close to the page edge (x {x0:.0f}-{x1:.0f}, y {y0:.0f}-{y1:.0f})')
            for (ox0, oy0, ox1, oy1, otag) in boxes:
                if x0 < ox1 and ox0 < x1 and y0 < oy1 and oy0 < y1:
                    warn.append(f'{tag} overlaps {otag}')
            if sp is not None:          # is the patch around it busy enough?
                g = np.asarray(sp.convert('L')).astype(np.float32)
                X0, Y0 = max(0, mm(x0 - hmm)), max(0, mm(y0 - hmm * 0.5))
                X1, Y1 = min(g.shape[1], mm(x1 + hmm)), min(g.shape[0], mm(y1 + hmm * 0.5))
                sdv = float(g[Y0:Y1, X0:X1].std())
                if sdv < 38:
                    warn.append(f'{tag}: quiet patch around it (contrast {sdv:.0f}); move it somewhere busier')
        else:
            if x1 > PAGE_W_MM - MARGIN and x0 < PAGE_W_MM + MARGIN:
                warn.append(f'{tag}: a decoy or prop is split by the coil')
        boxes.append((x0, y0, x1, y1, tag))
    print(f'spread {sd["n"]}: {len(places)} placements, {len(warn)} warnings')
    for w in warn:
        print('  !', w)
    return warn

def cmd_check(args):
    book = load_book(); sd = spread_def(book, args.n)
    check(book, sd, render_spread(book, sd, with_finds=False))

# ---------------------------------------------------------------- spot finder
def busy_map(sp, res=2):
    """Edge density of the scene at `res` px per mm: high where people and things are drawn,
    low on open grass, path, sand or floor."""
    g = sp.convert('L').resize((SPREAD_W_MM * res, SCENE_H_MM * res), Image.LANCZOS)
    a = np.asarray(g).astype(np.float32)
    mag = np.hypot(ndimage.sobel(a, 0), ndimage.sobel(a, 1))
    return ndimage.uniform_filter((mag > 60).astype(np.float32), size=3)

def box_mean(ii, x0, y0, x1, y1):
    """Mean of the map over [x0,x1) x [y0,y1) using an integral image."""
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(ii.shape[1] - 1, int(x1)), min(ii.shape[0] - 1, int(y1))
    if x1 <= x0 or y1 <= y0:
        return 1.0
    s = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    return s / ((x1 - x0) * (y1 - y0))

def cmd_spots(args):
    """Suggest placements: feet on open ground with open ground just below (so nobody stands in
    front of the find), the find's box over the crowd, finds spread out, every rule in `check`
    respected. With --apply the suggestions replace x and y in scenes.json (cut and h are kept;
    entries marked "fixed": true are left alone)."""
    book = load_book(); sd = spread_def(book, args.n)
    sp = render_spread(book, sd, with_finds=False)
    res = 2
    busy = busy_map(sp, res)
    ii = np.pad(busy.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    places = sd.get('places', [])
    chosen = [(p['x'], p['y'] - p['h'] / 2) for p in places if p.get('fixed')]
    rng = np.random.default_rng(args.seed)
    lefts = sum(1 for p in places if p.get('fixed') and p['x'] < PAGE_W_MM)
    for p in places:
        if p.get('fixed') or not p.get('find'):
            continue
        cut = load_cut(p['cut'])
        h = p['h']; w = h * cut.width / cut.height
        lying = p['cut'].startswith('obj_') and ('flat' in p['cut'] or 'lie' in p['cut'])
        best = []
        avoid = sd.get('avoid', [])        # [x0, y0, x1, y1] boxes in mm: roofs, walls, water...
        for x in np.arange(MARGIN + 4 + w / 2, SPREAD_W_MM - MARGIN - 4 - w / 2, 2.0):
            if x + w / 2 > PAGE_W_MM - FIND_CLEAR and x - w / 2 < PAGE_W_MM + FIND_CLEAR:
                continue
            for y in np.arange(h + 6, SCENE_H_MM - 4, 2.0):
                if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in avoid):
                    continue
                X0, X1 = (x - 0.4 * w) * res, (x + 0.4 * w) * res
                below = box_mean(ii, X0, y * res, X1, (y + 0.3 * h) * res)
                feet = box_mean(ii, X0, (y - 0.15 * h) * res, X1, y * res)
                body = box_mean(ii, (x - w / 2) * res, (y - h) * res, (x + w / 2) * res, (y - 0.15 * h) * res)
                if lying:          # an object lying on the ground: its whole box should be open ground
                    score = box_mean(ii, (x - w / 2) * res, (y - h) * res, (x + w / 2) * res, y * res) + 0.5 * below
                else:
                    score = below + 0.6 * feet + 0.25 * max(0.0, 0.15 - body)
                best.append((score, float(x), float(y)))
        best.sort()
        # take the best-scoring spot far enough from the others, balancing the two pages
        want_left = lefts < (len([q for q in places if q.get('find')]) + 1) // 2
        pick = None
        for score, x, y in best[:4000]:
            cy = y - h / 2
            if any(math.hypot(x - ox, cy - oy) < args.spacing for ox, oy in chosen):
                continue
            if args.balance and (x < PAGE_W_MM) != want_left and score > best[0][0] + 0.05:
                continue
            pick = (score, x, y); break
        if pick is None:
            print(f'{p["find"]}: no spot found'); continue
        score, x, y = pick
        chosen.append((x, y - h / 2))
        lefts += x < PAGE_W_MM
        print(f'{p["find"]:20s} {p["cut"]:22s} x {x:5.0f}  y {y:5.0f}  h {h:4.1f}  (ground score {score:.3f})')
        if args.apply:
            p['x'], p['y'] = round(x), round(y)
    if args.apply:
        save_book(book); print('scenes.json updated')

# ---------------------------------------------------------------- hide again: spots for new rounds
# On the website, "Hide everyone again" puts the family in new places. Each spread lists checked spots
# ("slots": feet position x, y in spread mm and a kind), and the site picks a fresh mix for every round.
# Kinds: p = room for one person, w = wide enough for the grandparents (also fits one person),
# o = a toy on the ground. Sizes on the website come from the crowd at each spot's depth (WEB_SIZE below).
ROUND_POSES = {     # find: [(cut, height as a share of A, may be mirrored)]; Dad is never mirrored
    'girl': [('girl_walk', .70, True), ('girl_stand', .70, True)],
    'dad': [('dad_stand', 1.0, False), ('dad_walk', 1.0, False)],
    'mum': [('mum_walk', .96, True), ('mum_stand', .96, True)],
    'grandma': [('grandma_stand', .93, True), ('grandma_walk', .93, True)],
    'uncle': [('uncle_stand', 1.0, True), ('uncle_walk', 1.0, True)],
    'grandparents': [('grandparents_walk', .96, True), ('grandparents_stand', .96, True)],
    'shoes': [('obj_shoes_flat', .19, True)],
    'teddy': [('obj_teddy_sit', .29, True), ('obj_teddy_lie', .27, True)],
    'unicorn': [('obj_unicorn_stand', .32, True)],
}
ROUND_KINDS = {'grandparents': 'w', 'shoes': 'o', 'teddy': 'o', 'unicorn': 'o'}   # others: 'pw'
# Sizes on the website (16 Oct). Mike, after the girl had played every page: the grown-ups look a little big
# next to the people in the pictures, the ballet shoes and the unicorn a little small. Measuring the crowd
# showed why: most scenes have perspective (people further up the picture are smaller), but the book used
# one size per find per page, and new rounds one size for every spot. So each spread now lists `crowd`:
# [y, height] points, the height of a grown-up in the crowd with feet at y (spread mm), measured on 5 to 15
# grown-ups per page (and children where there were no grown-ups), joined by straight lines and flat past
# the ends. Every find on the website is sized from it: WEB_SIZE is each cut-out's height as a share of a
# crowd grown-up at the same depth. Grown-ups match the crowd (Dad and the uncle 1.0, the others their book
# share of Dad's height); the girl keeps her book share of Dad's height (crowd children vary too much to
# measure against); the doll, the shoes and the unicorn keep their book size relative to the crowd on
# average (the median over the ten pages), the shoes and unicorn 30% bigger than that. Used for the book's places and for new rounds. Sizes
# are not part of a page's key, so changing them keeps every device's ticks and rounds. Hanging things
# keep their top where it is (the hook).
WEB_SIZE = {
    'dad_stand': 1.0, 'dad_walk': 1.0, 'uncle_stand': 1.0, 'uncle_walk': 1.0,
    'mum_walk': .96, 'mum_stand': .96, 'mum_sit': .73,
    'grandma_stand': .93, 'grandma_walk': .93,
    'grandparents_walk': .96, 'grandparents_stand': .96,
    'girl_walk': .74, 'girl_stand': .74,                  # her book share of Dad's height
    'obj_teddy_sit': .34, 'obj_teddy_lie': .32,
    'obj_unicorn_stand': .49, 'obj_unicorn_peek': .46,      # 1.3 x the book's median (.38 and .35)
    'obj_shoes_flat': .30, 'obj_shoes_hang': .44,            # 1.3 x the book's median (.23 and .34)
}
# The toys are never smaller than in the book: at least this many times their book size (book places), or
# their book share of Dad's book height A (new rounds). Mike asked for bigger shoes and unicorn, and on the
# pages where the grown-ups shrink a lot (the airport, the party) the crowd rule alone would shrink them.
OBJ_GROW = {'shoes': 1.3, 'unicorn': 1.3, 'teddy': 1.0}
HANGING = {'obj_shoes_hang'}
SLOT_TEST = {'p': ('uncle_walk', 1.0), 'w': ('grandparents_walk', .96), 'o': ('obj_teddy_lie', .27)}

def adult_h(sd):
    return next(p['h'] for p in sd['places'] if p.get('find') == 'dad')

def crowd_h(sd, y):
    """Height of a grown-up in the crowd with feet at y (spread mm): the spread's `crowd` points joined by
    straight lines, flat past the ends. Spreads without `crowd` fall back to Dad's height in the book."""
    pts = sorted(sd.get('crowd') or [])
    if not pts:
        return adult_h(sd)
    if y <= pts[0][0]:
        return pts[0][1]
    for (y0, h0), (y1, h1) in zip(pts, pts[1:]):
        if y <= y1:
            return h0 + (h1 - h0) * (y - y0) / (y1 - y0)
    return pts[-1][1]

def floor_mask(sp, refs, res=4, tol=22):
    """Open ground at `res` px per mm: close to one of the floor colours sampled at `refs`
    (spread mm) and smooth (no outlines or detail)."""
    small = sp.resize((SPREAD_W_MM * res, SCENE_H_MM * res), Image.LANCZOS)
    a = np.asarray(small).astype(np.float32)
    cols = [a[int(y * res), int(x * res)] for x, y in refs]
    dist = np.min(np.stack([np.sqrt(((a - c) ** 2).sum(-1)) for c in cols]), axis=0)
    g = np.asarray(small.convert('L')).astype(np.float32)
    mag = np.hypot(ndimage.sobel(g, 0), ndimage.sobel(g, 1))
    return ndimage.binary_opening((dist < tol) & (mag < 60), iterations=1)

def place_on(sp, items):
    """Composite [(cut, x, y, h, flip)] (spread mm) onto a copy of the spread picture."""
    can = sp.convert('RGBA')
    for cut_name, x, y, h, flip in items:
        cut = load_cut(cut_name)
        if flip:
            cut = ImageOps.mirror(cut)
        hpx = mm(h); cut = resize_rgba(cut, cut.width * hpx / cut.height, hpx)
        can.alpha_composite(cut, (int(round(mm(x) - cut.width / 2)), int(round(mm(y) - cut.height))))
    return can.convert('RGB')

def test_h(sd, k, y):
    """Height of the stand-in figure for a spot of kind k at depth y: as on the website when the spread
    has crowd heights, else a share of Dad's book height."""
    cut_name, share = SLOT_TEST[k]
    return WEB_SIZE[cut_name] * crowd_h(sd, y) if sd.get('crowd') else share * adult_h(sd)

def slot_sheet(sp, sd, slots, out, label_from=0):
    """Review sheet: every slot with its test figure in place, cropped and numbered."""
    f = ImageFont.truetype(NUNITO, 30) if os.path.exists(NUNITO) else ImageFont.load_default()
    tiles = []
    for i, (x, y, k) in enumerate(slots):
        cut_name = SLOT_TEST[k][0]
        h = test_h(sd, k, y); w = h * load_cut(cut_name).width / load_cut(cut_name).height
        im = place_on(sp, [(cut_name, x, y, h, False)])
        box = (mm(x - w / 2 - max(w * .8, h * .45)), mm(y - h * 1.35), mm(x + w / 2 + max(w * .8, h * .45)), mm(y + h * .4))
        t = im.crop(box); t = t.resize((360, round(t.height * 360 / t.width)), Image.LANCZOS)
        d = ImageDraw.Draw(t)
        d.text((6, 4), f'{label_from + i} {k}', font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
        tiles.append(t)
    if not tiles:
        return
    cols = 4; th = max(t.height for t in tiles); rows = math.ceil(len(tiles) / cols)
    sheet = Image.new('RGB', (cols * 364, rows * (th + 4)), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 364, (i // cols) * (th + 4)))
    sheet.save(out, quality=84)
    print('saved', out)

def cmd_slots(args):
    """Suggest spots for new rounds and draw review sheets; with --keep, save the approved ones.
        slots N --refs "x,y x,y ..."     floor colours to treat as open ground (saved in scenes.json)
        slots N --keep "1,4,7"           keep these candidates (numbers from the review sheets)
    Candidates: the feet and a strip just below them are on open ground (nobody in front), spots at
    least --spacing x A apart, clear of the coil and the edges."""
    book = load_book(); sd = spread_def(book, args.n)
    n = int(sd['n']); cand_path = os.path.join('preview', f'slots_{n:02d}.json')
    sp = render_spread(book, sd, with_finds=False)
    A = adult_h(sd)
    if args.keep is not None:
        cands = json.load(open(cand_path, encoding='utf-8'))
        keep = [int(v) for v in args.keep.replace(' ', ',').split(',') if v.strip()]
        sd['slots'] = [[round(cands[i][0], 1), round(cands[i][1], 1), cands[i][2]] for i in keep]
        save_book(book)
        kinds = {k: sum(1 for s in sd['slots'] if s[2] == k) for k in 'pwo'}
        print(f'spread {n}: {len(sd["slots"])} slots kept {kinds}')
        marks = place_on(sp, [(SLOT_TEST[k][0], x, y, test_h(sd, k, y), False) for x, y, k in sd['slots']])
        marks.resize((marks.width // 3, marks.height // 3), Image.LANCZOS).save(os.path.join('preview', f'slots_{n:02d}_all.jpg'), quality=85)
        return
    if args.refs:
        sd['floor'] = [[float(v) for v in r.split(',')] for r in args.refs.split()]
        save_book(book)
    refs = sd.get('floor')
    if not refs:
        sys.exit('give --refs "x,y x,y" (spread mm points on open floor) the first time')
    res = 4
    floor = floor_mask(sp, refs, res).astype(np.float32)
    ii = np.pad(floor.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    def fm(x0, y0, x1, y1):
        X0, Y0, X1, Y1 = [int(round(v * res)) for v in (x0, y0, x1, y1)]
        X0, Y0 = max(0, X0), max(0, Y0); X1, Y1 = min(floor.shape[1], X1), min(floor.shape[0], Y1)
        if X1 <= X0 or Y1 <= Y0:
            return 0.0
        return float((ii[Y1, X1] - ii[Y0, X1] - ii[Y1, X0] + ii[Y0, X0]) / ((X1 - X0) * (Y1 - Y0)))
    want = {'w': args.wide, 'p': args.person, 'o': args.objects}
    taken = []
    out = []
    # the book's own hiding places are good spots for someone else in a new round
    for p in sd['places']:
        k = {'grandparents': 'w'}.get(p.get('find'), 'p')
        if p.get('find') in ('shoes', 'teddy', 'unicorn') or not p['cut'].split('_')[-1] in ('stand', 'walk'):
            continue
        taken.append((p['x'], p['y'])); out.append([float(p['x']), float(p['y']), k])
    for k in ('w', 'p', 'o'):
        cut_name, share = SLOT_TEST[k]
        cut = load_cut(cut_name); h = share * A; w = h * cut.width / cut.height
        cands = []
        for x in np.arange(MARGIN + 4 + w / 2, SPREAD_W_MM - MARGIN - 4 - w / 2, 1.0):
            if x + w / 2 > PAGE_W_MM - FIND_CLEAR and x - w / 2 < PAGE_W_MM + FIND_CLEAR:
                continue
            for y in np.arange(h + 3, SCENE_H_MM - 3, 1.0):
                if k == 'o':
                    if fm(x - w / 2, y - h, x + w / 2, y) < .85 or fm(x - w / 2, y, x + w / 2, y + 2) < .8:
                        continue
                    busy = 1 - fm(x - w * 1.5, y - h * 2, x + w * 1.5, y + h)
                else:
                    if fm(x - .4 * w, y - .22 * h, x + .4 * w, y) < args.legs or fm(x - .42 * w, y, x + .42 * w, y + .12 * h) < args.below:
                        continue
                    busy = 1 - fm(x - .5 * w, y - h, x + .5 * w, y - .25 * h)
                cands.append((busy + .03 * rng_jitter(x, y), float(x), float(y)))
        cands.sort(reverse=True)
        got = 0
        for busy, x, y in cands:
            if got >= want[k]:
                break
            if any(math.hypot(x - tx, y - ty) < args.spacing * A for tx, ty in taken):
                continue
            taken.append((x, y)); out.append([x, y, k]); got += 1
        print(f'{k}: {len(cands)} positions pass, {got} suggested')
    os.makedirs('preview', exist_ok=True)
    json.dump(out, open(cand_path, 'w', encoding='utf-8'))
    half = math.ceil(len(out) / 2)
    slot_sheet(sp, sd, out[:half], os.path.join('preview', f'slots_{n:02d}_a.jpg'), 0)
    slot_sheet(sp, sd, out[half:], os.path.join('preview', f'slots_{n:02d}_b.jpg'), half)

def rng_jitter(x, y):
    """A fixed pseudo-random number in [0, 1) per position, so ties don't all cluster in one corner."""
    return (math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1.0

# ---------------------------------------------------------------- website export
def file_ver(path):
    """A short fingerprint of a file's contents, for ?v= links."""
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()[:8]

def cmd_web(args):
    """Export the website's pictures and data from scenes.json into OUT (default website/upload):
    scenes/sNN.webp (the empty spread, 3200 px wide), thumbs/sNN.webp (640 px, also empty, so the home
    page gives nothing away), cuts/<name>.webp (every cut-out, 400 px tall), portraits/<id>.webp (the
    key portraits, 240 px) and data.json. The site places the family on the empty picture itself:
    the book's places on a first play, and a new mix of the spread's checked spots on "Hide everyone
    again". data.json holds the finds, the poses allowed in new rounds, each cut-out's shape, and per
    spread the adult height A, the book's places, their boxes as fractions of the picture, and the spots.
    Sizes on the website follow the crowd: WEB_SIZE x crowd_h at each find's depth, for the book's places
    and (via each spot's crowd height) for new rounds."""
    book = load_book()
    out = args.out
    for d in ('scenes', 'thumbs', 'portraits', 'cuts'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    data = {'title': book.get('title', ''), 'mm': [SPREAD_W_MM, SCENE_H_MM], 'finds': [], 'spreads': [],
            'cuts': {}, 'poses': {}}
    for fd in book['finds']:
        pt = portrait(fd, 240, 14)
        pt.save(os.path.join(out, 'portraits', fd['id'] + '.webp'), quality=90, method=6)
        data['finds'].append({'id': fd['id'], 'label': fd['label'], 'say': fd.get('say', fd['label']),
                              'colour': '#%02X%02X%02X' % FAMILY[fd['colour']],
                              'portrait': f"portraits/{fd['id']}.webp?v={file_ver(os.path.join(out, 'portraits', fd['id'] + '.webp'))}"})
        # f: height as a share of a crowd grown-up at the spot's depth (each spot carries that height)
        # m: the least height as a share of A (toys only, so they're never smaller than in the book)
        g = OBJ_GROW.get(fd['id'])
        data['poses'][fd['id']] = [dict({'cut': c, 'f': WEB_SIZE[c], 'flip': fl, 'k': ROUND_KINDS.get(fd['id'], 'pw')},
                                        **({'m': round(share * g, 3)} if g else {}))
                                   for c, share, fl in ROUND_POSES[fd['id']]]
    # the cut-outs: the site places the family itself (the book's places first, new ones on "Hide again")
    cut_names = sorted({p['cut'] for sd in book['spreads'] for p in sd.get('places', [])} |
                       {c for poses in ROUND_POSES.values() for c, _, _ in poses})
    for name in cut_names:
        cut = load_cut(name)
        hpx = args.cut_height
        small = resize_rgba(cut, cut.width * hpx / cut.height, hpx)
        path = os.path.join(out, 'cuts', name + '.webp')
        small.save(path, 'WEBP', quality=88, method=6)
        data['cuts'][name] = {'src': f"cuts/{name}.webp?v={file_ver(path)}", 'a': round(cut.width / cut.height, 4)}
    for sd in book['spreads']:
        if not os.path.exists(os.path.join('scenes', sd['scene'])):
            print(f'spread {sd["n"]}: scene file missing, skipped'); continue
        n = int(sd['n'])
        sp = render_spread(book, sd, with_finds=False)       # the empty picture: the site adds the family
        wpx = args.width; hpx = round(sp.height * wpx / sp.width)
        sp.resize((wpx, hpx), Image.LANCZOS).save(os.path.join(out, 'scenes', f's{n:02d}.webp'), quality=args.quality, method=6)
        sp.resize((640, round(sp.height * 640 / sp.width)), Image.LANCZOS).save(
            os.path.join(out, 'thumbs', f's{n:02d}.webp'), quality=80, method=6)
        boxes, book_places = [], []
        for p in sd.get('places', []):
            if not p.get('find'):
                continue
            cut = load_cut(p['cut'])
            h = round(max(WEB_SIZE[p['cut']] * crowd_h(sd, p['y']), p['h'] * OBJ_GROW.get(p['find'], 0)), 1)
            y = round(p['y'] - p['h'] + h, 1) if p['cut'] in HANGING else p['y']    # feet stay put; hanging keeps its top
            w = h * cut.width / cut.height
            boxes.append({'id': p['find'],
                          'box': [round((p['x'] - w / 2) / SPREAD_W_MM, 5), round((y - h) / SCENE_H_MM, 5),
                                  round((p['x'] + w / 2) / SPREAD_W_MM, 5), round(y / SCENE_H_MM, 5)]})
            book_places.append({'id': p['find'], 'cut': p['cut'], 'x': p['x'], 'y': y, 'h': h,
                                'flip': bool(p.get('flip'))})
        slots = sd.get('slots', [])
        web_slots = [[x, y, k, round(crowd_h(sd, y), 1)] for x, y, k in slots]    # + crowd height at that depth
        # key: changes when the picture, the hiding places or the spots change, so the site never shows old
        # ticks on a new picture; ?v= makes phones fetch a changed picture instead of a cached one
        spec = json.dumps({'scene': sd['scene'], 'trim': [sd.get('trim_top', 1.0), sd.get('trim_left', 0.5)],
                           'places': sd.get('places', []), 'slots': slots}, sort_keys=True)
        key = f'{n}-' + hashlib.md5(spec.encode()).hexdigest()[:6]
        data['spreads'].append({'n': n, 'key': key, 'title': sd['title'],
                                'img': f"scenes/s{n:02d}.webp?v={file_ver(os.path.join(out, 'scenes', f's{n:02d}.webp'))}",
                                'thumb': f"thumbs/s{n:02d}.webp?v={file_ver(os.path.join(out, 'thumbs', f's{n:02d}.webp'))}",
                                'w': wpx, 'h': hpx, 'A': adult_h(sd), 'finds': boxes, 'book': book_places, 'slots': web_slots})
        kb = os.path.getsize(os.path.join(out, 'scenes', f's{n:02d}.webp')) // 1024
        print(f'spread {n}: {sd["title"]}, {len(boxes)} finds, {len(slots)} spots for new rounds, {wpx} x {hpx} px, {kb} KB')
    with open(os.path.join(out, 'data.json'), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(',', ':'))
    print(f'saved {out}/data.json')

# ---------------------------------------------------------------- front and back pages
def heading(can, text, baseline_mm, size_mm=17, start=0):
    f = font(FREDOKA, mm(size_mm), 'Bold')
    rainbow_text(can, text, f, mm(PAGE_W_MM / 2 + 4), mm(baseline_mm), stroke=mm(1.1), start=start, tilt=3)

def cmd_who(args):
    """Page 3 (recto): every find, large, with its name."""
    book = load_book()
    can = Image.new('RGBA', (W, H), CREAM + (255,))
    heading(can, book.get('who_heading', "Who's hiding?"), 42)
    d = ImageDraw.Draw(can)
    f_sub = font(NUNITO, mm(6.2), 'ExtraBold')
    d.text((mm(PAGE_W_MM / 2 + 4), mm(54)), book.get('who_sub', 'Find all of them on every page!'), font=f_sub, fill=INK, anchor='ms')
    finds = book['finds']
    cols = 3; rows = math.ceil(len(finds) / cols)
    x0, x1 = COIL_CLEAR + 8, PAGE_W_MM - MARGIN - 4
    dia = mm(44); ring = mm(2.2)
    f_name = font(NUNITO, mm(7), 'ExtraBold')
    top, bottom = 66, 283
    pitch_y = (bottom - top) / rows
    for i, fd in enumerate(finds):
        r, c = divmod(i, cols)
        cx = mm(x0 + (x1 - x0) * (c + 0.5) / cols)
        cy = mm(top + pitch_y * r) + dia // 2
        pt = portrait(fd, dia, ring)
        can.alpha_composite(pt, (int(cx - dia / 2), int(cy - dia / 2)))
        label_lines(d, fd['label'], f_name, cx, cy + dia / 2 + mm(2.5), mm((x1 - x0) / cols - 3), mm(8))
    out = can.convert('RGB')
    save_jpg(out, 'pages/p03_who.jpg')
    out.resize((W // 4, H // 4), Image.LANCZOS).save('preview/p03_who.jpg', quality=88)
    print('saved pages/p03_who.jpg')

def cmd_answers(args):
    """Pages 24-25: every spread small, with a ring on each find."""
    book = load_book(); fds = find_defs(book)
    spreads = [s for s in book['spreads'] if os.path.exists(os.path.join('scenes', s['scene']))]
    per_page = 5
    thumb_w = mm(92); thumb_h = int(thumb_w * SCENE_H_MM / SPREAD_W_MM)
    f_t = font(NUNITO, mm(5), 'ExtraBold')
    for pg in range(2):
        can = Image.new('RGBA', (W, H), CREAM + (255,))
        side = 'L' if pg == 0 else 'R'       # page 24 is a verso, 25 a recto
        if pg == 0:
            heading(can, 'Answers', 36, size_mm=15)
        d = ImageDraw.Draw(can)
        xs = [MARGIN + 2, PAGE_W_MM - COIL_CLEAR - 92] if side == 'L' else [COIL_CLEAR + 2, PAGE_W_MM - MARGIN - 92]
        top = 46 if pg == 0 else 14
        pitch = (PAGE_H_MM - 8 - top) / 3
        for k, sd in enumerate(spreads[pg * per_page:(pg + 1) * per_page]):
            r, c = divmod(k, 2)
            x = mm(xs[c]); y = mm(top + r * pitch)
            sp = render_spread(book, sd)
            th = sp.resize((thumb_w, thumb_h), Image.LANCZOS).convert('RGBA')
            td = ImageDraw.Draw(th)
            scale = thumb_w / sp.width
            gx = mm(PAGE_W_MM) * scale
            td.line([(gx, 0), (gx, thumb_h)], fill=(255, 255, 255, 200), width=3)
            for p in sd.get('places', []):
                if not p.get('find'):
                    continue
                cx, by, hpx = place_px(p)
                px, py = cx * scale, (by - hpx / 2) * scale
                rr = max(hpx * 0.9 * scale, mm(3.6))
                col = FAMILY[fds[p['find']]['colour']]
                td.ellipse([px - rr - mm(0.4), py - rr - mm(0.4), px + rr + mm(0.4), py + rr + mm(0.4)], outline=INK, width=mm(0.35))
                td.ellipse([px - rr, py - rr, px + rr, py + rr], outline=col, width=mm(0.9))
            can.alpha_composite(th, (x, y))
            d.rectangle([x - 2, y - 2, x + thumb_w + 1, y + thumb_h + 1], outline=INK, width=mm(0.4))
            d.text((x + thumb_w / 2, y + thumb_h + mm(1.5)), f'{int(sd["n"])}. {sd["title"]}', font=f_t, fill=INK, anchor='ma')
        if pg == 1:
            f_c = font(NUNITO, mm(3.4), 'Bold')
            d.text((mm(PAGE_W_MM / 2 + 4), mm(290)), book.get('footer', ''), font=f_c, fill=(120, 105, 140), anchor='ms')
        out = can.convert('RGB')
        name = f'pages/p{24 + pg}_answers{pg + 1}.jpg'
        save_jpg(out, name)
        out.resize((W // 4, H // 4), Image.LANCZOS).save(f'preview/p{24 + pg}_answers{pg + 1}.jpg', quality=88)
        print('saved', name)

def cmd_pdf(args):
    import img2pdf
    files = sorted(f for f in os.listdir('pages') if f.lower().endswith('.jpg'))
    print('pages:', ', '.join(files))
    nums = sorted(int(f[1:3]) for f in files)
    missing = [i for i in range(1, max(nums) + 1) if i not in nums]
    if missing:
        print('WARNING: missing page numbers', missing)
    layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(PAGE_W_MM), img2pdf.mm_to_pt(PAGE_H_MM)))
    with open('Seek_and_Find_All.pdf', 'wb') as fh:
        fh.write(img2pdf.convert([os.path.join('pages', f) for f in files], layout_fun=layout))
    print('saved Seek_and_Find_All.pdf,', len(files), 'pages')

# ---------------------------------------------------------------- cut-outs
def cmd_cut(args):
    """Cut the figures out of an AI Studio sheet (figures on plain white, nothing touching).
    Sticker-style rings around figures are dropped; small loose bits (hearts, sparkles) are dropped
    unless --keep-satellites. Output: cutouts/<name>_<pose>.png in reading order."""
    im = Image.open(args.sheet).convert('RGB')
    a = np.asarray(im).astype(np.int16)
    minc = a.min(axis=2)
    nonwhite = minc < args.white
    lab, n = ndimage.label(nonwhite, structure=np.ones((3, 3)))
    sizes = ndimage.sum(nonwhite, lab, range(1, n + 1))
    # drop hollow rings (sticker borders): filled area much larger than drawn area
    objs = ndimage.find_objects(lab)
    drop = np.zeros(n + 1, bool)
    for i, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        comp = lab[sl] == i
        if sizes[i - 1] < 50:
            drop[i] = True
            continue
        filled = ndimage.binary_fill_holes(comp).sum()
        if sizes[i - 1] / filled < 0.3 and filled > 0.01 * nonwhite.size:
            drop[i] = True
    nonwhite[drop[lab]] = False
    # background = near-white reachable from the border
    white = ~nonwhite
    wl, wn = ndimage.label(white)
    border = set(np.unique(np.concatenate([wl[0], wl[-1], wl[:, 0], wl[:, -1]])))
    border.discard(0)
    bg = np.isin(wl, list(border))
    # enclosed pure-white regions that are big are gaps between limbs or between two figures, not
    # eye whites or a collar: treat them as background too (a cream top is not pure white, so it stays)
    wsizes = ndimage.sum(white, wl, range(1, wn + 1))
    wmean = ndimage.mean(minc, wl, range(1, wn + 1))
    gaps = [i + 1 for i in range(wn) if (i + 1) not in border and wsizes[i] > 0.0008 * white.size and wmean[i] >= 246]
    if gaps:
        bg |= np.isin(wl, gaps)
    fg = ~bg
    lab, n = ndimage.label(fg, structure=np.ones((3, 3)))
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    objs = ndimage.find_objects(lab)
    order = np.argsort(-sizes)
    want = len(args.poses)
    seeds = [int(i) + 1 for i in order[:want] if sizes[i] > 0.002 * fg.size]
    boxes = {i: objs[i - 1] for i in seeds}
    # real pixel distance from every other piece to the nearest figure (not box distance: a heart
    # beside a shoulder sits inside the box the hair spans)
    seed_mask = np.isin(lab, seeds)
    dist, (iy, ix) = ndimage.distance_transform_edt(~seed_mask, return_indices=True)
    groups = {i: [i] for i in seeds}
    limit = (0.03 if args.keep_satellites else 0.003) * max(im.size)
    for i in range(1, n + 1):
        if i in seeds or sizes[i - 1] == 0:
            continue
        sl = objs[i - 1]
        comp = lab[sl] == i
        dsub = dist[sl][comp]
        k = int(np.argmin(dsub))
        # only pieces practically touching the figure belong to it (a detached hair tip); hearts,
        # sparkles and the like float further off and would give a hidden figure away
        if dsub[k] < limit:
            yy, xx = np.where(comp)
            near = int(lab[iy[sl][yy[k], xx[k]], ix[sl][yy[k], xx[k]]])
            groups[near].append(i)
    # reading order
    rows = args.grid[0]
    def key(s):
        sl = boxes[s]
        cy = (sl[0].start + sl[0].stop) / 2; cx = (sl[1].start + sl[1].stop) / 2
        return (int(cy // (im.height / rows)), cx)
    seeds.sort(key=key)
    os.makedirs('cutouts', exist_ok=True)
    for pose, s in zip(args.poses, seeds):
        m = np.isin(lab, groups[s])
        if pose.endswith('peek'):
            m = trim_wall_line(m)
        ys, xs = np.where(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        pad = 3
        y0, x0 = max(0, y0 - pad), max(0, x0 - pad); y1, x1 = min(im.height, y1 + pad), min(im.width, x1 + pad)
        sub = m[y0:y1, x0:x1]
        rgb = np.asarray(im)[y0:y1, x0:x1]
        alpha = (sub * 255).astype(np.uint8)
        # soften the outer pixel of the edge by how far from white it is
        edge = sub & ~ndimage.binary_erosion(sub, structure=np.ones((3, 3)))
        mc = minc[y0:y1, x0:x1]
        soft = np.clip((250 - mc) / 40.0, 0, 1)
        alpha = np.where(edge, (soft * 255).astype(np.uint8), alpha)
        out = np.dstack([rgb, alpha])
        name = f'{args.name}_{pose}.png'
        Image.fromarray(out, 'RGBA').save(os.path.join('cutouts', name))
        print(f'cutouts/{name}: {x1 - x0} x {y1 - y0} px')
    if len(seeds) < want:
        print(f'WARNING: found {len(seeds)} figures, wanted {want}')

def trim_wall_line(m):
    """Erase the "wall" line AI Studio draws under a peeking figure, keeping the hands that grip over
    it. The line always sticks out past the figure on both sides, so its rows are the rows drawn in
    the outermost columns. In those rows a pixel stays only where something crosses the line
    (fingers above and below it); the leftover line ends are dropped."""
    cols = np.where(m.any(axis=0))[0]
    if len(cols) < 20:
        return m
    w = cols[-1] - cols[0]
    edge_cols = np.r_[cols[0]:cols[0] + max(3, int(0.015 * w)), cols[-1] - max(3, int(0.015 * w)) + 1:cols[-1] + 1]
    rows = np.where(m[:, edge_cols].any(axis=1))[0]
    allrows = np.where(m.any(axis=1))[0]
    if len(rows) == 0 or rows.min() < allrows[-1] - 0.25 * (allrows[-1] - allrows[0]):
        return m                                  # no line at the bottom: leave it alone
    r0, r1 = max(0, rows.min() - 2), min(m.shape[0] - 1, rows.max() + 2)
    above = m[max(0, r0 - 4)]; below = m[min(m.shape[0] - 1, r1 + 4)]
    cross = ndimage.binary_dilation(above & below, iterations=2)
    m = m.copy()
    m[r0:r1 + 1] &= cross[None, :]
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n > 1:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        keep = [i + 1 for i in range(n) if sizes[i] >= 0.01 * sizes.max()]
        m = np.isin(lab, keep)
    return m

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('cut'); c.add_argument('sheet'); c.add_argument('name')
    c.add_argument('--poses', default='stand,sit,walk,peek'); c.add_argument('--grid', default='2x2')
    c.add_argument('--white', type=int, default=232); c.add_argument('--keep-satellites', action='store_true')
    c.set_defaults(fn=cmd_cut)
    for name, fn in (('spread', cmd_spread), ('check', cmd_check), ('grid', cmd_grid)):
        p = sub.add_parser(name); p.add_argument('n', type=int); p.set_defaults(fn=fn)
        if name == 'grid':
            p.add_argument('--finds', action='store_true', help='include the placed finds')
    s = sub.add_parser('spots'); s.add_argument('n', type=int); s.add_argument('--apply', action='store_true')
    s.add_argument('--spacing', type=float, default=55); s.add_argument('--seed', type=int, default=0)
    s.add_argument('--no-balance', dest='balance', action='store_false'); s.set_defaults(fn=cmd_spots)
    wb = sub.add_parser('web'); wb.add_argument('--out', default=os.path.join('website', 'upload'))
    wb.add_argument('--width', type=int, default=3200); wb.add_argument('--quality', type=int, default=74)
    wb.add_argument('--cut-height', dest='cut_height', type=int, default=400)
    wb.set_defaults(fn=cmd_web)
    sl = sub.add_parser('slots'); sl.add_argument('n', type=int); sl.add_argument('--refs')
    sl.add_argument('--keep'); sl.add_argument('--spacing', type=float, default=.45)
    sl.add_argument('--person', type=int, default=18); sl.add_argument('--wide', type=int, default=8)
    sl.add_argument('--objects', type=int, default=10)
    sl.add_argument('--legs', type=float, default=.55); sl.add_argument('--below', type=float, default=.85)
    sl.set_defaults(fn=cmd_slots)
    for name, fn in (('who', cmd_who), ('answers', cmd_answers), ('pdf', cmd_pdf)):
        p = sub.add_parser(name); p.set_defaults(fn=fn)
    args = ap.parse_args()
    if args.cmd == 'cut':
        args.poses = [s.strip() for s in args.poses.split(',') if s.strip()]
        args.grid = [int(v) for v in args.grid.lower().split('x')]
    args.fn(args)

if __name__ == '__main__':
    main()
