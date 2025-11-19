import os
import math
import uuid
import threading
import time
import json
from pathlib import Path
import shutil

from flask import Flask, request, render_template_string, jsonify, send_from_directory
import cv2

# Optional detectors (may not be installed)
try:
    from nudenet import NudeDetector
    detector = NudeDetector()
except Exception:
    detector = None

try:
    from ultralytics import YOLO
    person_detector = YOLO('yolov8n.pt')
except Exception:
    person_detector = None

# Fallback HOG person detector
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# Configuration
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'thumbs'), exist_ok=True)

SAMPLE_FPS = 2
SCORE_THRESHOLD = 0.5
DETECT_MAX_WIDTH = 640

# Job tracking
JOBS = {}
JOBS_LOCK = threading.Lock()

app = Flask(__name__)


INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Moderator</title>
  <link rel="stylesheet" href="/static/styles.css">
  </head>
<body>
  <div class="container">
    <div id="uploader" class="uploader">
      <input id="fileInput" type="file" name="video" accept="video/*">
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap">
        <div style="text-align:left">
          <p style="margin:0;font-size:16px;color:#cfeeff;font-weight:700">Drop an MP4 here</p>
          <div class="hint">Or click to select a file — processed locally on this machine</div>
        </div>
        <div>
          <button id="uploadBtn" class="btn">Select a file</button>
        </div>
      </div>
      <div class="progress" aria-hidden="true"><i></i></div>
    </div>

    <h3 style="margin-top:22px;color:#bfe8ff">Scanned Videos</h3>
    <div id="grid" class="grid">
      {% if cards|length == 0 %}
        <div class="empty">No scanned videos yet — upload one above.</div>
      {% else %}
        {% for c in cards %}
        <div class="card" data-video-id="{{ c.video_id }}" data-ts="{{ c.first_ts }}">
            <div class="actions">
              <button class="delete-btn" data-video-id="{{ c.video_id }}">Delete</button>
            </div>
            <div class="thumb">
              {% if c.thumb %}
                <img data-src="{{ url_for('uploaded', filename=c.thumb) }}" src="{{ url_for('uploaded', filename=c.thumb) }}" alt="thumbnail">
                                <div class="overlay">{{ format_time(c.first_ts) }}</div>
              {% else %}
                <div class="overlay">SAFE</div>
              {% endif %}
            </div>
          <div class="meta">
            <div class="title">{{ c.video_name }}</div>
                        <div class="subtitle">{{ c.video_id[:8] }} • scanned {{ format_time(c.scan_time) }}</div>
          </div>
          <div class="tags">
            {% for tag in c.tags[:6] %}
              <div class="tag">{{ tag }}</div>
            {% endfor %}
          </div>
        </div>
        {% endfor %}
      {% endif %}
    </div>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>"""


RESULT_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Viewer</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="container">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <a href="/" class="btn">← Back</a>
      <div style="color:var(--muted);font-size:13px">Video: <strong>{{ video_name }}</strong> — Duration: {{ "%.1f"|format(duration) }}s</div>
    </div>
    <div class="viewer">
      <div class="video-col">
        <video id="player" class="video-player" controls src="{{ url_for('uploaded', filename=video_file) }}"></video>
      </div>
      <div class="side-col">
        <h4 style="margin:6px 0;color:#bfe8ff">Detections</h4>
        <div style="margin-top:8px">
          {% if segments and segments|length > 0 %}
            <ul class="segments">
            {% for s in segments %}
              <li data-ts="{{ "%.2f"|format(s.start) }}" onclick="seekVideo({{ "%.2f"|format(s.start) }})">
                {% if s.thumbnail %}
                  <img src="{{ url_for('uploaded', filename=s.thumbnail) }}" alt="thumb" class="seg-thumb">
                {% else %}
                  <div class="seg-thumb placeholder">no thumb</div>
                {% endif %}
                <div class="seg-meta">
                  <div><a href="#" class="seek-to" data-ts="{{ "%.2f"|format(s.start) }}">{{ "%.2f"|format(s.start) }}s</a> – {{ "%.2f"|format(s.end) }}s</div>
                  <div class="muted">{{ s.class }} — {{ s.body_type }} — <strong>({{ s.count }})</strong></div>
                </div>
              </li>
            {% endfor %}
            </ul>
          {% elif results|length == 0 %}
            <div class="empty">No detections found.</div>
          {% else %}
            <ul class="segments">
            {% for r in results %}
              <li data-ts="{{ "%.2f"|format(r.timestamp) }}" onclick="seekVideo({{ "%.2f"|format(r.timestamp) }})">
                <div class="seg-thumb placeholder">#{{ loop.index }}</div>
                <div class="seg-meta"><a href="#" class="seek-to" data-ts="{{ "%.2f"|format(r.timestamp) }}">{{ "%.2f"|format(r.timestamp) }}s</a> — <b>{{ r.class }}</b><div class="muted">score {{ "%.2f"|format(r.score) }} — {{ r.body_type }}</div></div>
              </li>
            {% endfor %}
            </ul>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>"""


WAIT_HTML = """<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Processing...</title>
    <link rel="stylesheet" href="/static/styles.css">
    </head>
<body>
    <div class="container">
        <h3>Processing video — please wait</h3>
        <div id="status">
            <div>Stage: <span id="stage">queued</span></div>
            <div>Progress: <span id="percent">0</span>%</div>
            <div>ETA: <span id="eta">—</span></div>
            <div id="error" style="color:#f88;margin-top:8px"></div>
        </div>
        <div style="margin-top:14px"><a href="/">← Back</a></div>
    </div>
    <script>
        const jobId = '{{ job_id }}';
        async function poll() {
            try {
                const res = await fetch('/status/' + jobId);
                const j = await res.json();
                if (!j.ok) return;
                const s = j.status || {};
                document.getElementById('stage').textContent = s.stage || s.state || 'processing';
                document.getElementById('percent').textContent = (s.percent||0).toFixed ? (s.percent||0).toFixed(1) : (s.percent||0);
                document.getElementById('eta').textContent = s.eta_readable || (s.eta? Math.floor(s.eta)+'s' : '—');
                if (s.state === 'done') {
                    // reload the viewer which should now find the report
                    location.reload();
                    return;
                }
                if (s.state === 'error') {
                    document.getElementById('error').textContent = 'Error: ' + (s.error || 'unknown');
                    return;
                }
            } catch (e) {
                console.error(e);
            }
            setTimeout(poll, 1500);
        }
        poll();
    </script>
</body>
</html>"""


def safe_resize(frame, max_w=DETECT_MAX_WIDTH):
    """Resize frame preserving aspect ratio, guard against zero/invalid dims."""
    try:
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return frame
        if w <= max_w:
            return frame
        new_w = int(max_w)
        new_h = int((new_w * h) / w)
        if new_w <= 0 or new_h <= 0:
            return frame
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception:
        return frame


def format_time(secs):
    """Format seconds as Xm Ys for >=60s, else X.Ys."""
    try:
        s = float(secs)
    except Exception:
        return '0s'
    if s < 0:
        s = 0.0
    if s >= 60.0:
        m = int(s // 60)
        rem = s - (m * 60)
        return f"{m}m {rem:.1f}s"
    return f"{s:.1f}s"


def process_video_job(video_id, original_filename, video_path, job_id):
    start_time = time.time()
    job = {'state': 'processing', 'stage': 'start', 'percent': 0.0, 'processed': 0, 'total': 0, 'start_time': start_time}
    with JOBS_LOCK:
        JOBS[job_id] = job

    try:
        job['stage'] = 'opening'
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            job.update({'state': 'error', 'error': 'failed to open video'})
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = (frame_count / fps) if fps > 0 else 0.0
        job.update({'fps': fps, 'total_frames': frame_count, 'duration': duration})

        step = max(1, int(round(fps / float(max(1, SAMPLE_FPS))))) if fps > 0 else 1
        estimated_samples = max(1, int(math.ceil(duration * SAMPLE_FPS))) if duration > 0 else 1
        job['stage'] = 'sampling'
        job['total'] = estimated_samples

        results = []
        thumb_dir = os.path.join(UPLOAD_FOLDER, 'thumbs')
        Path(thumb_dir).mkdir(parents=True, exist_ok=True)

        frame_idx = 0
        samples_done = 0
        while True:
            grabbed = cap.grab()
            if not grabbed:
                break
            if frame_idx % step == 0:
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    frame_idx += 1
                    continue

                ts = float(frame_idx) / fps if fps > 0 else 0.0

                small = safe_resize(frame)
                dets = []
                try:
                    if detector is not None:
                        dets = detector.detect(small) or []
                except Exception:
                    dets = []

                filtered = [d for d in dets if float(d.get('score', 0.0)) >= SCORE_THRESHOLD]

                samples_done += 1
                job['processed'] = samples_done
                try:
                    elapsed = time.time() - start_time
                    pct = float(samples_done) / float(max(1, job.get('total', 1)))
                    eta = (elapsed / max(1e-6, pct) - elapsed) if pct > 0 else None
                    job.update({'percent': round(pct * 100, 1), 'elapsed': elapsed, 'eta': eta})
                except Exception:
                    pass

                if not filtered:
                    frame_idx += 1
                    continue

                thumb_name = f"{video_id}_f{frame_idx}.jpg"
                try:
                    cv2.imwrite(os.path.join(thumb_dir, thumb_name), frame)
                except Exception:
                    pass

                # body type inference
                body_type = 'unknown'
                try:
                    detect_frame = small
                    if person_detector is not None:
                        yres = person_detector(detect_frame)[0]
                        pboxes = []
                        for box, cls in zip(yres.boxes.xyxy, yres.boxes.cls):
                            if int(cls.item()) == 0:
                                x1, y1, x2, y2 = map(int, box.tolist())
                                pboxes.append((x1, y1, x2 - x1, y2 - y1))
                        if len(pboxes) == 0:
                            body_type = 'unknown'
                        elif len(pboxes) > 1:
                            body_type = 'multiple'
                        else:
                            x, y, w_box, h_box = pboxes[0]
                            h_ratio = float(h_box) / float(detect_frame.shape[0])
                            if h_ratio >= 0.6:
                                body_type = 'full_body'
                            elif h_ratio >= 0.35:
                                body_type = 'upper_body'
                            else:
                                body_type = 'partial_or_face'
                    else:
                        gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)
                        rects, _ = hog.detectMultiScale(gray, winStride=(8,8), padding=(8,8), scale=1.05)
                        if len(rects) == 0:
                            body_type = 'unknown'
                        elif len(rects) > 1:
                            body_type = 'multiple'
                        else:
                            x, y, w_box, h_box = rects[0]
                            h_ratio = float(h_box) / float(detect_frame.shape[0])
                            if h_ratio >= 0.6:
                                body_type = 'full_body'
                            elif h_ratio >= 0.35:
                                body_type = 'upper_body'
                            else:
                                body_type = 'partial_or_face'
                except Exception:
                    body_type = 'unknown'

                for d in filtered:
                    rec = {
                        'timestamp': float(ts),
                        'frame_index': frame_idx,
                        'class': d.get('class') or d.get('label') or 'unknown',
                        'score': float(d.get('score', 0.0)),
                        'box': d.get('box', []),
                        'body_type': body_type,
                        'thumbnail': f'thumbs/{thumb_name}',
                    }
                    results.append(rec)

            frame_idx += 1

        cap.release()

        scan_time = time.time() - start_time

        # pick best thumbnail
        best_thumb = ''
        if results:
            best = max(results, key=lambda r: r.get('score', 0.0))
            src = os.path.normpath(os.path.join(UPLOAD_FOLDER, *best.get('thumbnail','').split('/')))
            if os.path.exists(src):
                best_thumb = f"{video_id}_best.jpg"
                try:
                    shutil.copy2(src, os.path.join(UPLOAD_FOLDER, best_thumb))
                except Exception:
                    best_thumb = best.get('thumbnail','')

        # SFW fallback: first frame
        if not results:
            try:
                cap2 = cv2.VideoCapture(video_path)
                if cap2.isOpened():
                    cap2.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, f0 = cap2.read()
                    if ok and f0 is not None:
                        tn = f"{video_id}_f0.jpg"
                        try:
                            cv2.imwrite(os.path.join(UPLOAD_FOLDER, 'thumbs', tn), f0)
                            best_thumb = f"{video_id}_best.jpg"
                            shutil.copy2(os.path.join(UPLOAD_FOLDER, 'thumbs', tn), os.path.join(UPLOAD_FOLDER, best_thumb))
                        except Exception:
                            best_thumb = os.path.join('thumbs', tn)
                    cap2.release()
            except Exception:
                pass

        # merge segments
        MERGE_GAP = 10.0
        segments = []
        try:
            from collections import defaultdict, Counter
            grouped = defaultdict(list)
            for r in results:
                grouped[r.get('class','unknown')].append(r)
            for cls, items in grouped.items():
                items.sort(key=lambda x: x.get('timestamp',0.0))
                cur = None
                for it in items:
                    if cur is None:
                        cur = {'class': cls, 'start': it.get('timestamp',0.0), 'end': it.get('timestamp',0.0), 'scores':[it.get('score',0.0)], 'thumbnails':[it.get('thumbnail','')], 'body_types':[it.get('body_type','unknown')], 'count':1, 'best': it}
                    else:
                        if it.get('timestamp',0.0) <= cur['end'] + MERGE_GAP:
                            cur['end'] = max(cur['end'], it.get('timestamp',0.0))
                            cur['scores'].append(it.get('score',0.0))
                            cur['thumbnails'].append(it.get('thumbnail',''))
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
                            seg = {'class': cur['class'], 'start': display_start, 'end': float(cur['end']), 'score': float(max(cur['scores'])), 'thumbnail': thumb, 'body_type': bt, 'count': cur['count']}
                            segments.append(seg)
                            cur = {'class': cls, 'start': it.get('timestamp',0.0), 'end': it.get('timestamp',0.0), 'scores':[it.get('score',0.0)], 'thumbnails':[it.get('thumbnail','')], 'body_types':[it.get('body_type','unknown')], 'count':1, 'best': it}
                if cur is not None:
                    bt = Counter(cur['body_types']).most_common(1)[0][0] if cur['body_types'] else 'unknown'
                    thumb = cur['best'].get('thumbnail','') or ''
                    if thumb:
                        thumb = thumb.replace('\\','/').lstrip('/')
                    display_start = float(cur['best'].get('timestamp', cur['start']))
                    seg = {'class': cur['class'], 'start': display_start, 'end': float(cur['end']), 'score': float(max(cur['scores'])), 'thumbnail': thumb, 'body_type': bt, 'count': cur['count']}
                    segments.append(seg)
        except Exception:
            segments = []

        # write report
        report = {
            'video': original_filename,
            'video_id': video_id,
            'duration': duration,
            'fps': fps,
            'detections': results,
            'best_thumbnail': best_thumb,
            'segments': segments,
            'scan_time': scan_time,
        }
        try:
            with open(os.path.join(UPLOAD_FOLDER, f"{video_id}_report.json"), 'w', encoding='utf-8') as fh:
                json.dump(report, fh, indent=2)
        except Exception:
            pass

        # finalize job
        view_t = segments[0].get('start', 0) if segments else (results[0].get('timestamp', 0) if results else 0)
        job.update({'state': 'done', 'percent': 100.0, 'view': f'/view/{video_id}?t={view_t}', 'scan_time': scan_time})

    except Exception as e:
        job.update({'state': 'error', 'error': str(e)})
    finally:
        with JOBS_LOCK:
            JOBS[job_id] = job


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        cards = []
        for p in Path(UPLOAD_FOLDER).glob('*_report.json'):
            try:
                with open(p, 'r', encoding='utf-8') as fh:
                    rep = json.load(fh)
                dets = rep.get('detections', [])
                segs = rep.get('segments', [])
                if segs:
                    first_ts = segs[0].get('start', 0)
                else:
                    first_ts = dets[0].get('timestamp') if dets else 0
                thumb = rep.get('best_thumbnail') or ''
                if thumb:
                    thumb = thumb.replace('\\','/').lstrip('/')
                tags = []
                if dets:
                    freq = {}
                    for d in dets:
                        cls = d.get('class')
                        if cls:
                            freq[cls] = freq.get(cls, 0) + 1
                    tags = sorted(freq.keys(), key=lambda k: -freq[k])
                else:
                    tags = ['SAFE']
                cards.append({'video_id': rep.get('video_id'), 'video_name': rep.get('video'), 'first_ts': first_ts, 'thumb': thumb, 'tags': tags, 'scan_time': rep.get('scan_time', 0)})
            except Exception:
                continue
        return render_template_string(INDEX_HTML, cards=cards, format_time=format_time)

    # POST: upload file -> start background job
    f = request.files.get('video')
    if not f or f.filename == '':
        return jsonify({'ok': False, 'error': 'no file'}), 400
    original = f.filename
    video_id = str(uuid.uuid4())
    video_path = os.path.join(UPLOAD_FOLDER, f"{video_id}.mp4")
    f.save(video_path)

    job_id = video_id
    with JOBS_LOCK:
        JOBS[job_id] = {'state': 'queued', 'stage': 'queued', 'percent': 0.0, 'processed': 0, 'total': 0, 'start_time': time.time()}

    t = threading.Thread(target=process_video_job, args=(video_id, original, video_path, job_id), daemon=True)
    t.start()

    return jsonify({'ok': True, 'job': job_id, 'view': f'/view/{video_id}'}), 200


@app.route('/status/<job_id>')
def status(job_id):
    j = JOBS.get(job_id)
    if not j:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    out = dict(j)
    eta = out.get('eta')
    if eta is not None:
        out['eta_readable'] = f"{int(eta//60)}m {int(eta%60)}s"
    return jsonify({'ok': True, 'status': out})


@app.route('/uploads/<path:filename>')
def uploaded(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/delete/<video_id>', methods=['POST'])
def delete_video(video_id):
    removed = []
    errors = []
    try:
        v = os.path.join(UPLOAD_FOLDER, f"{video_id}.mp4")
        if os.path.exists(v):
            os.remove(v); removed.append(v)
        r = os.path.join(UPLOAD_FOLDER, f"{video_id}_report.json")
        if os.path.exists(r):
            os.remove(r); removed.append(r)
        b = os.path.join(UPLOAD_FOLDER, f"{video_id}_best.jpg")
        if os.path.exists(b):
            os.remove(b); removed.append(b)
        tdir = os.path.join(UPLOAD_FOLDER, 'thumbs')
        if os.path.isdir(tdir):
            for p in Path(tdir).glob(f"{video_id}_f*.jpg"):
                try:
                    os.remove(str(p)); removed.append(str(p))
                except Exception:
                    errors.append(str(p))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'removed': removed, 'errors': errors})


@app.route('/view/<video_id>')
def view_video(video_id):
    report = None
    for p in Path(UPLOAD_FOLDER).glob(f'{video_id}_report.json'):
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                report = json.load(fh); break
        except Exception:
            continue
    if not report:
        # If a background job exists for this id, show a waiting page that polls status
        j = JOBS.get(video_id)
        if j:
            return render_template_string(WAIT_HTML, job_id=video_id)
        return 'Report not found', 404
    dets = report.get('detections', [])
    segments = report.get('segments', [])
    best = report.get('best_thumbnail','')
    if best:
        best = os.path.basename(best).replace('\\','/')
    for d in dets:
        t = d.get('thumbnail','') or ''
        d['thumbnail'] = t.replace('\\','/').lstrip('/') if t else best
    for s in segments:
        t = s.get('thumbnail','') or ''
        s['thumbnail'] = t.replace('\\','/').lstrip('/') if t else best
    video_file = f"{video_id}.mp4"
    return render_template_string(RESULT_HTML, results=dets, segments=segments, duration=report.get('duration',0.0), video_file=video_file, video_name=report.get('video',''))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
