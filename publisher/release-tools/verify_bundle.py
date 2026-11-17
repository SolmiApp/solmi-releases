"""Validate an already signed release bundle. Never builds, signs or publishes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

POLICIES = {
    'solmi': dict(product='Solmi', apk='app-release.apk', applicationId='ru.solmi.app',
                  repository='SolmiApp/solmi-releases',
                  certificateSha256='7b4a61c48c9acb2589e6c233e396dac8e85cb405fc71ce2be1fbcd26c5c5ccdd'),
    'sensor': dict(product='Solmi Sensor', apk='solmi-sensor.apk', applicationId='ru.solmi.sensor',
                   repository='SolmiApp/Solmi-Sensor',
                   certificateSha256='fb27861b3b589c6933f176aefa6d2bf129c61fb7daa91651aaa11e883cdfb283'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run_tool(command, failure):
    result = subprocess.run(command, text=True, encoding='utf-8', errors='replace',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    require(result.returncode == 0, failure)
    return result.stdout


def inspect_apk(apk, aapt, apksigner):
    certificates = run_tool([str(apksigner), 'verify', '--print-certs', str(apk)], 'Signature verification failed')
    fingerprints = re.findall(r'^Signer #\d+ certificate SHA-256 digest:\s*([0-9a-fA-F]{64})\s*$', certificates, re.M)
    # Some Android tool versions label the verified signer by its scheme.
    if not fingerprints:
        fingerprints = re.findall(r'^V[234] Signer: certificate SHA-256 digest:\s*([0-9a-fA-F]{64})\s*$', certificates, re.M)
    require(len(fingerprints) == 1, 'Expected exactly one verified signing identity')
    badging = run_tool([str(aapt), 'dump', 'badging', str(apk)], 'APK metadata inspection failed')
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging, re.M)
    sdk = re.search(r"^(?:minSdkVersion|sdkVersion):'(\d+)'", badging, re.M)
    require(package is not None and sdk is not None, 'APK package/version/minimum SDK not readable')
    return dict(applicationId=package[1], versionCode=int(package[2]), versionName=package[3],
                minSdk=int(sdk[1]), certificateSha256=fingerprints[0].lower())


def verify(bundle, product, aapt, apksigner, previous=None):
    policy = POLICIES[product]
    bundle = Path(bundle)
    names = {entry.name for entry in bundle.iterdir()}
    require(names == {policy['apk'], 'update-manifest.json'}, 'Bundle must contain only the signed APK and update-manifest.json')
    require(all(entry.is_file() and not entry.is_symlink() for entry in bundle.iterdir()), 'Bundle files must be regular files')
    data = json.loads((bundle / 'update-manifest.json').read_text(encoding='utf-8'))
    require(isinstance(data, dict), 'Manifest must be an object')
    code, name = data.get('versionCode'), data.get('versionName')
    require(type(code) is int and 0 < code <= 2100000000, 'Invalid versionCode')
    require(isinstance(name, str) and re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,95}', name), 'Invalid versionName')
    require(isinstance(data.get('notes'), str) and data['notes'].strip(), 'Release notes are required')
    if previous is not None:
        require(type(previous.get('versionCode')) is int, 'Previous manifest version is unreadable')
        require(code > previous['versionCode'], 'Update versionCode must strictly increase')
    history = data.get('history')
    require(isinstance(history, list) and 0 < len(history) <= 100, 'Invalid update history')
    codes = []
    for item in history:
        require(isinstance(item, dict) and type(item.get('code')) is int and 0 < item['code'] <= code,
                'Invalid or future version in update history')
        require(isinstance(item.get('notes'), str) and item['notes'].strip(), 'Invalid history notes')
        codes.append(item['code'])
    require(codes == sorted(set(codes)) and codes[-1] == code, 'Update history must end with this version in increasing order')
    require(history[-1]['notes'] == data['notes'], 'Latest history notes must match release notes')
    if product == 'solmi':
        require('artifacts' not in data, 'Solmi uses the flat update manifest')
        artifact = data
    else:
        require(data.get('schema') == 1 and data.get('minSdk') == 26, 'Unsupported Sensor manifest schema/SDK')
        artifacts = data.get('artifacts')
        require(isinstance(artifacts, list) and len(artifacts) == 1 and isinstance(artifacts[0], dict), 'Expected one Sensor artifact')
        artifact = artifacts[0]
        require(artifact.get('applicationId') == policy['applicationId'], 'Wrong Sensor artifact package')
        require(artifact.get('url') == policy['apk'], 'Sensor artifact URL must be the local APK filename')
    require(artifact.get('file') == policy['apk'], 'Artifact filename must match the product')
    apk = bundle / policy['apk']
    require(type(artifact.get('size')) is int and artifact['size'] == apk.stat().st_size and artifact['size'] > 0, 'APK size does not match manifest')
    with apk.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(artifact.get('sha256') == digest, 'APK SHA-256 does not match manifest')
    metadata = inspect_apk(apk, aapt, apksigner)
    require(metadata['certificateSha256'] == policy['certificateSha256'], 'Wrong APK signing identity')
    require(metadata['applicationId'] == policy['applicationId'], 'Wrong APK application package')
    # The Sensor manifest and BuildConfig use the base version, while the phone
    # product flavor appends exactly -phone to the APK's package versionName.
    expected_apk_name = name + '-phone' if product == 'sensor' else name
    require(metadata['versionCode'] == code and metadata['versionName'] == expected_apk_name, 'Manifest version differs from signed APK')
    if product == 'sensor':
        require(metadata['minSdk'] == data['minSdk'], 'Sensor minimum SDK differs from signed APK')
    return dict(product=policy['product'], repository=policy['repository'], apk=policy['apk'],
                tag=f'{product}-{code}', versionCode=code, versionName=name, sha256=digest,
                certificateSha256=metadata['certificateSha256'], notes=data['notes'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--product', required=True, choices=POLICIES)
    parser.add_argument('--aapt', required=True)
    parser.add_argument('--apksigner', required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    previous = json.loads(args.previous.read_text(encoding='utf-8')) if args.previous else None
    plan = verify(args.bundle, args.product, args.aapt, args.apksigner, previous)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in plan.items() if key != 'notes'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
