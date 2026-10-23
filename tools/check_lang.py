"""check_lang.py: every language file has every line the game shows, with the same slots.

    python3 check_lang.py website/upload/data.json      (or imported by make_site.py and test_site.py)

lang/en.json and lang/ko.json hold all the game's text: ui (buttons, messages, labels), finds (what each
find is called) and pages (each page's title). Every key in one must be in the other, every page in
data.json needs a title in each, and every find a name. A line's slots ({name}, {title}, ...) must match,
whatever the language does around them (Korean adds a particle: {name|을/를})."""
import json, os, re, sys

SLOT = re.compile(r'\{(\w+)(?:\|[^/}]+/[^}]+)?\}')

def check_langs(langs, data):
    problems = []
    codes = list(langs)
    base = langs['en']
    for code in codes:
        L = langs[code]
        for sec in ('ui', 'finds', 'pages'):
            if sec not in L:
                problems.append(f'{code}: no "{sec}" section'); continue
            for other in codes:
                for k in langs[other].get(sec, {}):
                    if k not in L[sec]:
                        problems.append(f'{code}: {sec}.{k} is missing (it is in {other})')
        for k, v in L.get('ui', {}).items():
            if not isinstance(v, str) or not v.strip():
                problems.append(f'{code}: ui.{k} is empty')
            elif k in base['ui'] and sorted(SLOT.findall(v)) != sorted(SLOT.findall(base['ui'][k])):
                problems.append(f'{code}: ui.{k} has slots {sorted(SLOT.findall(v))}, English has {sorted(SLOT.findall(base["ui"][k]))}')
        for sp in data['spreads']:
            if not str(L.get('pages', {}).get(str(sp['n']), '')).strip():
                problems.append(f'{code}: page {sp["n"]} has no title')
        for f in data['finds']:
            tr = L.get('finds', {}).get(f['id'], {})
            if not str(tr.get('label', '')).strip() or not str(tr.get('say', '')).strip():
                problems.append(f'{code}: find "{f["id"]}" has no label or say')
    for sp in data['spreads']:      # English titles match the book's
        if base.get('pages', {}).get(str(sp['n'])) not in (None, sp['title']):
            problems.append(f'en: page {sp["n"]} is "{base["pages"][str(sp["n"])]}" but the book says "{sp["title"]}"')
    return problems

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    data = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'website', 'upload', 'data.json'), encoding='utf-8'))
    langs = {c: json.load(open(os.path.join(here, 'lang', c + '.json'), encoding='utf-8')) for c in ('en', 'ko')}
    p = check_langs(langs, data)
    print('\n'.join(p) if p else f'lang files OK: {len(langs["en"]["ui"])} lines, {len(data["finds"])} finds, {len(data["spreads"])} pages in each')
    sys.exit(1 if p else 0)
