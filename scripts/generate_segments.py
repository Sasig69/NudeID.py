import glob, json, os
from collections import defaultdict, Counter

UPLOAD_FOLDER = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads'))

MERGE_GAP = 10.0

for p in glob.glob(os.path.join(UPLOAD_FOLDER, '*_report.json')):
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            rep = json.load(fh)
    except Exception as e:
        print('skip read', p, e)
        continue
    dets = rep.get('detections', [])
    if not dets:
        print('no detections for', p)
        continue
    if rep.get('segments'):
        print('segments already present for', p)
        continue
    grouped = defaultdict(list)
    for r in dets:
        grouped[r.get('class','unknown')].append(r)
    segments = []
    for cls, items in grouped.items():
        items.sort(key=lambda x: x.get('timestamp',0.0))
        cur = None
        for it in items:
            if cur is None:
                cur = {
                    'class': cls,
                    'start': it.get('timestamp',0.0),
                    'end': it.get('timestamp',0.0),
                    'scores': [it.get('score',0.0)],
                    'body_types': [it.get('body_type','unknown')],
                    'count': 1,
                    'best': it,
                }
            else:
                if it.get('timestamp',0.0) <= cur['end'] + MERGE_GAP:
                    cur['end'] = max(cur['end'], it.get('timestamp',0.0))
                    cur['scores'].append(it.get('score',0.0))
                    cur['body_types'].append(it.get('body_type','unknown'))
                    cur['count'] += 1
                    if it.get('score',0.0) > cur['best'].get('score',0.0):
                        cur['best'] = it
                else:
                    bt = Counter(cur['body_types']).most_common(1)[0][0] if cur['body_types'] else 'unknown'
                    thumb = cur['best'].get('thumbnail','') or ''
                    if thumb:
                        thumb = thumb.replace('\\','/').lstrip('/')
                    display_start = float(cur['best'].get('timestamp', cur['start']))
                    seg = {
                        'class': cur['class'],
                        'start': display_start,
                        'end': float(cur['end']),
                        'score': float(max(cur['scores'])),
                        'thumbnail': thumb,
                        'body_type': bt,
                        'count': cur['count'],
                    }
                    segments.append(seg)
                    cur = {
                        'class': cls,
                        'start': it.get('timestamp',0.0),
                        'end': it.get('timestamp',0.0),
                        'scores': [it.get('score',0.0)],
                        'body_types': [it.get('body_type','unknown')],
                        'count': 1,
                        'best': it,
                    }
        if cur is not None:
            bt = Counter(cur['body_types']).most_common(1)[0][0] if cur['body_types'] else 'unknown'
            thumb = cur['best'].get('thumbnail','') or ''
            if thumb:
                thumb = thumb.replace('\\','/').lstrip('/')
            display_start = float(cur['best'].get('timestamp', cur['start']))
            seg = {
                'class': cur['class'],
                'start': display_start,
                'end': float(cur['end']),
                'score': float(max(cur['scores'])),
                'thumbnail': thumb,
                'body_type': bt,
                'count': cur['count'],
            }
            segments.append(seg)
    rep['segments'] = segments
    try:
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(rep, fh, indent=2)
        print('wrote segments for', p)
    except Exception as e:
        print('failed write', p, e)
