"""Regression tests for dataset pairing, classes.txt and duplicate auditing."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        for split in ('train', 'val', 'test'):
            images = data / 'images' / split
            labels = data / 'labels' / split
            images.mkdir(parents=True)
            labels.mkdir(parents=True)
            (images / 'sample.jpg').write_bytes(b'identical test fixture')
            (labels / 'sample.txt').write_text('0 0.5 0.5 0.2 0.3\n', encoding='utf-8')
            (labels / 'classes.txt').write_text('recyclable waste\nhazardous waste\nkitchen waste\nother waste\n', encoding='utf-8')
        cmd = [sys.executable, str(ROOT / 'scripts/package_dataset.py'), str(data), '--audit-only']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        assert report['local_images'] == 3
        assert report['cross_split_identical_image_groups'] == 1
        assert len(report['cross_split_identical_images'][0]['files']) == 3
        (data / 'labels/train/sample.txt').write_text('5 0.5 0.5 0.2 0.3\n', encoding='utf-8')
        assert subprocess.run(cmd, capture_output=True).returncode != 0
        (data / 'labels/train/sample.txt').unlink()
        assert subprocess.run(cmd, capture_output=True).returncode != 0
    print('DATASET_AUDIT_TEST_PASSED')

if __name__ == '__main__':
    main()
