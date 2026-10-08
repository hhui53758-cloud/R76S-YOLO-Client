"""Audit and package the local training snapshot; never modify the source dataset."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['recyclable waste', 'hazardous waste', 'kitchen waste', 'other waste']

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    source = args.dataset.resolve()
    files = []
    hashes = []
    stats = {}
    seen = defaultdict(set)
    image_paths = defaultdict(list)
    for split in ('train', 'val', 'test'):
        images = sorted(p for p in (source / 'images' / split).iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp'})
        labels = sorted(p for p in (source / 'labels' / split).glob('*.txt') if p.name != 'classes.txt')
        class_file = source / 'labels' / split / 'classes.txt'
        if class_file.exists() and class_file.read_text(encoding='utf-8-sig').splitlines() != NAMES:
            raise ValueError(f'Class mapping mismatch: {split}')
        if {p.stem for p in images} != {p.stem for p in labels}:
            raise ValueError(f'Image/label pairing mismatch: {split}')
        if len({p.stem for p in images}) != len(images):
            raise ValueError(f'Duplicate image stems: {split}')
        counts = Counter()
        for image in images:
            label = source / 'labels' / split / (image.stem + '.txt')
            for line in label.read_text(encoding='utf-8-sig').splitlines():
                if not line.strip():
                    continue
                fields = line.split()
                if len(fields) != 5:
                    raise ValueError(f'Invalid label: {label.name}')
                class_id = int(fields[0])
                coords = [float(x) for x in fields[1:]]
                if class_id not in range(4) or not all(0 <= x <= 1 for x in coords) or min(coords[2:]) <= 0:
                    raise ValueError(f'Invalid class/coordinates: {label.name}')
                counts[class_id] += 1
            for path in (image, label):
                relative = path.relative_to(source).as_posix()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                hashes.append(f'{digest}  {relative}')
                files.append((path, relative))
                if path == image:
                    seen[digest].add(split)
                    image_paths[digest].append(relative)
        stats[split] = {'images': len(images), 'labels': len(labels), 'boxes': sum(counts.values()), 'boxes_by_class': {NAMES[i]: counts[i] for i in range(4)}}
    report = {'source_url': 'https://universe.roboflow.com/keai-xiao-zwt9l/waste-8vlsn', 'source_confirmed_by': 'project owner', 'upstream_version': None, 'license': 'CC BY 4.0 (upstream dataset)', 'upstream_page_images': 2739, 'local_images': sum(s['images'] for s in stats.values()), 'splits': stats, 'cross_split_identical_image_groups': sum(len(s) > 1 for s in seen.values()), 'limitations': 'Local snapshot is not verified byte-for-byte against upstream. Extra images and historical modifications are not traced; upstream license scope for additions is unverified.'}
    report['cross_split_identical_images'] = [{'sha256': h, 'files': image_paths[h]} for h, splits in seen.items() if len(splits) > 1]
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.audit_only:
        return
    out = ROOT / 'release'
    out.mkdir(exist_ok=True)
    archive = out / 'trash-local-snapshot.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for path, relative in files:
            z.write(path, 'trash/' + relative)
        z.write(ROOT / 'training' / 'DATASET.md', 'trash/ATTRIBUTION.md')
        z.writestr('trash/data.yaml', 'path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n' + ''.join(f'  {i}: {name}\n' for i, name in enumerate(NAMES)))
        z.writestr('trash/SHA256SUMS.txt', '\n'.join(hashes) + '\n')
        z.writestr('trash/audit.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'training' / 'dataset_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'DATASET_SHA256SUMS.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='utf-8')
    print(f'PACKAGED: {archive.name} ({archive.stat().st_size} bytes)')

if __name__ == '__main__':
    main()
