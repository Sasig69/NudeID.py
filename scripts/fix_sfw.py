import glob, json, os, cv2, shutil

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
UPLOAD_FOLDER = os.path.normpath(UPLOAD_FOLDER)
THUMB_DIR = os.path.join(UPLOAD_FOLDER, 'thumbs')

os.makedirs(THUMB_DIR, exist_ok=True)

for p in glob.glob(os.path.join(UPLOAD_FOLDER, '*_report.json')):
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            rep = json.load(fh)
    except Exception as e:
        print('skip read', p, e)
        continue
    if rep.get('detections') == [] and not rep.get('best_thumbnail'):
        vid = rep.get('video_id') + '.mp4'
        vp = os.path.join(UPLOAD_FOLDER, vid)
        if not os.path.exists(vp):
            print('video missing', vp)
            continue
        cap = cv2.VideoCapture(vp)
        if not cap.isOpened():
            print('cant open', vp)
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            print('no frame', vp)
            cap.release()
            continue
        thumb_name = f"{rep.get('video_id')}_f0.jpg"
        thumb_path = os.path.join(THUMB_DIR, thumb_name)
        try:
            cv2.imwrite(thumb_path, frame)
            best_name = f"{rep.get('video_id')}_best.jpg"
            shutil.copy2(thumb_path, os.path.join(UPLOAD_FOLDER, best_name))
            rep['best_thumbnail'] = best_name
            with open(p, 'w', encoding='utf-8') as fh:
                json.dump(rep, fh, indent=2)
            print('updated', p)
        except Exception as e:
            print('error processing', p, e)
        cap.release()
    else:
        print('skip already', p)
