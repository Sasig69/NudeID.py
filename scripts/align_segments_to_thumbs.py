import glob, json, os

UPLOAD_FOLDER = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads'))

for p in glob.glob(os.path.join(UPLOAD_FOLDER, '*_report.json')):
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            rep = json.load(fh)
    except Exception as e:
        print('skip', p, e)
        continue
    dets = rep.get('detections', [])
    segs = rep.get('segments', [])
    changed = False
    # build map from thumbnail -> earliest detection timestamp (or best detection timestamp)
    thumb_map = {}
    for d in dets:
        t = (d.get('thumbnail','') or '').replace('\\','/').lstrip('/')
        if not t:
            continue
        # prefer earliest or highest score? choose the timestamp of this detection
        thumb_map.setdefault(t, []).append(d)
    for s in segs:
        th = (s.get('thumbnail','') or '').replace('\\','/').lstrip('/')
        if th and th in thumb_map:
            # pick the detection with highest score for that thumbnail
            items = thumb_map[th]
            best = max(items, key=lambda x: x.get('score',0.0))
            new_start = float(best.get('timestamp', s.get('start', 0.0)))
            if abs(new_start - s.get('start', 0.0)) > 0.0001:
                s['start'] = new_start
                changed = True
    if changed:
        try:
            with open(p, 'w', encoding='utf-8') as fh:
                json.dump(rep, fh, indent=2)
            print('aligned', p)
        except Exception as e:
            print('failed write', p, e)
    else:
        print('no-change', p)
