"""Seek-and-Find image maker: generates the character sheets and scenes with Google AI Studio's
image model, from the prompts in prompts.json.

    py gen.py check                 photos and key present? (no API call)
    py gen.py prompts sheets        show the sheet prompts (free)
    py gen.py sheets                make every character and object sheet -> sheets/sheet_<name>_vN.jpg
    py gen.py sheets dad mum        just those
    py gen.py scene 1               make scene 1 -> scenes/scene_01_vN.jpg (its prompt must be in prompts.json)
    py gen.py scene 1 --count 2     two versions to choose from

Options:
    --model gemini-3-pro-image      image model (default; gemini-nano-banana-2.1 is cheaper)
    --size 4K                       1K, 2K or 4K (default 4K)
    --count 1                       how many versions to make of each

Setup, same as the Monster Book kit maker: the API key is read from the GEMINI_API_KEY environment
variable, and the google-genai package must be installed (py -m pip install --upgrade google-genai).
Outputs are never overwritten: every run saves a new _vN file.
"""
import argparse, base64, io, json, os, re, sys, time
from datetime import datetime
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / 'prompts.json').read_text(encoding='utf-8'))
SHEETS, SCENES = HERE / 'sheets', HERE / 'scenes'

# ----------------------------------------------------------------- prompts ---

def job(kind, name):
    group = DATA['sheets'] if kind == 'sheet' else DATA['scenes']
    key = name if name in group else str(int(name)).zfill(2) if kind == 'scene' and name.isdigit() else None
    if key is None or key not in group:
        sys.exit(f'No {kind} "{name}" in prompts.json. Known: {", ".join(group)}')
    j = dict(group[key]); j['name'] = key
    j['prompt'] = j['prompt'].replace('{tail}', DATA['tail'])
    return j

def out_path(kind, name):
    folder = SHEETS if kind == 'sheet' else SCENES
    folder.mkdir(exist_ok=True)
    stem = f'sheet_{name}' if kind == 'sheet' else f'scene_{name}'
    vs = [int(p.stem.rsplit('_v', 1)[1]) for p in folder.glob(f'{stem}_v*.*') if p.stem.rsplit('_v', 1)[1].isdigit()]
    return folder, stem, max(vs, default=0) + 1

# --------------------------------------------------------------------- API ---

def _client():
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        sys.exit('GEMINI_API_KEY is not set. Run:  setx GEMINI_API_KEY "your-key"  then open a new window.')
    try:
        from google import genai
    except ImportError:
        sys.exit('The google-genai package is missing. Run:  py -m pip install --upgrade google-genai')
    return genai.Client(api_key=key)

def ref_bytes(path, max_px=2048):
    """A reference image as JPEG bytes, downsized so the request stays small."""
    im = Image.open(HERE / path).convert('RGB')
    s = min(1.0, max_px / max(im.size))
    if s < 1:
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=92)
    return buf.getvalue()

def _generate_once(client, model, prompt, refs, aspect, size):
    """Return image bytes. Tries the Interactions API first, then generateContent."""
    errors = []
    if hasattr(client, 'interactions'):
        try:
            parts = [{'type': 'image', 'data': base64.b64encode(b).decode('ascii'), 'mime_type': 'image/jpeg'}
                     for b in refs] + [{'type': 'text', 'text': prompt}]
            it = client.interactions.create(
                model=model, input=parts,
                response_format={'type': 'image', 'mime_type': 'image/png',
                                 'aspect_ratio': aspect, 'image_size': size})
            img = getattr(it, 'output_image', None)
            if img is not None and getattr(img, 'data', None):
                d = img.data
                return base64.b64decode(d) if isinstance(d, str) else bytes(d)
            errors.append('interactions: no image returned ' + str(getattr(it, 'output_text', '') or '')[:200])
        except Exception as e:
            errors.append(f'interactions: {e}')
    try:
        from google.genai import types
        contents = [types.Part.from_bytes(data=b, mime_type='image/jpeg') for b in refs] + [prompt]
        resp = client.models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=types.ImageConfig(aspect_ratio=aspect, image_size=size)))
        for part in resp.candidates[0].content.parts:
            inline = getattr(part, 'inline_data', None)
            if inline is not None and inline.data:
                d = inline.data
                return base64.b64decode(d) if isinstance(d, str) else bytes(d)
        errors.append('generateContent: no image returned')
    except Exception as e:
        errors.append(f'generateContent: {e}')
    raise RuntimeError(' | '.join(errors))

def generate(client, model, j, size):
    fake = os.environ.get('GEN_FAKE')           # testing only: copy an existing image, no API call
    if fake:
        return Path(fake).read_bytes()
    refs = [ref_bytes(p) for p in j['refs']]
    for attempt in range(3):                    # retry transient errors (rate limits, overload)
        try:
            return _generate_once(client, model, j['prompt'], refs, j.get('aspect', '1:1'), size)
        except RuntimeError as e:
            msg = str(e)
            if attempt < 2 and re.search(r'429|503|500|overload|unavailable|RESOURCE_EXHAUSTED', msg, re.I):
                print(f'    busy, waiting 30 s ({msg[:80]})'); time.sleep(30); continue
            raise

# -------------------------------------------------------------------- main ---

def run(kind, names, a):
    client = None if os.environ.get('GEN_FAKE') else _client()
    log = HERE / 'gen_log.csv'
    made = 0
    for name in names:
        j = job(kind, name)
        missing = [p for p in j['refs'] if not (HERE / p).exists()]
        if missing:
            print(f'\n{kind} {j["name"]}: skipped, missing {", ".join(missing)}'); continue
        print(f'\n{kind} {j["name"]} ({len(j["refs"])} reference images, {j.get("aspect", "1:1")}, {a.size})')
        for _ in range(a.count):
            try:
                data = generate(client, a.model, j, a.size)
            except Exception as e:
                print(f'    failed: {e}'); break
            folder, stem, v = out_path(kind, j['name'])
            ext = '.jpg' if data[:3] == b'\xff\xd8\xff' else '.png'
            path = folder / f'{stem}_v{v}{ext}'
            path.write_bytes(data)
            im = Image.open(path)
            print(f'    saved {folder.name}/{path.name}  {im.width} x {im.height}')
            with log.open('a', newline='', encoding='utf-8') as f:
                f.write(f'{datetime.now().isoformat(timespec="seconds")},{kind},{j["name"]},{path.name},{a.model},{a.size}\n')
            made += 1
    print(f'\n{made} image(s) generated.')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['check', 'prompts', 'sheets', 'scene'])
    ap.add_argument('targets', nargs='*')
    ap.add_argument('--model', default='gemini-3-pro-image')
    ap.add_argument('--size', default='4K', choices=['1K', '2K', '4K'])
    ap.add_argument('--count', type=int, default=1)
    a = ap.parse_args()

    if a.command == 'check':
        needed = sorted({p for j in DATA['sheets'].values() for p in j['refs']})
        for p in needed:
            print(('ok      ' if (HERE / p).exists() else 'MISSING ') + p)
        print('key:', 'set' if os.environ.get('GEMINI_API_KEY') else 'GEMINI_API_KEY not set in this window')
        try:
            import google.genai  # noqa: F401
            print('google-genai: installed')
        except ImportError:
            print('google-genai: MISSING  (py -m pip install --upgrade google-genai)')
        return

    if a.command == 'prompts':
        kind = 'scene' if a.targets and a.targets[0] == 'scenes' else 'sheet'
        names = a.targets[1:] if a.targets and a.targets[0] in ('sheets', 'scenes') else a.targets
        group = DATA['scenes'] if kind == 'scene' else DATA['sheets']
        for name in names or list(group):
            j = job(kind, name)
            print(f'\n===== {kind} {j["name"]} (attach: {", ".join(j["refs"])}) =====\n{j["prompt"]}')
        return

    if a.command == 'sheets':
        run('sheet', a.targets or list(DATA['sheets']), a)
    else:
        if not a.targets:
            sys.exit('Say which scene, e.g.  py gen.py scene 1')
        run('scene', a.targets, a)

if __name__ == '__main__':
    main()
