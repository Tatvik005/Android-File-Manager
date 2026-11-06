"""
tests/test_adb.py
Unit tests for ADB parser, command builder, and device detection.
"""

import unittest
from adb_manager import AdbManager, ConnectionState, RemoteFileInfo


class TestAdbManager(unittest.TestCase):
    def setUp(self):
        self.mgr = AdbManager()

    def test_find_adb_binary(self):
        self.assertTrue(bool(self.mgr.adb_path))
        print(f"Detected ADB binary at: {self.mgr.adb_path}")

    def test_parse_toybox_ls(self):
        sample = "drwxrwx--x 41 root sdcard_rw 4096 2026-11-06 12:00 Download"
        info = self.mgr.parse_ls_line(sample, "/sdcard")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "Download")
        self.assertEqual(info.path, "/sdcard/Download")
        self.assertTrue(info.is_dir)
        self.assertFalse(info.is_symlink)
        self.assertEqual(info.permissions, "drwxrwx--x")
        self.assertEqual(info.owner, "root")
        self.assertEqual(info.group, "sdcard_rw")

    def test_parse_file_with_spaces(self):
        sample = "-rw-rw---- 1 root sdcard_rw 1048576 2026-11-06 11:30 My Super Photo 2024.jpg"
        info = self.mgr.parse_ls_line(sample, "/sdcard/DCIM")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "My Super Photo 2024.jpg")
        self.assertEqual(info.path, "/sdcard/DCIM/My Super Photo 2024.jpg")
        self.assertFalse(info.is_dir)
        self.assertEqual(info.size, 1048576)
        self.assertEqual(info.extension, "jpg")

    def test_parse_symlink(self):
        sample = "lrwxrwxrwx 1 root root 19 2026-11-06 10:00 sdcard -> /storage/emulated/0"
        info = self.mgr.parse_ls_line(sample, "/")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "sdcard")
        self.assertEqual(info.path, "/sdcard")
        self.assertTrue(info.is_symlink)
        self.assertEqual(info.link_target, "/storage/emulated/0")

    def test_parse_month_date_format(self):
        sample = "-rw-r--r-- 1 shell shell 2048 Jan 15 14:05 test.txt"
        info = self.mgr.parse_ls_line(sample, "/sdcard")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "test.txt")
        self.assertEqual(info.size, 2048)
        self.assertEqual(info.date_str, "Jan 15 14:05")

    def test_ignore_dots_and_totals(self):
        self.assertIsNone(self.mgr.parse_ls_line("total 128", "/sdcard"))
        self.assertIsNone(self.mgr.parse_ls_line("drwxrwxr-x 2 root root 4096 2026-11-06 12:00 .", "/sdcard"))
        self.assertIsNone(self.mgr.parse_ls_line("drwxrwxr-x 2 root root 4096 2026-11-06 12:00 ..", "/sdcard"))
        self.assertIsNone(self.mgr.parse_ls_line("ls: /data: Permission denied", "/sdcard"))

    def test_device_status_detection(self):
        state, dev, msg = self.mgr.get_primary_device()
        print(f"Device status check: state={state}, msg='{msg}'")
        self.assertIn(
            state,
            [
                ConnectionState.NO_DEVICE,
                ConnectionState.CONNECTED,
                ConnectionState.UNAUTHORIZED,
                ConnectionState.DEBUGGING_DISABLED,
            ],
        )


if __name__ == "__main__":
    unittest.main()
