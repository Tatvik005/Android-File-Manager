"""
tests/test_ui.py
Unit and integration tests for PyQt6 UI components and device states.
"""

import sys
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from adb_manager import AdbManager, ConnectionState, DeviceInfo, RemoteFileInfo
from main_window import MainWindow

# Ensure single QApplication instance across tests
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])


class TestUIComponents(unittest.TestCase):
    def setUp(self):
        self.adb = AdbManager()
        self.window = MainWindow(adb_manager=self.adb)

    def tearDown(self):
        if hasattr(self.window, "monitor"):
            self.window.monitor.stop()
        self.window.deleteLater()
        app.processEvents()

    def test_mac_pane_initialization(self):
        # Mac pane should default to user home and contain items
        self.assertGreater(self.window.mac_pane.model.rowCount(), 0)
        self.assertTrue(self.window.mac_pane.path_bar.path_edit.text().startswith("/"))

    def test_state_debugging_disabled(self):
        dev = DeviceInfo(serial="RZCY512P8PT", state=ConnectionState.DEBUGGING_DISABLED, model="Samsung Galaxy")
        self.window.on_device_status_changed(ConnectionState.DEBUGGING_DISABLED, dev, "USB Debugging is OFF")
        self.assertEqual(self.window.current_state, ConnectionState.DEBUGGING_DISABLED)
        self.assertFalse(self.window.unauth_banner.isHidden())
        self.assertIn("USB Debugging is OFF", self.window.status_device_label.text())

    def test_state_no_device(self):
        self.window.on_device_status_changed(ConnectionState.NO_DEVICE, None, "No Device Found")
        self.assertEqual(self.window.current_state, ConnectionState.NO_DEVICE)
        self.assertTrue(self.window.unauth_banner.isHidden())
        self.assertIn("No Android Device Found", self.window.status_device_label.text())
        self.assertEqual(self.window.android_pane.model.rowCount(), 0)

    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_state_unauthorized(self, mock_warning):
        dev = DeviceInfo(serial="FA12345678", state=ConnectionState.UNAUTHORIZED, model="Pixel 7")
        self.window.on_device_status_changed(ConnectionState.UNAUTHORIZED, dev, "Unauthorized")
        self.assertEqual(self.window.current_state, ConnectionState.UNAUTHORIZED)
        self.assertFalse(self.window.unauth_banner.isHidden())
        self.assertIn("Unauthorized", self.window.status_device_label.text())
        mock_warning.assert_called_once()

    def test_state_connected_with_items(self):
        dev = DeviceInfo(serial="FA12345678", state=ConnectionState.CONNECTED, model="Galaxy S23")
        self.window.on_device_status_changed(ConnectionState.CONNECTED, dev, "Connected")
        self.assertEqual(self.window.current_state, ConnectionState.CONNECTED)
        self.assertTrue(self.window.unauth_banner.isHidden())
        self.assertIn("Connected", self.window.status_device_label.text())

        # Test populating remote items
        mock_items = [
            RemoteFileInfo(name="Download", path="/sdcard/Download", is_dir=True, size=0, date_str="2026-11-06 12:00", permissions="drwxrwx--x"),
            RemoteFileInfo(name="DCIM", path="/sdcard/DCIM", is_dir=True, size=0, date_str="2026-11-06 12:00", permissions="drwxrwx--x"),
            RemoteFileInfo(name="photo.jpg", path="/sdcard/photo.jpg", is_dir=False, size=2048500, date_str="2026-11-06 12:00", permissions="-rw-rw----"),
        ]
        self.window._on_android_listing_finished("/sdcard", mock_items)
        self.assertEqual(self.window.android_pane.model.rowCount(), 3)

        # First item should be directory
        first_item = self.window.android_pane.model.get_item(0)
        self.assertTrue(first_item.is_dir)

    def test_double_click_folder_triggers_load(self):
        dev = DeviceInfo(serial="FA12345678", state=ConnectionState.CONNECTED, model="Galaxy S23")
        self.window.on_device_status_changed(ConnectionState.CONNECTED, dev, "Connected")

        folder_item = RemoteFileInfo(
            name="Download",
            path="/storage/emulated/0/Download",
            is_dir=True,
            size=0,
            date_str="2026-11-06 12:00",
            permissions="drwxrwx--x"
        )
        self.window._on_android_listing_finished("/storage/emulated/0", [folder_item])

        with patch.object(self.window, "load_android_directory") as mock_load:
            # Simulate double click via proxy model
            p_idx = self.window.android_pane.proxy_model.index(0, 0)
            self.window.android_pane.on_double_click(p_idx)
            mock_load.assert_called_once_with("/storage/emulated/0/Download")

    def test_path_bar_display_and_current_path_sync(self):
        self.window.android_pane.path_bar.set_path("/storage/emulated/0/DCIM")
        self.assertEqual(self.window.android_pane.current_path, "/storage/emulated/0/DCIM")
        self.assertEqual(self.window.android_pane.path_bar.path_edit.text(), "Internal Storage / DCIM")

        with patch.object(self.window, "load_android_directory") as mock_load:
            self.window.android_pane.path_bar.go_up()
            # go_up should emit parent: /storage/emulated/0
            self.assertEqual(self.window.android_pane.current_path, "/storage/emulated/0/DCIM")

    def test_return_key_opens_selected_folder(self):
        dev = DeviceInfo(serial="FA12345678", state=ConnectionState.CONNECTED, model="Galaxy S23")
        self.window.on_device_status_changed(ConnectionState.CONNECTED, dev, "Connected")

        folder_item = RemoteFileInfo(
            name="DCIM",
            path="/storage/emulated/0/DCIM",
            is_dir=True,
            size=0,
            date_str="2026-11-06 12:00",
            permissions="drwxrwx--x"
        )
        self.window._on_android_listing_finished("/storage/emulated/0", [folder_item])

        # Focus table view and select the item
        self.window.android_pane.table_view.setCurrentIndex(
            self.window.android_pane.proxy_model.index(0, 0)
        )

        with patch.object(self.window, "load_android_directory") as mock_load:
            self.window.on_return_open_shortcut()
            mock_load.assert_called_once_with("/storage/emulated/0/DCIM")


if __name__ == "__main__":
    unittest.main()
