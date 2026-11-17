"""Inspect the complete Git tree, even when the checkout itself is sparse."""
import argparse
from pathlib import Path
import re
import subprocess


def check(checkout, sha):
    if re.fullmatch('[0-9a-f]{40}', sha) is None:
        raise ValueError('Candidate must be a full immutable commit SHA')
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if head != sha:
        raise ValueError('Checked out commit differs from requested candidate')
    result = subprocess.run(['git', '-C', str(checkout), 'ls-tree', '-rz', '--full-tree', 'HEAD'], check=True, capture_output=True)
    entries = {}
    for entry in result.stdout.split(b'\0'):
        if not entry:
            continue
        metadata, filename = entry.split(b'\t', 1)
        mode, kind, _ = metadata.split(b' ')
        if mode != b'100644' or kind != b'blob':
            raise ValueError('Candidate may contain only regular artifact blobs')
        entries[filename.decode('utf-8')] = True
    if set(entries) != {'app-release.apk', 'update-manifest.json'}:
        raise ValueError('Entire candidate Git tree must contain only the signed APK and manifest')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    check(args.checkout, args.sha)
    print('Complete candidate Git tree contains only APK and update metadata')
