"""Publish only an independently revalidated bundle from a real Actions run."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from verify_bundle import verify, require
from previous_release import previous as fetch_previous


def gh(*args):
    result = subprocess.run(['gh', *map(str, args)], text=True, encoding='utf-8',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    require(result.returncode == 0, 'GitHub release operation failed; inspect the draft before retrying')
    return result.stdout


def publish(bundle, candidate, aapt, apksigner, previous):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Publication requires a real GitHub Actions run')
    require(os.environ.get('GITHUB_REPOSITORY') == 'SolmiApp/solmi-releases', 'Wrong publication repository')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'Publisher must run from the trusted main branch')
    require(bool(os.environ.get('GH_TOKEN')), 'Actions token is required')
    require(re.fullmatch('[0-9a-f]{40}', candidate) is not None, 'Candidate must be an immutable commit SHA')
    plan = verify(bundle, 'solmi', aapt, apksigner, previous)
    repo, tag = plan['repository'], plan['tag']
    with tempfile.TemporaryDirectory(prefix='solmi-publish-') as directory:
        directory = Path(directory)
        def confirm_previous(filename):
            current_path = directory / filename
            found = fetch_previous(current_path, allow_first=True)
            current = json.loads(current_path.read_text(encoding='utf-8')) if found else None
            require(current == previous, 'Previous release changed since validation; rerun validation')
        confirm_previous('previous-before.json')
        notes = directory / 'release-notes.txt'
        notes.write_text(plan['notes'], encoding='utf-8')
        gh('release', 'create', tag, Path(bundle) / plan['apk'], Path(bundle) / 'update-manifest.json',
           '--repo', repo, '--target', candidate, '--title', f"Solmi {plan['versionName']} ({plan['versionCode']})",
           '--notes-file', notes, '--draft')
        release = json.loads(gh('release', 'view', tag, '--repo', repo, '--json', 'author,isDraft,assets'))
        require(release.get('author', {}).get('login') == 'github-actions[bot]', 'Release must be authored by the real Actions bot')
        require(release.get('isDraft') is True, 'Uploaded release must remain a draft until readback validation')
        require({asset['name'] for asset in release.get('assets', [])} == {plan['apk'], 'update-manifest.json'}, 'Unexpected release assets')
        readback = directory / 'readback'
        readback.mkdir()
        gh('release', 'download', tag, '--repo', repo, '--dir', readback)
        verified = verify(readback, 'solmi', aapt, apksigner, previous)
        require(verified == plan, 'Uploaded release differs from validated candidate')
        confirm_previous('previous-before-publish.json')
        gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--aapt', required=True)
    parser.add_argument('--apksigner', required=True)
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    previous = json.loads(args.previous.read_text(encoding='utf-8')) if args.previous else None
    plan = publish(args.bundle, args.candidate, args.aapt, args.apksigner, previous)
    print(f"Published {plan['repository']} {plan['tag']} using the real Actions token")
