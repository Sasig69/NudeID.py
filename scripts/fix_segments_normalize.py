import glob, json, os

UPLOAD_FOLDER = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads'))

for p in glob.glob(os.path.join(UPLOAD_FOLDER, '*_report.json')):
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            rep = json.load(fh)
    except Exception as e:
        print('skip', p, e)
        continue
    changed = False
    segs = rep.get('segments') or []
    for s in segs:
        t = s.get('thumbnail','') or ''
        if t and '\\' in t:
            s['thumbnail'] = t.replace('\\','/').lstrip('/')
            changed = True
        # ensure start is representative (best timestamp if present)
        if 'best' in s:
            # if segment erroneously includes internal best object, ignore
            del s['best']
            changed = True
        # if start seems 0 but end > start and thumbnail refers to a later frame, try adjust
        bs = s.get('start')
        if isinstance(bs, (int,float)) and bs == 0:
            # try to set start to mid of segment if thumbnail exists with a numeric in name
            changed = True
            # leave as-is; viewer will use thumbnail timestamp fallback earlier
    if changed:
        try:
            with open(p, 'w', encoding='utf-8') as fh:
                json.dump(rep, fh, indent=2)
            print('fixed', p)
        except Exception as e:
            print('failed write', p, e)
    else:
        print('no-change', p)
