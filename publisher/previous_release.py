"""Fetch the public main-app manifest; fail closed on transport/server errors."""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Solmi-release-validation', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Previous release metadata exceeds size limit')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('Previous release response is not an object')
    return data


def previous(output, allow_first=False):
    repository = 'SolmiApp/solmi-releases'
    try:
        release = fetch_json(f'https://api.github.com/repos/{repository}/releases/latest')
    except urllib.error.HTTPError as error:
        error.close()
        if error.code != 404 or not allow_first:
            raise
        return False
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Previous latest release must be public and stable')
    assets = [asset for asset in release.get('assets', []) if asset.get('name') == 'update-manifest.json']
    if len(assets) != 1:
        raise ValueError('Previous release must contain exactly one update manifest')
    url = assets[0].get('browser_download_url', '')
    if not url.startswith(f'https://github.com/{repository}/releases/download/') or not url.endswith('/update-manifest.json'):
        raise ValueError('Previous manifest is outside the organization release channel')
    data = fetch_json(url)
    if type(data.get('versionCode')) is not int or data['versionCode'] <= 0:
        raise ValueError('Previous release version is invalid')
    Path(output).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-first-release', action='store_true')
    args = parser.parse_args()
    print('Previous public manifest fetched' if previous(args.output, args.allow_first_release) else 'Explicit first-release mode; no previous release')
