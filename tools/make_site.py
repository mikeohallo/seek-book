"""make_site.py: turn the site page (site_src.html, the same page as the Claude preview) into the
hosted index.html in website/upload, and zip the folder for Cloudflare Pages.

    python3 make_site.py            -> website/upload/index.html, website/upload/share.jpg, website/seek_upload.zip

The preview page is a fragment (Claude's viewer adds the document head). The hosted page needs its own:
doctype, charset, the phone viewport, a share preview, and the same small reset the viewer adds.
The plain link says "My Seek and Find"; ?for=Name names it on that device (DEFAULT_OWNER empty).
"""
import os, re, zipfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
UP = os.path.join('website', 'upload')
SITE = 'https://seek.mikeohalloran.au/'

src = open('site_src.html', encoding='utf-8').read()
head_end = src.index('</style>') + len('</style>')
head, body = src[:head_end], src[head_end:]
head = re.sub(r'<title>.*?</title>\s*', '', head, flags=re.S)
head = re.sub(r'<meta name="claude:viewport-fit-sides"[^>]*>\s*', '', head)
head = re.sub(r'<meta name="description"[^>]*>\s*', '', head)
assert "const DEFAULT_OWNER = '';" in body, 'the hosted page must not name anyone (DEFAULT_OWNER must be empty)'

# The game's text: one file per language in lang/ (lang/en.json, lang/ko.json), the same keys in each.
# Built into the page, so it stays one file. The build stops if a language is missing a line.
import json, urllib.parse
from check_lang import check_langs
LANGS = {code: json.load(open(os.path.join('lang', code + '.json'), encoding='utf-8')) for code in ('en', 'ko')}
problems = check_langs(LANGS, json.load(open(os.path.join(UP, 'data.json'), encoding='utf-8')))
assert not problems, 'lang files: ' + '; '.join(problems)
for v in LANGS.values(): v.pop('_about', None)
# the Korean font, cut down to just the letters the Korean text uses (Google Fonts' text= option)
def strings(o):
    if isinstance(o, dict): return ''.join(strings(v) for v in o.values())
    return o if isinstance(o, str) else ''
ko_chars = ''.join(sorted({c for c in strings(LANGS['ko']) if ord(c) > 0x7F}))
ko_font = 'https://fonts.googleapis.com/css2?family=Jua&family=Gowun+Dodum&display=swap&text=' + urllib.parse.quote(ko_chars)
for tok, val in (('LANGS', json.dumps(LANGS, ensure_ascii=False, separators=(',', ':'))), ('KO_FONT', json.dumps(ko_font))):
    pat = re.compile(r'/\*' + tok + r'\*/.*?/\*/' + tok + r'\*/', re.S)
    assert len(pat.findall(body)) == 1, tok
    body = pat.sub(lambda m: val, body)

desc = 'Find the family hidden in every busy picture.'
page = f'''<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>My Seek and Find</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#FFF8EC">
<meta name="robots" content="noindex">
<meta property="og:type" content="website">
<meta property="og:title" content="Seek and Find">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{SITE}">
<meta property="og:image" content="{SITE}share.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
{head.strip()}
</head>
<body>
{body.strip()}
</body>
</html>
'''
open(os.path.join(UP, 'index.html'), 'w', encoding='utf-8').write(page)

# share picture: the first page's scene, cropped to 1200 x 630
scenes = sorted(f for f in os.listdir(os.path.join(UP, 'scenes')) if f.endswith('.webp'))
if scenes:
    im = Image.open(os.path.join(UP, 'scenes', scenes[0])).convert('RGB')
    s = 1200 / im.width
    im = im.resize((1200, round(im.height * s)), Image.LANCZOS)
    top = max(0, (im.height - 630) // 2)
    im.crop((0, top, 1200, top + 630)).save(os.path.join(UP, 'share.jpg'), quality=74)  # quality keeps the upload under the 10 MB the browser hand-off takes

zpath = os.path.join('website', 'seek_upload.zip')
n = 0
with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(UP):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, UP)); n += 1
print(f'{UP}/index.html written; {n} files zipped to {zpath} ({os.path.getsize(zpath) // 1024} KB)')
