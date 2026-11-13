#!/usr/bin/env python3
"""Check full test-bundle layout and relocated launch without loading OBS or CEF."""
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile

root = Path(__file__).resolve().parent.parent


def elf_fixture(path, needed):
    note = b''
    if needed is not None:
        properties = struct.pack('<III4x', 0xC0008002, 4, needed)
        note = struct.pack('<III', 4, len(properties), 5) + b'GNU\0' + properties
    ident = b'\x7fELF\x02\x01\x01' + bytes(9)
    header = struct.pack('<HHIQQQIHHHHHH', 3, 62, 1, 0, 64 if note else 0, 0,
                         0, 64, 56 if note else 0, 1 if note else 0, 0, 0, 0)
    program = struct.pack('<IIQQQQQQ', 4, 0, 120, 0, 0, len(note), len(note), 4) if note else b''
    path.write_bytes(ident + header + program + note)

with tempfile.TemporaryDirectory(prefix='obs-package-') as work:
    folder = Path(work)
    fixture = folder / 'v3.elf'
    elf_fixture(fixture, 7)
    baseline = folder / 'baseline.elf'
    elf_fixture(baseline, 1)
    unmarked = folder / 'unmarked.elf'
    elf_fixture(unmarked, None)
    v4 = folder / 'v4.elf'
    elf_fixture(v4, 15)
    unknown = folder / 'unknown.elf'
    elf_fixture(unknown, 16)
    guard_runtime = folder / 'guard runtime'
    guard_runtime.mkdir()
    for name, source in [('obs-browser-page', fixture), ('obs-browser.so', baseline), ('libcef.so', unmarked)]:
        (guard_runtime / name).write_bytes(source.read_bytes())
    guard = ['python3', str(root / 'scripts/check-bundle-isa.py'), str(guard_runtime)]
    report = json.loads(subprocess.check_output(guard, text=True))
    records = {record['path']: record for record in report['elf_files']}
    assert records['obs-browser-page']['needed_isa_bits'] == 7
    assert records['obs-browser.so']['needed_isa_bits'] == 1
    assert records['libcef.so']['needed_isa'] is None
    assert records['libcef.so']['metadata_check'] == 'no-required-isa-note'
    for rejected in [v4, unknown]:
        nested = guard_runtime / 'drivers'
        nested.mkdir(exist_ok=True)
        bad = nested / 'libEGL.so'
        bad.write_bytes(rejected.read_bytes())
        result = subprocess.run(guard, capture_output=True, text=True)
        assert result.returncode != 0 and 'drivers/libEGL.so' in result.stderr, result
        bad.unlink()
    build = folder / 'fake build'
    build.mkdir()
    (build / 'CMakeCache.txt').write_text('CMAKE_CXX_COMPILER:FILEPATH=c++\nCMAKE_CXX_FLAGS:STRING=-march=x86-64-v3 -mtune=generic\n')
    binary = folder / 'bin'
    binary.mkdir()
    cmake = binary / 'cmake'
    cmake.write_text('''#!/usr/bin/env bash
set -eu
if [[ $1 == --version ]]; then echo 'cmake fixture'; exit; fi
[[ $1 == --install && $3 == --prefix && $4 == /usr ]]
runtime=$DESTDIR/usr/lib/obs-browser-nvidia
mkdir -p "$runtime/locales" "$DESTDIR/usr/share/obs/obs-plugins/obs-browser" \\
  "$DESTDIR/usr/share/licenses/obs-browser-nvidia"
cp "$ELF_FIXTURE" "$runtime/obs-browser.so"
cp "$ELF_FIXTURE" "$runtime/libcef.so"
printf resources > "$runtime/resources.pak"
printf locale > "$runtime/locales/en-US.pak"
cp "$ELF_HELPER_FIXTURE" "$runtime/obs-browser-page"
chmod 755 "$runtime/obs-browser-page"
printf data > "$DESTDIR/usr/share/obs/obs-plugins/obs-browser/en-US.ini"
printf license > "$DESTDIR/usr/share/licenses/obs-browser-nvidia/CEF-LICENSE.txt"
''')
    cmake.chmod(0o755)
    env = os.environ.copy()
    env['PATH'] = str(binary) + ':' + env['PATH']
    env.update(ELF_FIXTURE=str(fixture), ELF_HELPER_FIXTURE=str(fixture))
    output = folder / 'output with spaces'
    subprocess.run(['bash', str(root / 'scripts/package-test-build.sh'), str(build), str(output)],
                   env=env, check=True, capture_output=True, text=True)
    archives = list(output.glob('*.tar.zst'))
    assert len(archives) == 1
    subprocess.run(['sha256sum', '-c', archives[0].name + '.sha256'], cwd=output, check=True,
                   capture_output=True)
    relocated = folder / 'relocated with spaces'
    relocated.mkdir()
    subprocess.run(['tar', '--zstd', '-xf', str(archives[0]), '-C', str(relocated)], check=True)
    bundle = next(relocated.iterdir())
    for name in ['runtime/obs-browser.so', 'runtime/libcef.so', 'runtime/resources.pak',
                 'runtime/locales/en-US.pak', 'runtime/obs-browser-page', 'data/en-US.ini',
                 'licenses/CEF-LICENSE.txt', 'README.txt', 'source.tar.gz', 'SOURCE-CHANGES.patch',
                 'fixtures/fixture.html', 'fixtures/heavy-fixture.html', 'docs/VALIDATION.md']:
        assert (bundle / name).is_file(), name
    metadata = json.loads((bundle / 'BUILD-INFO.json').read_text())
    assert metadata['source_revision'] and metadata['source_archive_sha256']
    assert metadata['nvidia_hardware_verified_by_packaging'] is False
    assert metadata['cpu_isa_check']['maximum_declared_isa'] == 'x86-64-v3'
    assert len(metadata['cpu_isa_check']['elf_files']) == 3
    assert all(record['sha256'] for record in metadata['cpu_isa_check']['elf_files'])
    assert metadata['compiler_flags']['CMAKE_CXX_FLAGS'] == '-march=x86-64-v3 -mtune=generic'
    assert 'x86_64-v3-' in archives[0].name
    rejected_output = folder / 'rejected output'
    rejected_env = dict(env, ELF_HELPER_FIXTURE=str(v4))
    failure = subprocess.run(['bash', str(root / 'scripts/package-test-build.sh'), str(build), str(rejected_output)],
                             env=rejected_env, capture_output=True, text=True)
    assert failure.returncode != 0 and 'obs-browser-page requires ISA' in failure.stderr, failure
    assert not list(rejected_output.glob('*.tar.zst'))
    assert not list(rejected_output.glob('*.sha256'))
    assert archives[0].name.endswith(metadata['source_archive_sha256'][:12] + '.tar.zst')
    source_names = subprocess.check_output(['tar', '-tzf', str(bundle / 'source.tar.gz')], text=True)
    assert 'scripts/package-test-build.sh' in source_names

    core = folder / 'core'
    core.mkdir()
    (core / 'obs-browser.so').touch()
    (core / 'system-plugin.so').touch()
    bwrap = binary / 'bwrap'
    bwrap.write_text('''#!/usr/bin/env python3
import json, os, sys
binds = [sys.argv[i+1:i+3] for i, value in enumerate(sys.argv) if value == '--ro-bind']
overlay = binds[1][0]
print(json.dumps({'args': sys.argv[1:], 'config': os.environ['XDG_CONFIG_HOME'],
                  'cache': os.environ['XDG_CACHE_HOME'], 'userdata': os.environ['XDG_DATA_HOME'],
                  'overlay': {name: os.readlink(os.path.join(overlay, name)) for name in os.listdir(overlay)},
                  'runtime': os.environ['OBS_BROWSER_RUNTIME_ROOT'],
                  'data': os.environ['OBS_BROWSER_DATA_ROOT']}))
''')
    bwrap.chmod(0o755)
    env.update(OBS_BROWSER_CORE_ROOT=str(core), OBS_BROWSER_COREDATA_ROOT=str(folder / 'coredata'),
               XDG_CONFIG_HOME=str(folder / 'existing user config'))
    env.pop('OBS_BROWSER_TEST_CONFIG_HOME', None)
    for override in [None, str(folder / 'explicit config')]:
        if override is not None:
            env['OBS_BROWSER_TEST_CONFIG_HOME'] = override
        launch = subprocess.check_output([str(bundle / 'obs-nvidia-browser'), '--fixture-argument'],
                                         env=env, text=True)
        result = json.loads(launch)
        assert result['config'] == (override or str(bundle / 'config'))
        assert Path(result['config']).is_dir()
        assert result['cache'] == result['config'] + '/cache'
        assert result['userdata'] == result['config'] + '/data'
        assert result['runtime'] == str(bundle / 'runtime')
        assert result['data'] == str(bundle / 'data')
        assert result['args'][-2:] == ['obs', '--fixture-argument']
        for name in ['obs-browser.so', 'obs-browser-page', 'libcef.so', 'locales']:
            assert result['overlay'][name] == str(bundle / 'runtime' / name)
        assert result['overlay']['system-plugin.so'].endswith('/original/system-plugin.so')
    assert not (folder / 'existing user config').exists()
print('relocatable test bundle: passed')
