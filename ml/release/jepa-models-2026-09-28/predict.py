#!/usr/bin/env python3
"""YOLO26x (640 or 960) -> latest 23-way ConvNeXt-small; images, folder or ZIP."""
import argparse
import csv
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}


class Tee:
    def __init__(self, console, file):
        self.console, self.file = console, file

    def write(self, message):
        self.console.write(message)
        self.file.write(message)
        self.file.flush()
        return len(message)

    def flush(self):
        self.console.flush()
        self.file.flush()

    def isatty(self):
        return False


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def list_images(source):
    if source.is_dir():
        return [(str(p.relative_to(source)), p) for p in sorted(source.rglob('*'))
                if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith('._')]
    if source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as z:
            return [(n, None) for n in sorted(z.namelist()) if not n.endswith('/')
                    and Path(n).suffix.lower() in EXTENSIONS and '__MACOSX' not in Path(n).parts
                    and not Path(n).name.startswith('._')]
    if source.is_file() and source.suffix.lower() in EXTENSIONS:
        return [(source.name, source)]
    raise ValueError('Source must be an image, directory or ZIP of images')


def run(args):
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Output is not empty: {out}. Choose a new --output directory.')
    sources = list_images(args.source)
    if args.limit:
        sources = sources[:args.limit]
    if not sources:
        raise ValueError('No input images found')
    out.mkdir(parents=True, exist_ok=True)
    (out/'annotated').mkdir()
    log = (out/'run.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout, sys.stderr = Tee(sys.stdout, log), Tee(sys.stderr, log)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout)], force=True)
    logging.info('START live stdout/stderr + durable log=%s', out/'run.log')
    os.environ.update(YOLO_OFFLINE='True', YOLO_AUTOINSTALL='False',
                      YOLO_CONFIG_DIR=str(out/'runtime'), MPLCONFIGDIR=str(out/'runtime/matplotlib'))

    import cv2
    import numpy as np
    import torch
    import torchvision
    import ultralytics
    from PIL import Image, ImageOps
    from torchvision.models import convnext_small
    from ultralytics import YOLO
    from ultralytics.models.yolo.detect import DetectionPredictor

    torch.set_num_threads(args.threads)
    cv2.setNumThreads(1)
    device = args.device
    if device == 'auto':
        device = 'cuda:0' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')
    if device.isdigit():
        device = 'cuda:' + device
    td = torch.device(device)
    if td.type not in {'cpu', 'cuda', 'mps'}:
        raise ValueError(f'Unsupported device: {device}')
    assert ultralytics.__version__ == '8.4.160', 'Install the included Ultralytics wheel'
    files = [f'weights/yolo_{args.model}.pt', 'weights/convnext_small_latest.pth', 'reject_threshold.json']
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name in files:
        assert sha256(ROOT/name) == manifest[name]['sha256'], f'Checksum mismatch: {name}'
        logging.info('CHECKPOINT/CONFIG VERIFIED %s sha256=%s', name, manifest[name]['sha256'])
    classifier_checkpoint = torch.load(ROOT/files[1], map_location='cpu', weights_only=True)
    assert classifier_checkpoint['architecture'] == 'convnext_small' and classifier_checkpoint['num_classes'] == 23
    names = {int(k): v for k, v in classifier_checkpoint['class_names'].items()}
    assert names[22] == 'unknown' and names[20] == 'person'
    meta = classifier_checkpoint['preprocessing']
    threshold = json.loads((ROOT/'reject_threshold.json').read_text())['threshold']
    classifier = convnext_small(weights=None)
    classifier.classifier[2] = torch.nn.Linear(classifier.classifier[2].in_features, 23)
    classifier.load_state_dict(classifier_checkpoint['model_state_dict'], strict=True)
    classifier = classifier.float().eval().to(td)
    detector = YOLO(str(ROOT/files[0]))
    size = int(args.model)
    options = dict(predictor=DetectionPredictor, imgsz=size, conf=args.conf, iou=.7,
                   max_det=300, half=False, augment=False, rect=False, batch=1,
                   device=device, verbose=False)
    config = dict(model=args.model, imgsz=size, detector_confidence=args.conf, device=device,
                  precision='FP32', classifier_batch=args.batch_size, class_names=names,
                  classifier_preprocessing=meta, unknown_threshold=threshold,
                  checkpoints={name: manifest[name] for name in files},
                  versions=dict(torch=torch.__version__, torchvision=torchvision.__version__, ultralytics=ultralytics.__version__),
                  policy='Unknown if p_unknown > threshold; otherwise argmax of 22 known classes. Filter unknown/person by default; preserve every detection in JSON. No combined-score cutoff.',
                  show_rejected=args.show_rejected, images=len(sources),
                  timings='Synchronized FP32 wall time after warmup on this device; decode, YOLO, crop, classifier measured separately. pipeline_ms excludes visualization/file writes.')
    save(out/'config.json', config)
    logging.info('CONFIG %s', json.dumps(config, ensure_ascii=False))
    logging.info('LOADED YOLO%s and ConvNeXt best_epoch=%s', args.model, classifier_checkpoint['best_epoch'])

    def sync():
        if td.type == 'cuda':
            torch.cuda.synchronize(td)
        elif td.type == 'mps':
            torch.mps.synchronize()

    def prepare(rgb, box):
        H, W = rgb.shape[:2]
        x1, y1, x2, y2 = box
        left, top = max(0, min(W-1, math.floor(x1))), max(0, min(H-1, math.floor(y1)))
        right, bottom = max(left+1, min(W, math.ceil(x2))), max(top+1, min(H, math.ceil(y2)))
        crop = rgb[top:bottom, left:right]
        h, w = crop.shape[:2]
        scale = meta['size']/max(h, w)
        nw, nh = max(1, round(w*scale)), max(1, round(h*scale))
        canvas = np.full((meta['size'], meta['size'], 3), meta['padding'], np.uint8)
        x, y = (meta['size']-nw)//2, (meta['size']-nh)//2
        canvas[y:y+nh, x:x+nw] = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_LINEAR)
        array = (canvas.astype(np.float32)/255-np.array(meta['mean'], np.float32))/np.array(meta['std'], np.float32)
        return torch.from_numpy(np.ascontiguousarray(array.transpose(2, 0, 1))), [left, top, right, bottom]

    results, latency = [], []
    with torch.inference_mode():
        for _ in range(3):
            detector.predict(np.zeros((size, size, 3), np.uint8), **options)
            classifier(torch.zeros((1, 3, meta['size'], meta['size']), device=td))
        sync()
        logging.info('WARMUP complete')
        z = zipfile.ZipFile(args.source) if args.source.suffix.lower() == '.zip' else None
        try:
            with (out/'predictions.jsonl').open('w', encoding='utf-8') as stream:
                for index, (name, path) in enumerate(sources, 1):
                    sync(); start = time.perf_counter()
                    content = z.read(name) if z else path.read_bytes()
                    with Image.open(io.BytesIO(content)) as image:
                        rgb = np.array(ImageOps.exif_transpose(image).convert('RGB'))
                    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                    decode_ms = (time.perf_counter()-start)*1000
                    sync(); t = time.perf_counter()
                    prediction = detector.predict(bgr, **options)[0]
                    xyxy = prediction.boxes.xyxy.cpu().numpy()
                    scores = prediction.boxes.conf.cpu().numpy()
                    sync(); detector_ms = (time.perf_counter()-t)*1000
                    boxes, crop_ms, classifier_ms = [], 0., 0.
                    for offset in range(0, len(xyxy), args.batch_size):
                        chunk = xyxy[offset:offset+args.batch_size]
                        assert np.isfinite(chunk).all()
                        t = time.perf_counter()
                        prepared = [prepare(rgb, box) for box in chunk]
                        tensors = torch.stack([x[0] for x in prepared])
                        crop_ms += (time.perf_counter()-t)*1000
                        sync(); t = time.perf_counter()
                        probs = classifier(tensors.to(td)).float().softmax(-1).cpu().numpy()
                        sync(); classifier_ms += (time.perf_counter()-t)*1000
                        assert np.isfinite(probs).all()
                        for j, (box, probability, (_, crop_box)) in enumerate(zip(chunk, probs, prepared)):
                            best = int(probability[:22].argmax())
                            unknown = float(probability[22])
                            cid = 22 if unknown > threshold else best
                            reason = 'unknown' if cid == 22 else ('person' if cid == 20 else None)
                            detector_score = float(scores[offset+j])
                            boxes.append(dict(id=len(boxes)+1, xyxy=box.tolist(), crop_xyxy=crop_box,
                                              class_id=cid, class_name=names[cid], class_probability=float(probability[cid]),
                                              detector_confidence=detector_score, best_known_name=names[best],
                                              best_known_probability=float(probability[best]), unknown_probability=unknown,
                                              combined_score=detector_score*float(probability[best]),
                                              retained=reason is None, filter_reason=reason,
                                              top3=[dict(class_name=names[int(k)], probability=float(probability[k]))
                                                    for k in np.argsort(probability)[::-1][:3]]))
                    sync()
                    timing = dict(filename=name, decode_ms=decode_ms, detector_ms=detector_ms,
                                  crop_ms=crop_ms, classifier_ms=classifier_ms,
                                  pipeline_ms=(time.perf_counter()-start)*1000, boxes=len(boxes),
                                  retained=sum(b['retained'] for b in boxes))
                    target = f'{index:04d}_{Path(name).stem}.jpg'
                    entry = dict(filename=name, width=rgb.shape[1], height=rgb.shape[0],
                                 annotated='annotated/'+target, boxes=boxes, timing=timing)
                    results.append(entry); latency.append(timing)
                    stream.write(json.dumps(entry, ensure_ascii=False, allow_nan=False)+'\n'); stream.flush()
                    canvas = bgr.copy()
                    for box in boxes:
                        if not box['retained'] and not args.show_rejected:
                            continue
                        x1, y1, x2, y2 = map(round, box['xyxy'])
                        color = (40, 210, 100) if box['retained'] else (100, 100, 255)
                        cv2.rectangle(canvas, (x1,y1), (x2,y2), color, 2)
                        label = f"{box['id']}: {box['class_name']} {box['class_probability']:.2f}"
                        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .55, 1)
                        tx = max(0, min(x1, canvas.shape[1]-tw-5)); ty = max(th+5, y1-4)
                        cv2.rectangle(canvas, (tx,ty-th-4), (tx+tw+4,ty+baseline), color, -1)
                        cv2.putText(canvas, label, (tx+2,ty-1), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,0,0), 1, cv2.LINE_AA)
                    ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 93])
                    assert ok
                    (out/'annotated'/target).write_bytes(encoded.tobytes())
                    logging.info('IMAGE %s/%s %s boxes=%s retained=%s YOLO=%.1fms classifier=%.1fms total=%.1fms',
                                 index, len(sources), name, len(boxes), timing['retained'], detector_ms, classifier_ms, timing['pipeline_ms'])
        finally:
            if z:
                z.close()
    save(out/'predictions.json', results)
    with (out/'latency.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(latency[0])); writer.writeheader(); writer.writerows(latency)
    summary = dict(images=len(results), boxes=sum(r['boxes'] for r in latency),
                   retained=sum(r['retained'] for r in latency), device=device, model=args.model,
                   mean_ms={k:sum(r[k] for r in latency)/len(latency)
                            for k in ['decode_ms','detector_ms','crop_ms','classifier_ms','pipeline_ms']})
    save(out/'COMPLETE.json', summary)
    logging.info('COMPLETE %s', json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Image, folder (recursive), or ZIP')
    parser.add_argument('--model', choices=['640','960'], default='640')
    parser.add_argument('--output', type=Path, required=True, help='New or empty directory')
    parser.add_argument('--device', default='auto', help='auto, cpu, mps, cuda:0 or 0')
    parser.add_argument('--conf', type=float, default=.25, help='YOLO confidence cutoff')
    parser.add_argument('--batch-size', type=int, default=16, help='ConvNeXt crop batch size')
    parser.add_argument('--threads', type=int, default=4, help='CPU threads')
    parser.add_argument('--limit', type=int, default=0, help='Limit images, 0 = all')
    parser.add_argument('--show-rejected', action='store_true', help='Also draw unknown/person; JSON always includes them')
    args = parser.parse_args()
    if not 0 < args.conf <= 1 or args.batch_size < 1 or args.threads < 1 or args.limit < 0:
        parser.error('Require 0 < conf <= 1, batch-size/threads >= 1, limit >= 0')
    try:
        run(args)
    except Exception:
        logging.exception('FAILED')
        raise
