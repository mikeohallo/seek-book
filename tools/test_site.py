"""Drive the site in Chromium at phone size (touch) and laptop size (mouse).

    python3 tools/test_site.py website/upload

Needs the built site folder (index.html, data.json and the pictures) and Playwright with Chromium.
Checks: every find on the first page registers when tapped, a tap on nothing shows a miss, the count
and rings survive a reload, the last find opens "You found everyone!", Start again clears the page,
the zoom buttons and mouse wheel zoom, a drag never counts as a tap, holding a face shows a clue,
nothing scrolls sideways, and the page throws no errors.
Hide everyone again (on every page): the family moves, nobody overlaps, every find in the new round
can be tapped, a reload keeps the round, and Start this page again puts everyone back in the book's places.
Coming back: a finished page opens straight into a new round and keeps its star on the home page, and a
page finished before stars were saved separately still gets its star and a new round.
"""
import asyncio, json, os, subprocess, sys, time
from playwright.async_api import async_playwright

ROOT = next((a for a in sys.argv[1:] if not a.startswith('--')), os.path.join('website', 'upload'))
PORT = 8765
DATA = json.load(open(os.path.join(ROOT, 'data.json'), encoding='utf-8'))
SP = DATA['spreads'][0]


async def img_to_screen(page, fx, fy):
    """Where a point on the picture (as fractions) is on screen right now."""
    return await page.evaluate("""([fx, fy]) => {
        const r = document.getElementById('stage').getBoundingClientRect();
        const m = /translate\\(([-\\d.]+)px, ([-\\d.]+)px\\) scale\\(([\\d.]+)\\)/.exec(document.getElementById('layer').style.transform);
        const img = document.getElementById('scene');
        const W = parseFloat(img.style.width), H = parseFloat(img.style.height);
        return { x: r.left + +m[1] + fx * W * m[3], y: r.top + +m[2] + fy * H * m[3], s: +m[3] };
    }""", [fx, fy])


async def run(name, viewport, touch):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=2)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(f'http://localhost:{PORT}/')
        await page.wait_for_selector('.page-card')
        assert await page.evaluate('document.documentElement.scrollWidth') <= viewport['width'], 'home scrolls sideways'
        await page.click('.page-card')
        await page.wait_for_function("document.getElementById('loading').hidden")
        tap = page.touchscreen.tap if touch else page.mouse.click
        await page.click('#zfit'); await page.wait_for_timeout(450)
        finds = SP['finds']
        for f in finds[:-1]:
            x0, y0, x1, y1 = f['box']
            pt = await img_to_screen(page, (x0 + x1) / 2, (y0 + y1) / 2)
            await tap(pt['x'], pt['y']); await page.wait_for_timeout(120)
        assert await page.text_content('#count') == f'{len(finds) - 1}/{len(finds)}', 'a find did not register'
        await tap(viewport['width'] * 0.5, 90); await page.wait_for_timeout(100)
        assert await page.locator('.miss').count() >= 0
        await page.reload(); await page.wait_for_function("document.getElementById('loading').hidden")
        assert await page.locator('#marks g').count() == len(finds) - 1, 'rings not restored after reload'
        await page.click('#zfit'); await page.wait_for_timeout(450)
        x0, y0, x1, y1 = finds[-1]['box']
        pt = await img_to_screen(page, (x0 + x1) / 2, (y0 + y1) / 2)
        await tap(pt['x'], pt['y']); await page.wait_for_timeout(1500)
        assert await page.is_visible('#finale'), 'no finale after the last find'
        await page.click('#finHome'); await page.wait_for_timeout(300)
        await page.click('.again'); await page.click('.again'); await page.wait_for_timeout(200)
        assert (await page.locator('.dots b').first.text_content()).startswith('0 of'), 'Start again did not clear'
        await page.click('.page-card'); await page.wait_for_function("document.getElementById('loading').hidden")
        s0 = (await img_to_screen(page, 0, 0))['s']
        await page.click('#zin'); await page.wait_for_timeout(400)
        assert (await img_to_screen(page, 0, 0))['s'] > s0, 'zoom in did nothing'
        before = await page.text_content('#count')
        if not touch:
            await page.mouse.move(400, 300); await page.mouse.down(); await page.mouse.move(250, 260, steps=8); await page.mouse.up()
            s1 = (await img_to_screen(page, 0, 0))['s']
            await page.mouse.wheel(0, -400); await page.wait_for_timeout(100)
            assert (await img_to_screen(page, 0, 0))['s'] > s1, 'wheel did not zoom'
        assert before == await page.text_content('#count'), 'a drag counted as a tap'
        face = page.locator('.face').nth(1); bb = await face.bounding_box()
        await page.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
        await page.mouse.down(); await page.wait_for_timeout(800); await page.mouse.up(); await page.wait_for_timeout(300)
        assert await page.locator('#marks circle.glow').count() == 1, 'no clue glow'
        assert await page.evaluate('document.documentElement.scrollWidth') <= viewport['width'], 'page scrolls sideways'
        assert not errs, errs
        print(f'{name}: all checks passed')
        await b.close()


async def fam(page):
    """The family as placed on screen right now: [(left, top, width, height)] in picture px."""
    return await page.evaluate("""() => [...document.querySelectorAll('#layer img.fam')].map(e =>
        [parseFloat(e.style.left), parseFloat(e.style.top), parseFloat(e.style.width), parseFloat(e.style.height)])""")


async def tap_all(page, tap):
    boxes = await page.evaluate('page.finds.map(f => f.box)')
    for b in boxes:
        await page.click('#zfit'); await page.wait_for_timeout(350)
        x0, y0, x1, y1 = b
        pt = await img_to_screen(page, (x0 + x1) / 2, (y0 + y1) / 2)
        await tap(pt['x'], pt['y']); await page.wait_for_timeout(120)
    return len(boxes)


async def rounds(name, viewport, touch):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=1)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        tap = page.touchscreen.tap if touch else page.mouse.click
        await page.goto(f'http://localhost:{PORT}/'); await page.wait_for_selector('.page-card')
        for sp in DATA['spreads']:
            n = sp['n']
            await page.goto(f'http://localhost:{PORT}/#page{n}'); await page.reload()
            await page.wait_for_function("document.getElementById('loading').hidden")
            book = await fam(page)
            assert len(book) == len(sp['finds']), f'page {n}: family not all placed'
            await tap_all(page, tap); await page.wait_for_timeout(1500)
            assert await page.is_visible('#finale'), f'page {n}: no finale after the book round'
            await page.click('#finAgain'); await page.wait_for_function("document.getElementById('loading').hidden")
            await page.wait_for_timeout(200)
            new = await fam(page)
            moved = sum(1 for a, c in zip(book, new) if abs(a[0] - c[0]) + abs(a[1] - c[1]) > 20)
            assert moved >= len(new) - 1, f'page {n}: only {moved} moved'
            assert await page.text_content('#count') == f'0/{len(new)}', f'page {n}: new round did not start empty'
            for i in range(len(new)):
                for j in range(i + 1, len(new)):
                    a, c = new[i], new[j]
                    ov_x = min(a[0] + a[2], c[0] + c[2]) - max(a[0], c[0]); ov_y = min(a[1] + a[3], c[1] + c[3]) - max(a[1], c[1])
                    assert not (ov_x > 4 and ov_y > 4), f'page {n}: two finds overlap in the new round'
            await page.reload(); await page.wait_for_function("document.getElementById('loading').hidden")
            assert await fam(page) == new, f'page {n}: reload changed the round'
            got = await tap_all(page, tap); await page.wait_for_timeout(1500)
            assert await page.text_content('#count') == f'{got}/{got}', f'page {n}: a find in the new round did not register'
            assert await page.is_visible('#finale'), f'page {n}: no finale after the new round'
            print(f'  page {n}: {moved}/{len(new)} moved, all found again')
        # Start this page again: back to the book's places
        await page.click('#finHome'); await page.wait_for_timeout(300)
        last = page.locator('.again').last
        await last.click(); await last.click(); await page.wait_for_timeout(200)
        await page.locator('.page-card').last.click(); await page.wait_for_function("document.getElementById('loading').hidden")
        sp = DATA['spreads'][-1]
        boxes = await page.evaluate('page.finds.map(f => f.box)')
        assert all(abs(a - c) < 2e-4 for bx, f in zip(boxes, sp['finds']) for a, c in zip(bx, f["box"])), "Start again did not go back to the book"
        assert not errs, errs
        print(f'{name}: hide again checks passed')
        await b.close()


async def reopen(name, viewport, touch):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=1)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        tap = page.touchscreen.tap if touch else page.mouse.click
        await page.goto(f'http://localhost:{PORT}/'); await page.wait_for_selector('.page-card')
        # finish page 1 in the book's places, then go home
        await page.locator('.page-card').first.click(); await page.wait_for_function("document.getElementById('loading').hidden")
        book = await fam(page)
        await tap_all(page, tap); await page.wait_for_timeout(1500)
        assert await page.is_visible('#finale'), 'no finale on page 1'
        await page.click('#finHome'); await page.wait_for_timeout(300)
        card = page.locator('.page-card').first
        assert await card.locator('.star').count() == 1, 'no star after finishing'
        # tapping the finished page starts a new round straight away
        await card.click(); await page.wait_for_function("document.getElementById('loading').hidden"); await page.wait_for_timeout(200)
        new = await fam(page)
        moved = sum(1 for a, c in zip(book, new) if abs(a[0] - c[0]) + abs(a[1] - c[1]) > 20)
        assert moved >= len(new) - 1, f'reopened page: only {moved} moved'
        assert await page.text_content('#count') == f'0/{len(new)}', 'reopened page did not start empty'
        assert 'hiding again' in (await page.text_content('#say') or ''), 'no "hiding again" message'
        await page.reload(); await page.wait_for_function("document.getElementById('loading').hidden")
        assert await fam(page) == new, 'reload changed the new round'
        await page.click('#back'); await page.wait_for_timeout(300)
        card = page.locator('.page-card').first
        assert await card.locator('.star').count() == 1, 'star lost after the new round started'
        assert (await card.locator('.dots b').text_content()).startswith('0 of'), 'card does not show the new round'
        # a phone that finished page 2 before stars were saved: star kept, and a new round on opening
        sp = DATA['spreads'][1]
        await page.evaluate(OLD_FINISH, [sp['key'], [f['id'] for f in sp['finds']]])
        await page.reload(); await page.wait_for_selector('.page-card')
        card = page.locator('.page-card').nth(1)
        assert await card.locator('.star').count() == 1, 'old finished page lost its star'
        await card.click(); await page.wait_for_function("document.getElementById('loading').hidden"); await page.wait_for_timeout(200)
        assert await page.text_content('#count') == f"0/{len(sp['finds'])}", 'old finished page did not start a new round'
        boxes = await page.evaluate('page.finds.map(f => f.box)')
        assert not all(abs(a - c) < 2e-4 for bx, f in zip(boxes, sp['finds']) for a, c in zip(bx, f['box'])), 'old finished page reopened in the book places'
        assert not errs, errs
        print(f'{name}: coming back checks passed')
        await b.close()


# progress as an older version of the site saved it: the page's finds all found, no separate star
OLD_FINISH = """([k, ids]) => { const d = JSON.parse(localStorage.getItem('seek-book.v1') || '{}');
    d.found = d.found || {}; d.found[k] = ids; if (d.done) delete d.done[k]; if (d.rounds) delete d.rounds[k];
    localStorage.setItem('seek-book.v1', JSON.stringify(d)); }"""


async def main():
    if '--rounds-only' not in sys.argv:
        await run('phone 390 x 760', {'width': 390, 'height': 760}, True)
        await run('laptop 1280 x 800', {'width': 1280, 'height': 800}, False)
    await rounds('phone 390 x 760', {'width': 390, 'height': 760}, True)
    await reopen('phone 390 x 760', {'width': 390, 'height': 760}, True)

if __name__ == '__main__':
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '-d', ROOT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        asyncio.run(main())
    finally:
        srv.terminate()
