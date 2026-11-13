#!/usr/bin/env python3
"""Reject declared ELF ISA requirements above x86-64-v3; this is not an opcode audit."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ISA_NEEDED = 0xC0008002
ISA_NAMES = ['x86-64-baseline', 'x86-64-v2', 'x86-64-v3', 'x86-64-v4']


def inspect_elf(path):
    with path.open('rb') as file:
        ident = file.read(16)
        if ident[:4] != b'\x7fELF':
            return None
        if len(ident) != 16 or ident[4] not in (1, 2) or ident[5] not in (1, 2):
            raise ValueError('unsupported ELF class or byte order')
        endian = '<' if ident[5] == 1 else '>'
        elf64 = ident[4] == 2
        header_format = endian + ('HHIQQQIHHHHHH' if elf64 else 'HHIIIIIHHHHHH')
        header_size = struct.calcsize(header_format)
        header_bytes = file.read(header_size)
        if len(header_bytes) != header_size:
            raise ValueError('truncated ELF header')
        header = struct.unpack(header_format, header_bytes)
        machine, phoff, shoff = header[1], header[4], header[5]
        phentsize, phnum, shentsize, shnum = header[8:12]
        if machine != 62 or not elf64:
            raise ValueError(f'expected ELF64 x86-64, got class {ident[4]}, machine {machine}')
        size = path.stat().st_size

        def read_at(offset, length):
            if offset < 0 or length < 0 or offset + length > size:
                raise ValueError('ELF range outside file')
            file.seek(offset)
            data = file.read(length)
            if len(data) != length:
                raise ValueError('truncated ELF data')
            return data

        note_ranges = set()
        for offset, entry_size, count, format_, note_type, range_indices in [
            (phoff, phentsize, phnum, endian + 'IIQQQQQQ', 4, (2, 5)),
            (shoff, shentsize, shnum, endian + 'IIQQQQIIQQ', 7, (4, 5)),
        ]:
            minimum = struct.calcsize(format_)
            if count and (entry_size < minimum or offset + entry_size * count > size):
                raise ValueError('invalid ELF header table')
            for index in range(count):
                entry = struct.unpack(format_, read_at(offset + index * entry_size, minimum))
                kind = entry[0] if note_type == 4 else entry[1]
                if kind == note_type:
                    note_ranges.add((entry[range_indices[0]], entry[range_indices[1]]))

        needed = None
        for offset, length in sorted(note_ranges):
            notes = read_at(offset, length)
            cursor = 0
            while cursor + 12 <= len(notes):
                namesz, descsz, kind = struct.unpack_from(endian + 'III', notes, cursor)
                name_start = cursor + 12
                desc_start = (name_start + namesz + 3) & ~3
                end = desc_start + descsz
                next_note = (end + 3) & ~3
                if end > len(notes) or name_start + namesz > len(notes):
                    raise ValueError('truncated ELF note')
                if kind == 5 and notes[name_start:name_start + namesz].rstrip(b'\0') == b'GNU':
                    prop = desc_start
                    while prop + 8 <= end:
                        prop_type, prop_size = struct.unpack_from(endian + 'II', notes, prop)
                        if prop + 8 + prop_size > end:
                            raise ValueError('truncated GNU property')
                        if prop_type == ISA_NEEDED:
                            if prop_size != 4:
                                raise ValueError('invalid x86 ISA property size')
                            bits = struct.unpack_from(endian + 'I', notes, prop + 8)[0]
                            needed = (needed or 0) | bits
                        prop = desc_start + ((prop + 8 + prop_size - desc_start + 7) & ~7)
                cursor = next_note
        file.seek(0)
        digest = hashlib.file_digest(file, 'sha256').hexdigest()
    return {
        'architecture': 'ELF64 x86-64',
        'sha256': digest,
        'needed_isa_bits': needed,
        'needed_isa': [name for bit, name in enumerate(ISA_NAMES) if needed is not None and needed & (1 << bit)]
                      if needed is not None else None,
        'metadata_check': 'no-required-isa-note' if needed is None else 'required-note-within-policy',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    files = []
    try:
        for path in sorted(runtime.rglob('*')):
            if not path.is_file():
                continue
            record = inspect_elf(path)
            if record is None:
                continue
            record['path'] = path.relative_to(runtime).as_posix()
            bits = record['needed_isa_bits']
            if bits is not None and bits & ~0x7:
                raise ValueError(f'{record["path"]} requires ISA bits 0x{bits:x}, above x86-64-v3')
            files.append(record)
        found = {record['path'] for record in files}
        for name in ['obs-browser-page', 'obs-browser.so', 'libcef.so']:
            if name not in found:
                raise ValueError(f'{name} is missing or is not an ELF executable/library')
    except (OSError, ValueError, struct.error) as error:
        print(f'Bundle ISA check failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({
        'maximum_declared_isa': 'x86-64-v3',
        'scope': 'Bundled ELF files only; GNU_PROPERTY_X86_ISA_1_NEEDED metadata',
        'limitation': 'Missing notes do not prove a baseline ISA. This is not an opcode audit or a check of host system libraries.',
        'elf_files': files,
    }, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
