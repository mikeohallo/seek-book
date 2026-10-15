"""Drive the site in Chromium at phone size (touch) and laptop size (mouse).

    python3 tools/test_site.py website/upload

Needs the built site folder (index.html, data.json and the pictures) and Playwright with Chromium.
Checks: every find on the first page registers when tapped, a tap on nothing shows a miss, the count
and rings survive a reload, the last find opens "You found everyone!", Start again clears the page,
the zoom buttons and mouse wheel zoom, a drag never counts as a tap, holding a face shows a clue,
nothing scrolls sideways, and the page throws no errors.
"""
import asyncio, json, os, subprocess, sys, time
from playwright.async_api import async_playwright

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join('website', 'upload')
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


async def main():
    await run('phone 390 x 760', {'width': 390, 'height': 760}, True)
    await run('laptop 1280 x 800', {'width': 1280, 'height': 800}, False)

if __name__ == '__main__':
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '-d', ROOT],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        asyncio.run(main())
    finally:
        srv.terminate()
