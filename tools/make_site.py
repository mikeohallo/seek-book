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
body = body.replace("const DEFAULT_OWNER = 'the girl';", "const DEFAULT_OWNER = '';")
assert "const DEFAULT_OWNER = '';" in body, 'DEFAULT_OWNER line not found'

desc = 'Find the family hidden in every busy picture from the seek-and-find book.'
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
    im.crop((0, top, 1200, top + 630)).save(os.path.join(UP, 'share.jpg'), quality=86)

zpath = os.path.join('website', 'seek_upload.zip')
n = 0
with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(UP):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, UP)); n += 1
print(f'{UP}/index.html written; {n} files zipped to {zpath} ({os.path.getsize(zpath) // 1024} KB)')
