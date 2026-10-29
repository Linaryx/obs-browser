#!/usr/bin/env python3
"""Unit tests for benchmark.inspect_frames without ffmpeg, a GPU, or CEF."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark


def rgba(width, height, pixels):
    data = bytearray(width * height * 4)
    for (x, y), color in pixels.items():
        offset = (y * width + x) * 4
        data[offset:offset + 4] = bytes(color)
    return bytes(data)


def make_frame(width, height, marker=0, changes=None):
    pixels = {
        (50, 50): (255, 0, 0, 255),
        (width - 50, 50): (0, 128, 0, 128),
        (50, height - 50): (0, 0, 255, 255),
        (width - 50, height - 50): (0, 0, 0, 0),
        (0, 0): (marker, 0, 0, 255),
    }
    if changes:
        pixels.update(changes)
    return rgba(width, height, pixels)


class InspectFramesTest(unittest.TestCase):
    def setUp(self):
        scratch = Path('/tmp/opencode')
        self._tmp = tempfile.TemporaryDirectory(dir=str(scratch) if scratch.is_dir() else None)
        self.folder = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def inspect(self, images, width=1280, height=720):
        for index in range(len(images)):
            (self.folder / f'frame-{index + 1:04d}.png').write_bytes(b'')
        side_effect = list(images)
        with mock.patch('benchmark.subprocess.check_output', side_effect=side_effect) as check:
            result = benchmark.inspect_frames(self.folder, width, height)
        return result, check

    def assert_valid(self, width, height):
        images = [make_frame(width, height, marker) for marker in (1, 2, 3)]
        result, check = self.inspect(images, width, height)
        self.assertEqual(set(result), {'passed', 'colors', 'alpha', 'animation', 'samples'})
        self.assertTrue(result['passed'])
        self.assertTrue(result['colors'])
        self.assertTrue(result['alpha'])
        self.assertTrue(result['animation'])
        self.assertEqual(result['samples'], {
            'red': [255, 0, 0, 255],
            'half_green': [0, 128, 0, 128],
            'webgl_blue': [0, 0, 255, 255],
            'transparent': [0, 0, 0, 0],
        })
        self.assertEqual(check.call_count, 3)
        self.assertIn(str(self.folder / 'frame-0001.png'), check.call_args_list[0].args[0])
        self.assertEqual(check.call_args_list[0].kwargs, {'timeout': 30})

    def test_valid_1280x720(self):
        self.assert_valid(1280, 720)

    def test_valid_1920x1080(self):
        self.assert_valid(1920, 1080)

    def test_all_transparent_fails(self):
        result, _ = self.inspect([bytes(1280 * 720 * 4)] * 3)
        self.assertFalse(result['colors'])
        self.assertFalse(result['alpha'])
        self.assertFalse(result['passed'])

    def test_static_frames_fail_animation(self):
        images = [make_frame(1280, 720, marker=7)] * 3
        result, _ = self.inspect(images)
        self.assertTrue(result['colors'])
        self.assertTrue(result['alpha'])
        self.assertFalse(result['animation'])
        self.assertFalse(result['passed'])

    def test_missing_frames(self):
        (self.folder / 'unrelated.png').write_bytes(b'')
        with mock.patch('benchmark.subprocess.check_output') as check:
            result = benchmark.inspect_frames(self.folder)
        self.assertEqual(result, {'passed': False, 'reason': 'no screenshots'})
        check.assert_not_called()

    def test_malformed_frame_name(self):
        for name in ('frame-abc.png', 'frame-1-extra.png'):
            with self.subTest(name=name):
                frame = self.folder / name
                frame.write_bytes(b'')
                with mock.patch('benchmark.subprocess.check_output') as check:
                    result = benchmark.inspect_frames(self.folder)
                self.assertEqual(result, {'passed': False, 'reason': 'malformed frame name'})
                check.assert_not_called()
                frame.unlink()

    def test_wrong_raw_length(self):
        good = make_frame(1280, 720, marker=1)
        cases = {
            'empty_final': [good, good, b''],
            'truncated_first': [good[:-4], good, good],
        }
        for name, images in cases.items():
            with self.subTest(name=name):
                result, check = self.inspect(images)
                self.assertEqual(result, {'passed': False, 'reason': 'wrong frame size'})
                self.assertEqual(check.call_count, 3)

    def test_subprocess_failures(self):
        cases = [
            ('missing_ffmpeg', lambda: FileNotFoundError(), 'missing ffmpeg'),
            ('timeout', lambda: subprocess.TimeoutExpired(['ffmpeg'], 30), 'ffmpeg timeout'),
            ('error', lambda: subprocess.CalledProcessError(1, ['ffmpeg']), 'ffmpeg failed'),
            ('oserror', lambda: OSError(), 'ffmpeg failed'),
        ]
        for name, error, reason in cases:
            with self.subTest(name=name):
                for index in range(3):
                    (self.folder / f'frame-{index + 1:04d}.png').write_bytes(b'')
                with mock.patch('benchmark.subprocess.check_output', side_effect=error()) as check:
                    result = benchmark.inspect_frames(self.folder)
                self.assertEqual(result, {'passed': False, 'reason': reason})
                self.assertEqual(check.call_args.kwargs, {'timeout': 30})

    def test_blank_sampled_frame_fails(self):
        good_first = make_frame(1280, 720, marker=1)
        good_last = make_frame(1280, 720, marker=2)
        blank = bytes(1280 * 720 * 4)
        expected = {
            'red': [255, 0, 0, 255],
            'half_green': [0, 128, 0, 128],
            'webgl_blue': [0, 0, 255, 255],
            'transparent': [0, 0, 0, 0],
        }
        cases = {'startup': [blank, good_first, good_last], 'middle': [good_first, blank, good_last]}
        for name, images in cases.items():
            with self.subTest(name=name):
                result, _ = self.inspect(images)
                self.assertTrue(result['animation'])
                self.assertFalse(result['colors'])
                self.assertFalse(result['alpha'])
                self.assertFalse(result['passed'])
                self.assertEqual(result['samples'], expected)

    def test_wrong_color_samples_fail(self):
        cases = {
            'swapped': {(50, 50): (0, 0, 255, 255), (50, 720 - 50): (255, 0, 0, 255)},
            'magenta_red': {(50, 50): (255, 0, 255, 255)},
            'cyan_blue': {(50, 720 - 50): (0, 255, 255, 255)},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                images = [make_frame(1280, 720, marker, changes) for marker in (1, 2, 3)]
                result, _ = self.inspect(images)
                self.assertFalse(result['colors'])
                self.assertTrue(result['alpha'])
                self.assertTrue(result['animation'])
                self.assertFalse(result['passed'])

    def test_incorrect_blue_fails(self):
        changes = {(50, 720 - 50): (255, 0, 0, 255)}
        images = [make_frame(1280, 720, marker, changes) for marker in (1, 2, 3)]
        result, _ = self.inspect(images)
        self.assertFalse(result['colors'])
        self.assertTrue(result['alpha'])
        self.assertTrue(result['animation'])
        self.assertFalse(result['passed'])

    def test_incorrect_alpha_fails(self):
        cases = {
            'green_out_of_band': {(1280 - 50, 50): (0, 128, 0, 200)},
            'green_not_premultiplied': {(1280 - 50, 50): (0, 255, 0, 128)},
            'green_wrong_channel': {(1280 - 50, 50): (0, 128, 255, 128)},
            'clear_opaque': {(1280 - 50, 720 - 50): (0, 0, 0, 255)},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                images = [make_frame(1280, 720, marker, changes) for marker in (1, 2, 3)]
                result, _ = self.inspect(images)
                self.assertTrue(result['colors'])
                self.assertFalse(result['alpha'])
                self.assertTrue(result['animation'])
                self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
