"""Drive the site in Chromium at phone size (touch) and laptop size (mouse).

    python3 tools/test_site.py website/upload

Needs the built site folder (index.html, data.json and the pictures) and Playwright with Chromium.
Checks: every find on the first page registers when tapped, a tap on an empty part of the picture shows a miss, the count
and rings survive a reload, the last find opens "You found everyone!", Start again clears the page,
the zoom buttons and mouse wheel zoom, a drag never counts as a tap, holding a face shows a clue,
nothing scrolls sideways, and the page throws no errors.
Hide everyone again (on every page): the family moves, nobody overlaps, every find in the new round
can be tapped, a reload keeps the round, and Start this page again puts everyone back in the book's places.
Coming back: a finished page opens straight into a new round and keeps its star on the home page, and a
page finished before stars were saved separately still gets its star and a new round.
Private names: the plain page shows only the generic labels; a #me= link sets a child's own names and name on
the device, carries ticks over from a renamed id and leaves the address bar clean; a broken link does nothing.
Harder rounds (when data.json has them): levels 1, 2, 3 in turn; lookalikes, hiding and sitting at level 3,
nothing overlaps, a lookalike tap says "Nearly!" and doesn't count, every find taps, Start again resets the level.
Costumes (when data.json has them): on a page that dresses the family differently, the people are in costume in
the book's places, a new round and a level-3 round, people lookalikes are the costume's own, the strip and the
finale show the costume's faces, and the toys and the other pages are unchanged.
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
        # a tap on an empty part of the picture shows a miss and counts nothing
        await page.click('#zfit'); await page.wait_for_timeout(450)
        spot = await page.evaluate(EMPTY_SPOT)
        assert spot, 'no empty part of the picture to test a miss on'
        pt = await img_to_screen(page, spot[0], spot[1])
        misses = await page.locator('.miss').count()
        await tap(pt['x'], pt['y']); await page.wait_for_timeout(100)
        assert await page.locator('.miss').count() == misses + 1, 'a tap on nothing did not show a miss'
        assert await page.text_content('#count') == f'{len(finds) - 1}/{len(finds)}', 'a miss counted as a find'
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


# a point on the picture (as fractions) well away from every find's tap area
EMPTY_SPOT = """() => { for (let gy = 0.1; gy < 0.92; gy += 0.04) for (let gx = 0.06; gx < 0.94; gx += 0.04)
        if (!page.finds.some(f => { const b = padded(f); return Math.abs(gx * view.W - b.cx) <= b.hw * 1.6 && Math.abs(gy * view.H - b.cy) <= b.hh * 1.6; }))
            return [gx, gy];
    return null; }"""


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


async def names(name, viewport, touch):
    """Private names: the public page shows only data.json's generic labels; a #me= link (made by
    hide.py link) saves a child's own names and name on the device, carries ticks over from a renamed id,
    leaves the address bar clean, and keeps working after a reload. A broken link does nothing.
    Ticks for an id that's no longer on a page don't count."""
    import base64
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=1)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        base = f'http://localhost:{PORT}/'
        await page.goto(base); await page.wait_for_selector('.page-card')
        caps = await page.locator('#who figcaption').all_text_contents()
        assert caps == [f['label'] for f in DATA['finds']], f'home shows {caps}, not the labels in data.json'
        assert (await page.title()) == 'My Seek and Find', 'the plain page names someone'
        first, second = DATA['finds'][0]['id'], DATA['finds'][1]['id']
        sp1, sp2 = DATA['spreads'][0], DATA['spreads'][1]
        # ticks saved under an old id on page 1, and under an id that no longer exists on page 2
        await page.evaluate("""([k1, k2, other]) => localStorage.setItem('seek-book.v1', JSON.stringify(
            { found: { [k1]: ['old-id', other], [k2]: ['gone'] }, rounds: {}, done: {} }))""", [sp1['key'], sp2['key'], second])
        await page.reload(); await page.wait_for_selector('.page-card')
        dots = await page.locator('.page-card .dots b').all_text_contents()
        assert dots[1].startswith('0 of'), f'an id no longer on the page counted: {dots[1]}'
        me = {'for': 'Sam', 'names': {first: 'Testname', second: 'Other Name'}, 'was': {'old-id': first}}
        b64 = base64.urlsafe_b64encode(json.dumps(me).encode()).decode().rstrip('=')
        # opened in the tab that already shows the page (only the part after # changes, so no reload by itself)
        await page.goto(base + '#me=' + b64); await page.wait_for_function("location.hash === ''")
        await page.wait_for_selector('.page-card')
        for attempt in ('after the link', 'after a reload'):
            caps = await page.locator('#who figcaption').all_text_contents()
            assert caps[0] == 'Testname' and caps[1] == 'Other Name', f'own names not shown {attempt}: {caps}'
            assert caps[2:] == [f['label'] for f in DATA['finds'][2:]], f'other labels changed {attempt}'
            assert (await page.title()) == "Sam's Seek and Find", f'name not taken from the link {attempt}'
            await page.goto(base); await page.wait_for_selector('.page-card')
        found = await page.evaluate("([k]) => JSON.parse(localStorage.getItem('seek-book.v1')).found[k]", [sp1['key']])
        assert sorted(found) == sorted([first, second]), f'ticks not carried over from the old id: {found}'
        await page.locator('.page-card').first.click(); await page.wait_for_function("document.getElementById('loading').hidden")
        assert await page.text_content('#count') == f"2/{len(sp1['finds'])}", 'carried-over ticks not counted'
        assert (await page.locator(f'.face[data-id="{first}"] span').text_content()) == 'Testname', 'own name not on the face strip'
        # a broken link: no errors, nothing changed, address bar cleaned
        await page.goto(base + '#me=bm90IGpzb24'); await page.wait_for_function("location.hash === ''")
        await page.wait_for_selector('.page-card')
        assert (await page.locator('#who figcaption').first.text_content()) == 'Testname', 'a broken link changed the names'
        assert not errs, errs
        print(f'{name}: private names checks passed')
        await b.close()


# progress as an older version of the site saved it: the page's finds all found, no separate star
OLD_FINISH = """([k, ids]) => { const d = JSON.parse(localStorage.getItem('seek-book.v1') || '{}');
    d.found = d.found || {}; d.found[k] = ids; if (d.done) delete d.done[k]; if (d.rounds) delete d.rounds[k];
    localStorage.setItem('seek-book.v1', JSON.stringify(d)); }"""


async def hard(name, viewport, touch):
    """Harder rounds: each new round on a page is harder (levels 1, 2, 3); at level 3 lookalikes are in the
    picture, some of the family hide or sit, nothing overlaps, a lookalike tap says "Nearly!" and doesn't count,
    every find can still be tapped, a reload keeps the round, and Start this page again goes back to level 1."""
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=1)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        tap = page.touchscreen.tap if touch else page.mouse.click
        await page.goto(f'http://localhost:{PORT}/'); await page.wait_for_selector('.page-card')
        lv = await page.evaluate("""() => { const n = DATA.spreads[0].n, out = [];
            for (let i = 0; i < 4; i++) { newRound(n); out.push(levelOf(n)); } return out; }""")
        assert lv == [1, 2, 3, 3], f'levels went {lv}'
        for sp in DATA['spreads']:
            n = sp['n']
            await page.evaluate(f"() => {{ store.plays[K({n})] = 2; newRound({n}); persist(); }}")
            await page.goto(f'http://localhost:{PORT}/#page{n}'); await page.reload()
            await page.wait_for_function("document.getElementById('loading').hidden")
            info = await page.evaluate("""() => ({ lv: levelOf(page.n), decoys: page.decoys.length,
                hidden: page.finds.filter(f => f.prop).length, sit: page.finds.filter(f => /_sit$/.test(f.cut)).length,
                units: [...page.finds, ...page.decoys].map(u => u.ubox || u.ibox),
                boxes: page.finds.map(f => f.box), imgs: document.querySelectorAll('#layer img.fam').length })""")
            assert info['lv'] == 3, f'page {n}: level {info["lv"]}'
            assert info['decoys'] >= 4, f'page {n}: only {info["decoys"]} lookalikes'
            assert info['hidden'] >= 2 or n == 0, f'page {n}: only {info["hidden"]} hiding'
            U = info['units']
            for i in range(len(U)):
                for j in range(i + 1, len(U)):
                    a, c = U[i], U[j]
                    assert not (a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3]), f'page {n}: two things overlap'
            assert all(0 <= v <= 1 for bx in info['boxes'] for v in bx), f'page {n}: a find is off the picture'
            # a lookalike tap: "Nearly!", nothing counted
            await page.click('#zfit'); await page.wait_for_timeout(350)
            pt = await page.evaluate("""() => { for (const d of page.decoys) {
                    const cx = (d.box[0] + d.box[2]) / 2, cy = (d.box[1] + d.box[3]) / 2;
                    if (!page.finds.some(f => { const b = padded(f); return Math.abs(cx * view.W - b.cx) <= b.hw && Math.abs(cy * view.H - b.cy) <= b.hh; })) return [cx, cy]; }
                return null; }""")
            if pt:
                s0 = await img_to_screen(page, pt[0], pt[1])
                await tap(s0['x'], s0['y']); await page.wait_for_timeout(150)
                assert 'Nearly' in (await page.text_content('#say') or ''), f'page {n}: a lookalike tap did not say Nearly'
                assert await page.text_content('#count') == f"0/{len(sp['finds'])}", f'page {n}: a lookalike counted'
            got = await tap_all(page, tap); await page.wait_for_timeout(1500)
            assert await page.text_content('#count') == f'{got}/{got}', f'page {n}: a find in the hard round did not register'
            print(f"  page {n}: level 3, {info['decoys']} lookalikes, {info['hidden']} hiding, {info['sit']} sitting, {info['imgs']} pictures, all found")
        await page.click('#finHome'); await page.wait_for_timeout(300)
        last = page.locator('.again').last
        await last.click(); await last.click(); await page.wait_for_timeout(200)
        n = DATA['spreads'][-1]['n']
        assert await page.evaluate(f'levelOf({n})') == 1 and await page.evaluate(f'store.plays[K({n})] === undefined'), 'Start again did not reset the level'
        assert not errs, errs
        print(f'{name}: harder rounds checks passed')
        await b.close()


async def costumes(name, viewport, touch):
    """Costumes: on a page dressed differently ("co"), every person is that costume's cut-out in the book's
    places, in a new round and in a level-3 round (sitting and peeking too), people lookalikes are the
    costume's own, and the strip and the finale show the costume's faces; the toys and every other page
    stay as they are."""
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=viewport, has_touch=touch, is_mobile=touch, device_scale_factor=1)
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        tap = page.touchscreen.tap if touch else page.mouse.click
        await page.goto(f'http://localhost:{PORT}/'); await page.wait_for_selector('.page-card')
        people = ['girl', 'dad', 'mum', 'grandma', 'uncle', 'grandparents']
        plain = next(sp for sp in DATA['spreads'] if not sp.get('co'))
        await page.goto(f"http://localhost:{PORT}/#page{plain['n']}"); await page.reload()
        await page.wait_for_function("document.getElementById('loading').hidden")
        srcs = await page.evaluate("() => [...document.querySelectorAll('#layer img.fam, #strip img')].map(e => e.getAttribute('src'))")
        for co in DATA.get('costumes', {}):
            assert not any(f'_{co}' in s for s in srcs), f"page {plain['n']}: a {co} picture on an everyday page"
        for sp in [s for s in DATA['spreads'] if s.get('co')]:
            n, co = sp['n'], sp['co']
            C = DATA['costumes'][co]
            own_decoys = {d['cut'] for d in C['hard']['decoys'] if d['like'] in people} if 'hard' in C else set()
            for rnd in ('book', 'new', 'level 3'):
                if rnd == 'new':
                    await page.evaluate(f"() => {{ delete store.plays[K({n})]; newRound({n}); persist(); }}")
                if rnd == 'level 3':
                    await page.evaluate(f"() => {{ store.plays[K({n})] = 2; newRound({n}); persist(); }}")
                await page.goto(f'http://localhost:{PORT}/#page{n}'); await page.reload()
                await page.wait_for_function("document.getElementById('loading').hidden")
                info = await page.evaluate("""() => ({ finds: page.finds.map(f => [f.id, f.cut]), decoys: page.decoys.map(d => [d.like, d.cut]),
                    faces: [...document.querySelectorAll('#strip .face')].map(e => [e.dataset.id, e.querySelector('img').getAttribute('src')]),
                    imgs: [...document.querySelectorAll('#layer img.fam:not(.decoy):not(.prop)')].map(e => e.getAttribute('src')) })""")
                for fid, cut in info['finds']:
                    if fid in people:
                        assert f'_{co}_' in cut, f'page {n} ({rnd}): {fid} is {cut}, not in {co}'
                    else:
                        assert f'_{co}' not in cut, f'page {n} ({rnd}): the toy {fid} changed to {cut}'
                assert sum(f'_{co}_' in s for s in info['imgs']) == sum(f in people for f, _ in info['finds']), f'page {n} ({rnd}): pictures not in {co}'
                for like, cut in info['decoys']:
                    assert (cut in own_decoys) == (like in people), f'page {n} ({rnd}): lookalike {cut} for {like}'
                for fid, src in info['faces']:
                    want = C['portraits'].get(fid) or next(f['portrait'] for f in DATA['finds'] if f['id'] == fid)
                    assert src == want, f'page {n} ({rnd}): face {fid} is {src}'
                if rnd == 'level 3':
                    assert info['decoys'], f'page {n}: no lookalikes at level 3'
                    print(f"  page {n} ({co}): level 3 with {len(info['decoys'])} lookalikes, poses {sorted({c.rsplit('_', 1)[1] for f, c in info['finds'] if f in people})}")
            got = await tap_all(page, tap); await page.wait_for_timeout(1500)
            assert await page.is_visible('#finale'), f'page {n}: no finale'
            fin = await page.evaluate("() => [...document.querySelectorAll('#finFaces img')].map(e => e.getAttribute('src'))")
            assert all(s in C['portraits'].values() for s in fin[:len(people)]), f'page {n}: everyday faces in the finale'
        assert not errs, errs
        print(f'{name}: costume checks passed')
        await b.close()


async def main():
    if '--rounds-only' not in sys.argv:
        await run('phone 390 x 760', {'width': 390, 'height': 760}, True)
        await run('laptop 1280 x 800', {'width': 1280, 'height': 800}, False)
    await rounds('phone 390 x 760', {'width': 390, 'height': 760}, True)
    await reopen('phone 390 x 760', {'width': 390, 'height': 760}, True)
    await names('phone 390 x 760', {'width': 390, 'height': 760}, True)
    if json.load(open(os.path.join(ROOT, 'data.json'))).get('hard'):
        await hard('phone 390 x 760', {'width': 390, 'height': 760}, True)
    if json.load(open(os.path.join(ROOT, 'data.json'))).get('costumes'):
        await costumes('phone 390 x 760', {'width': 390, 'height': 760}, True)

if __name__ == '__main__':
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '-d', ROOT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        asyncio.run(main())
    finally:
        srv.terminate()
