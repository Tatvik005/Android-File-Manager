"""
adb_manager.py
Backend ADB wrapper module for macOS Android File Manager.
Handles subprocess commands, structured output parsing, error handling,
and USB connection states.
"""

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple


class ConnectionState(Enum):
    NO_DEVICE = "no_device"
    UNAUTHORIZED = "unauthorized"
    CONNECTED = "connected"
    OFFLINE = "offline"
    DEBUGGING_DISABLED = "debugging_disabled"
    ERROR = "error"


@dataclass
class DeviceInfo:
    serial: str
    state: ConnectionState
    model: str = "Android Device"
    product: str = ""
    device: str = ""
    raw_info: str = ""

    @property
    def is_wireless(self) -> bool:
        """Check if device is connected via Wi-Fi (IP:port format)."""
        return bool(re.search(r"^\d+\.\d+\.\d+\.\d+:\d+$", self.serial))

    @property
    def display_name(self) -> str:
        tag = " 📶" if self.is_wireless else ""
        if self.model and self.model != "Android Device":
            return f"{self.model} ({self.serial}){tag}"
        return f"{self.serial}{tag}"


@dataclass
class StorageVolume:
    name: str              # e.g. "Internal Storage" or "SD Card (1234-5678)"
    path: str              # e.g. "/storage/emulated/0" or "/storage/1234-5678"
    is_removable: bool     # True for SD Card / USB OTG, False for Internal Storage
    is_primary: bool       # True for Internal Storage
    uuid: str = ""         # e.g. "1234-5678"
    total_size: str = ""   # e.g. "64G"
    free_size: str = ""    # e.g. "45G"


@dataclass
class RemoteFileInfo:
    name: str
    path: str
    is_dir: bool
    size: int  # in bytes (0 for directories)
    date_str: str
    permissions: str
    owner: str = ""
    group: str = ""
    is_symlink: bool = False
    link_target: str = ""

    @property
    def extension(self) -> str:
        if self.is_dir:
            return ""
        parts = self.name.rsplit(".", 1)
        return parts[1].lower() if len(parts) > 1 else ""


def find_adb_binary() -> str:
    """Find the path to the adb binary."""
    # 1. Check PATH
    which_adb = shutil.which("adb")
    if which_adb and os.path.isfile(which_adb) and os.access(which_adb, os.X_OK):
        return which_adb

    # 2. Check standard Homebrew locations
    brew_paths = [
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
    ]
    for p in brew_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    # 3. Check standard Android SDK locations
    home = os.path.expanduser("~")
    sdk_paths = [
        os.path.join(home, "Library/Android/sdk/platform-tools/adb"),
        os.path.join(home, "android-sdk/platform-tools/adb"),
        os.path.join(home, "Library/Developer/Xamarin/android-sdk-macosx/platform-tools/adb"),
    ]
    for p in sdk_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return "adb"  # fallback to PATH default


def format_bytes(size: int) -> str:
    """Formats bytes into human-readable string (KB, MB, GB)."""
    if size < 0:
        return "--"
    if size == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    val = float(size)
    while val >= 1024.0 and unit_index < len(units) - 1:
        val /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(val)} B"
    return f"{val:.1f} {units[unit_index]}"


ANDROID_INTERNAL_STORAGE = "/storage/emulated/0"


def normalize_remote_path(path: str) -> str:
    """
    Normalize remote Android paths, robustly aliasing 'Internal Storage',
    'SD Card', or legacy '/sdcard' to the actual device mount point.
    """
    if not path:
        return ANDROID_INTERNAL_STORAGE
    clean = path.strip()
    if not clean:
        return ANDROID_INTERNAL_STORAGE

    # All storage roots alias
    if clean in ("/storage", "/storage/", "All Storage", "all storage"):
        return "/storage"

    # Emulated root -> internal storage
    if clean in ("/storage/emulated", "/storage/emulated/", "/storage/self", "/storage/self/"):
        return ANDROID_INTERNAL_STORAGE

    # Exact matches for root internal storage
    if clean in (
        ANDROID_INTERNAL_STORAGE,
        f"{ANDROID_INTERNAL_STORAGE}/",
        "Internal Storage",
        "internal storage",
        "Internal Storage/",
        "/sdcard",
        "/sdcard/",
        "/storage/self/primary",
        "/storage/self/primary/",
    ):
        return ANDROID_INTERNAL_STORAGE

    # Match 'Internal Storage' with optional slashes/spaces (e.g. 'Internal Storage / DCIM / Camera')
    match = re.match(r"^Internal\s+Storage(?:\s*[\/\\]\s*|\s+)(.*)$", clean, re.IGNORECASE)
    if match:
        rest = match.group(1).strip()
        parts = [p.strip() for p in re.split(r"\s*[\/\\]\s*", rest) if p.strip()]
        return f"{ANDROID_INTERNAL_STORAGE}/" + "/".join(parts) if parts else ANDROID_INTERNAL_STORAGE

    # Match 'SD Card' with optional UUID and path (e.g. 'SD Card / DCIM', 'SD Card (1234-5678) / DCIM')
    match_sd = re.match(r"^SD\s*Card(?:\s*\(([A-Za-z0-9_-]+)\))?(?:\s*[\/\\]\s*|\s+)?(.*)$", clean, re.IGNORECASE)
    if match_sd:
        uuid = match_sd.group(1)
        rest = match_sd.group(2).strip()
        parts = [p.strip() for p in re.split(r"\s*[\/\\]\s*", rest) if p.strip()] if rest else []
        if uuid:
            base = f"/storage/{uuid}"
        else:
            base = "/storage"
        return f"{base}/" + "/".join(parts) if parts else base

    # Match legacy /sdcard/ or /storage/self/primary/
    if clean.startswith("/sdcard/"):
        rel = clean[len("/sdcard/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        return f"{ANDROID_INTERNAL_STORAGE}/" + "/".join(parts) if parts else ANDROID_INTERNAL_STORAGE
    elif clean.startswith("/storage/self/primary/"):
        rel = clean[len("/storage/self/primary/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        return f"{ANDROID_INTERNAL_STORAGE}/" + "/".join(parts) if parts else ANDROID_INTERNAL_STORAGE

    # Clean redundant trailing slashes
    if len(clean) > 1 and clean.endswith("/"):
        clean = clean.rstrip("/")

    return clean


def format_display_remote_path(path: str) -> str:
    """Format remote path for user-friendly display (e.g. 'Internal Storage / DCIM' or 'SD Card (1234-5678) / DCIM')."""
    if not path:
        return "Internal Storage"
    clean = path.strip()
    if clean in (
        ANDROID_INTERNAL_STORAGE,
        f"{ANDROID_INTERNAL_STORAGE}/",
        "/sdcard",
        "/sdcard/",
        "/storage/self/primary",
        "/storage/self/primary/",
        "Internal Storage",
    ):
        return "Internal Storage"

    if clean in ("/storage", "/storage/"):
        return "All Storage Volumes"

    if clean.startswith(f"{ANDROID_INTERNAL_STORAGE}/"):
        rel = clean[len(ANDROID_INTERNAL_STORAGE) + 1:].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        return "Internal Storage / " + " / ".join(parts) if parts else "Internal Storage"
    if clean.startswith("/sdcard/"):
        rel = clean[len("/sdcard/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        return "Internal Storage / " + " / ".join(parts) if parts else "Internal Storage"
    if clean.startswith("/storage/self/primary/"):
        rel = clean[len("/storage/self/primary/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        return "Internal Storage / " + " / ".join(parts) if parts else "Internal Storage"

    # External storage: /storage/<UUID>/...
    if clean.startswith("/storage/"):
        rel = clean[len("/storage/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        if parts:
            first = parts[0]
            if first not in ("emulated", "self"):
                card_title = f"SD Card ({first})" if re.match(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$", first) else f"External Storage ({first})"
                sub_parts = parts[1:]
                return card_title + (" / " + " / ".join(sub_parts) if sub_parts else "")

    return clean


class AdbError(Exception):
    """Custom exception for ADB command failures."""
    pass


class AdbManager:
    """Wrapper around Android Debug Bridge (ADB) CLI."""

    def __init__(self, adb_path: Optional[str] = None):
        self.adb_path = adb_path or find_adb_binary()
        self.selected_serial: Optional[str] = None

    def _build_cmd(self, args: List[str], serial: Optional[str] = None) -> List[str]:
        target_serial = serial or self.selected_serial
        cmd = [self.adb_path]
        if target_serial:
            cmd.extend(["-s", target_serial])
        cmd.extend(args)
        return cmd

    def run_cmd(
        self,
        args: List[str],
        serial: Optional[str] = None,
        timeout: Optional[float] = 30.0,
        check: bool = False,
    ) -> Tuple[int, str, str]:
        """Execute an ADB command synchronously using subprocess."""
        cmd = self._build_cmd(args, serial)
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
            if check and res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip() or f"ADB exited with code {res.returncode}"
                raise AdbError(err_msg)
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"ADB command timed out after {timeout}s: {' '.join(cmd)}") from e
        except FileNotFoundError as e:
            raise AdbError(f"ADB binary not found at '{self.adb_path}'") from e
        except Exception as e:
            raise AdbError(f"Failed to execute ADB command: {e}") from e

    def start_server(self) -> bool:
        """Start the ADB server if not already running."""
        try:
            code, _, _ = self.run_cmd(["start-server"], timeout=10.0)
            return code == 0
        except Exception:
            return False

    def list_devices(self) -> List[DeviceInfo]:
        """
        Query adb devices -l and return structured list of connected devices.
        Handles states: device (connected), unauthorized, offline, etc.
        """
        code, stdout, _ = self.run_cmd(["devices", "-l"], timeout=10.0)
        if code != 0:
            return []

        devices: List[DeviceInfo] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices attached") or line.startswith("* daemon"):
                continue

            parts = line.split()
            if not parts:
                continue

            serial = parts[0]
            raw_state = parts[1] if len(parts) > 1 else "unknown"

            if raw_state == "device":
                state = ConnectionState.CONNECTED
            elif raw_state == "unauthorized":
                state = ConnectionState.UNAUTHORIZED
            elif raw_state == "offline":
                state = ConnectionState.OFFLINE
            else:
                state = ConnectionState.ERROR

            # Extract model, product, device if present in line
            model = "Android Device"
            product = ""
            device_name = ""
            for item in parts[2:]:
                if item.startswith("model:"):
                    model = item.split(":", 1)[1].replace("_", " ")
                elif item.startswith("product:"):
                    product = item.split(":", 1)[1]
                elif item.startswith("device:"):
                    device_name = item.split(":", 1)[1]

            devices.append(
                DeviceInfo(
                    serial=serial,
                    state=state,
                    model=model,
                    product=product,
                    device=device_name,
                    raw_info=line,
                )
            )

        return devices

    def detect_usb_android_devices(self) -> List[Dict[str, Any]]:
        """
        Check macOS IORegistry for physical USB Android devices
        even when USB Debugging is not enabled on the device.
        """
        known_vendors = {
            1256: "Samsung Galaxy",
            6353: "Google Pixel",
            10007: "Xiaomi / Redmi",
            8921: "OnePlus / Oppo / Realme",
            8888: "Motorola",
            4817: "Huawei",
            4100: "LG",
            4046: "Sony Xperia",
            2996: "HTC",
            11669: "Vivo",
            6018: "Infinix / Tecno",
        }
        try:
            res = subprocess.run(
                ["ioreg", "-r", "-c", "IOUSBHostDevice", "-l"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0,
            )
            if res.returncode != 0:
                return []

            devices = []
            seen_serials = set()
            blocks = res.stdout.split("+-o ")
            for block in blocks:
                vendor_m = re.search(r"\"idVendor\"\s*=\s*(\d+)", block)
                if not vendor_m:
                    continue
                v_id = int(vendor_m.group(1))

                prod_name_m = re.search(r"\"USB Product Name\"\s*=\s*\"([^\"]+)\"", block)
                p_name = prod_name_m.group(1) if prod_name_m else ""

                serial_m = re.search(r"\"kUSBSerialNumberString\"\s*=\s*\"([^\"]+)\"", block)
                serial = serial_m.group(1) if serial_m else ""

                prod_id_m = re.search(r"\"idProduct\"\s*=\s*(\d+)", block)
                p_id = int(prod_id_m.group(1)) if prod_id_m else 0

                is_android = (
                    v_id in known_vendors
                    or "android" in p_name.lower()
                    or "samsung" in p_name.lower()
                )

                if is_android:
                    vendor_name = known_vendors.get(v_id, "Android Device")
                    ident = serial or f"{v_id}:{p_id}"
                    if ident not in seen_serials:
                        seen_serials.add(ident)
                        devices.append({
                            "vendor_id": v_id,
                            "vendor_name": vendor_name,
                            "product_name": p_name or vendor_name,
                            "product_id": p_id,
                            "serial": serial,
                        })
            return devices
        except Exception:
            return []

    def get_primary_device(self) -> Tuple[ConnectionState, Optional[DeviceInfo], str]:
        """
        Get the overall connection state and the primary device.
        Returns:
            (state, device_info, status_message)
        """
        devices = self.list_devices()
        if not devices:
            # Check if an Android device is physically connected via USB
            # but USB Debugging is turned OFF on the phone
            usb_devs = self.detect_usb_android_devices()
            if usb_devs:
                first_usb = usb_devs[0]
                dev_info = DeviceInfo(
                    serial=first_usb["serial"] or "USB_CONNECTED",
                    state=ConnectionState.DEBUGGING_DISABLED,
                    model=first_usb["vendor_name"],
                    product=first_usb["product_name"],
                )
                disp = f"{first_usb['vendor_name']}" + (f" ({first_usb['serial']})" if first_usb['serial'] else "")
                return (
                    ConnectionState.DEBUGGING_DISABLED,
                    dev_info,
                    f"USB Device Detected ({disp}) — USB Debugging is OFF",
                )
            return ConnectionState.NO_DEVICE, None, "No Device Found"

        # Check if selected serial is still connected
        if self.selected_serial:
            for d in devices:
                if d.serial == self.selected_serial:
                    if d.state == ConnectionState.CONNECTED:
                        return ConnectionState.CONNECTED, d, f"Connected: {d.display_name}"
                    elif d.state == ConnectionState.UNAUTHORIZED:
                        return ConnectionState.UNAUTHORIZED, d, f"Unauthorized: {d.display_name}"
                    else:
                        return d.state, d, f"Device state: {d.state.value}"

        # Otherwise pick the first connected or unauthorized
        connected = [d for d in devices if d.state == ConnectionState.CONNECTED]
        if connected:
            self.selected_serial = connected[0].serial
            return ConnectionState.CONNECTED, connected[0], f"Connected: {connected[0].display_name}"

        unauthorized = [d for d in devices if d.state == ConnectionState.UNAUTHORIZED]
        if unauthorized:
            self.selected_serial = unauthorized[0].serial
            return (
                ConnectionState.UNAUTHORIZED,
                unauthorized[0],
                f"Device Unauthorized: {unauthorized[0].serial}",
            )

        first = devices[0]
        self.selected_serial = first.serial
        return first.state, first, f"Device ({first.state.value}): {first.serial}"

    # Regex for standard toybox / Linux ls -la
    _TOYBOX_RE = re.compile(
        r"^([bcdlps\-][rwx\-sStTxX]{9})\s+"   # Permissions (10 chars)
        r"(\d+)\s+"                          # Links
        r"(\S+)\s+"                          # Owner
        r"(\S+)\s+"                          # Group
        r"(\d+)\s+"                          # Size
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?|\w{3}\s+\d+\s+(?:\d{4}|\d{2}:\d{2}))\s+" # Date
        r"(.+)$"                             # Filename / symlink
    )

    # Fallback regex for older toolbox ls -la (no links column)
    _TOOLBOX_RE = re.compile(
        r"^([bcdlps\-][rwx\-sStTxX]{9})\s+"   # Permissions (10 chars)
        r"(\S+)\s+"                          # Owner
        r"(\S+)\s+"                          # Group
        r"(\d*)\s*"                          # Optional size
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?|\w{3}\s+\d+\s+(?:\d{4}|\d{2}:\d{2}))\s+" # Date
        r"(.+)$"                             # Filename / symlink
    )

    def parse_ls_line(self, line: str, parent_path: str) -> Optional[RemoteFileInfo]:
        """Parse a single line from 'adb shell ls -la'."""
        line = line.strip()
        if not line or line.startswith("total ") or line.startswith("ls: "):
            return None

        # Check toybox first
        m = self._TOYBOX_RE.match(line)
        if m:
            perms, links, owner, group, size_str, date_str, name_part = m.groups()
            size = int(size_str)
        else:
            m2 = self._TOOLBOX_RE.match(line)
            if m2:
                perms, owner, group, size_str, date_str, name_part = m2.groups()
                size = int(size_str) if size_str and size_str.isdigit() else 0
            else:
                return None

        # Ignore current/parent directories
        if name_part in (".", "..") or name_part.startswith("./"):
            return None

        is_symlink = perms.startswith("l")
        is_dir = perms.startswith("d")
        link_target = ""

        if is_symlink and " -> " in name_part:
            name, link_target = name_part.split(" -> ", 1)
            name = name.strip()
            link_target = link_target.strip()
        else:
            name = name_part.strip()

        # Build full remote path
        if parent_path.endswith("/"):
            full_path = f"{parent_path}{name}"
        else:
            full_path = f"{parent_path}/{name}"

        return RemoteFileInfo(
            name=name,
            path=full_path,
            is_dir=is_dir,
            size=size if not is_dir else 0,
            date_str=date_str,
            permissions=perms,
            owner=owner,
            group=group,
            is_symlink=is_symlink,
            link_target=link_target,
        )

    def list_files(self, remote_path: str, serial: Optional[str] = None) -> List[RemoteFileInfo]:
        """
        List files in an Android directory using `adb shell ls -la <path>`.
        Returns structured list sorted with directories first.
        """
        clean_path = normalize_remote_path(remote_path)

        # Safely quote path for remote shell
        quoted_path = shlex.quote(clean_path)
        cmd_args = ["shell", f"ls -la {quoted_path}"]

        code, stdout, stderr = self.run_cmd(cmd_args, serial=serial, timeout=15.0)

        combined_err = (stderr + "\n" + stdout).lower()

        # Handle explicit failures or errors returned by toybox ls
        if code != 0:
            if "permission denied" in combined_err:
                raise AdbError(f"Permission denied accessing '{clean_path}' on device.")
            if "no such file or directory" in combined_err:
                raise AdbError(f"Directory not found: '{clean_path}'")
            if "not a directory" in combined_err:
                raise AdbError(f"Path is not a directory: '{clean_path}'")
            if not stdout.strip():
                raise AdbError(stderr.strip() or f"Failed to list directory '{clean_path}' (code {code})")

        # Toybox ls sometimes returns code 0 even when printing 'ls: ...: No such file or directory'
        stdout_lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        if len(stdout_lines) == 1 and stdout_lines[0].startswith("ls: "):
            err_line = stdout_lines[0].lower()
            if "no such file or directory" in err_line:
                raise AdbError(f"Directory not found: '{clean_path}'")
            if "permission denied" in err_line:
                raise AdbError(f"Permission denied: '{clean_path}'")
            if "not a directory" in err_line:
                raise AdbError(f"Not a directory: '{clean_path}'")

        items: List[RemoteFileInfo] = []
        symlink_items: List[RemoteFileInfo] = []

        for line in stdout.splitlines():
            info = self.parse_ls_line(line, clean_path)
            if info:
                if info.is_symlink:
                    symlink_items.append(info)
                else:
                    items.append(info)

        # For symlinks, resolve whether target is directory if possible
        if symlink_items:
            for s in symlink_items:
                # Test if symlink target is a directory on device
                target_check_cmd = ["shell", f"[ -d {shlex.quote(s.path)} ] && echo is_dir || echo not_dir"]
                try:
                    c, out, _ = self.run_cmd(target_check_cmd, serial=serial, timeout=3.0)
                    if c == 0 and "is_dir" in out:
                        s.is_dir = True
                except Exception:
                    pass
                items.append(s)

        # Sort: directories first (alphabetical, case-insensitive), then files
        items.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return items

    def push(
        self,
        local_path: str,
        remote_path: str,
        serial: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Push local file or folder to Android: `adb push <local_path> <remote_path>`
        """
        if not os.path.exists(local_path):
            raise AdbError(f"Local file does not exist: {local_path}")

        code, stdout, stderr = self.run_cmd(
            ["push", local_path, remote_path],
            serial=serial,
            timeout=None,  # No timeout for large transfers
        )

        msg = (stdout + "\n" + stderr).strip()
        if code != 0:
            raise AdbError(f"Failed to push to Android: {msg}")

        return True, msg

    def pull(
        self,
        remote_path: str,
        local_path: str,
        serial: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Pull remote file or folder from Android: `adb pull <remote_path> <local_path>`
        """
        code, stdout, stderr = self.run_cmd(
            ["pull", remote_path, local_path],
            serial=serial,
            timeout=None,  # No timeout for large transfers
        )

        msg = (stdout + "\n" + stderr).strip()
        if code != 0:
            raise AdbError(f"Failed to pull from Android: {msg}")

        return True, msg

    def delete(
        self,
        remote_path: str,
        is_dir: bool = False,
        serial: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Delete file or directory on Android:
        `adb shell rm -f <path>` or `adb shell rm -rf <path>`
        """
        quoted = shlex.quote(remote_path)
        cmd_str = f"rm -rf {quoted}" if is_dir else f"rm -f {quoted}"

        code, stdout, stderr = self.run_cmd(["shell", cmd_str], serial=serial, timeout=15.0)
        out = (stdout + "\n" + stderr).strip()

        if "permission denied" in out.lower() or "read-only" in out.lower():
            raise AdbError(f"Failed to delete '{remote_path}': {out}")
        if code != 0 and out:
            raise AdbError(f"Error deleting '{remote_path}': {out}")

        return True, out

    def mkdir(self, remote_path: str, serial: Optional[str] = None) -> bool:
        """Create directory on Android: `adb shell mkdir -p <remote_path>`."""
        quoted = shlex.quote(remote_path)
        code, stdout, stderr = self.run_cmd(["shell", f"mkdir -p {quoted}"], serial=serial, timeout=10.0)
        if code != 0:
            out = (stdout + "\n" + stderr).strip()
            raise AdbError(f"Failed to create directory '{remote_path}': {out}")
        return True

    def rename(self, old_remote_path: str, new_remote_path: str, serial: Optional[str] = None) -> bool:
        """Rename/Move file on Android: `adb shell mv <old> <new>`."""
        old_q = shlex.quote(old_remote_path)
        new_q = shlex.quote(new_remote_path)
        code, stdout, stderr = self.run_cmd(["shell", f"mv {old_q} {new_q}"], serial=serial, timeout=10.0)
        if code != 0:
            out = (stdout + "\n" + stderr).strip()
            raise AdbError(f"Failed to rename '{old_remote_path}': {out}")
        return True

    def get_storage_stats(self, remote_path: str = ANDROID_INTERNAL_STORAGE, serial: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Query storage usage: `adb shell df -h <remote_path>`."""
        clean_path = normalize_remote_path(remote_path)
        quoted = shlex.quote(clean_path)
        try:
            code, stdout, _ = self.run_cmd(["shell", f"df -h {quoted}"], serial=serial, timeout=5.0)
            if code == 0:
                lines = [l.strip() for l in stdout.splitlines() if l.strip()]
                if len(lines) >= 2:
                    parts = lines[-1].split()
                    # filesystem, size, used, avail, use%, mounted on
                    if len(parts) >= 5:
                        return {
                            "size": parts[1],
                            "used": parts[2],
                            "free": parts[3],
                            "percent": parts[4],
                        }
        except Exception:
            pass
        return None

    def get_storage_volumes(self, serial: Optional[str] = None) -> List[StorageVolume]:
        """
        Discover all mounted storage volumes on the Android device:
        - Internal Storage (/storage/emulated/0)
        - MicroSD cards (/storage/XXXX-XXXX)
        - USB OTG drives (/storage/...)
        """
        volumes: List[StorageVolume] = []
        seen_paths = set()

        # 1. Primary Internal Storage (always present)
        volumes.append(
            StorageVolume(
                name="Internal Storage",
                path=ANDROID_INTERNAL_STORAGE,
                is_removable=False,
                is_primary=True,
                uuid="primary",
            )
        )
        seen_paths.add(ANDROID_INTERNAL_STORAGE)
        seen_paths.add("/storage/emulated")
        seen_paths.add("/storage/self")

        # 2. Check StorageManager via 'sm list-volumes public'
        try:
            code, stdout, _ = self.run_cmd(["shell", "sm list-volumes public"], serial=serial, timeout=3.0)
            if code == 0 and stdout:
                for line in stdout.splitlines():
                    # e.g. "public:179,1 mounted 1234-5678"
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "mounted":
                        uuid = parts[2]
                        v_path = f"/storage/{uuid}"
                        if v_path not in seen_paths:
                            seen_paths.add(v_path)
                            volumes.append(
                                StorageVolume(
                                    name=f"SD Card ({uuid})",
                                    path=v_path,
                                    is_removable=True,
                                    is_primary=False,
                                    uuid=uuid,
                                )
                            )
        except Exception:
            pass

        # 3. Check items in /storage directory
        try:
            code, stdout, _ = self.run_cmd(["shell", "ls -1 /storage"], serial=serial, timeout=3.0)
            if code == 0 and stdout:
                for item in stdout.splitlines():
                    item = item.strip()
                    if not item or item in ("emulated", "self", "knox", "container"):
                        continue
                    v_path = f"/storage/{item}"
                    if v_path not in seen_paths:
                        seen_paths.add(v_path)
                        is_uuid = bool(re.match(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$", item))
                        name = f"SD Card ({item})" if is_uuid else f"External Storage ({item})"
                        volumes.append(
                            StorageVolume(
                                name=name,
                                path=v_path,
                                is_removable=True,
                                is_primary=False,
                                uuid=item,
                            )
                        )
        except Exception:
            pass

        # 4. Check /proc/mounts fallback
        try:
            code, stdout, _ = self.run_cmd(["shell", "cat /proc/mounts"], serial=serial, timeout=3.0)
            if code == 0 and stdout:
                for line in stdout.splitlines():
                    if "/storage/" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            m = parts[1].strip()
                            if m.startswith("/storage/") and m not in ("/storage/emulated", "/storage/self"):
                                sub = m[len("/storage/"):].split("/")[0]
                                if sub and sub not in ("emulated", "self", "knox"):
                                    v_path = f"/storage/{sub}"
                                    if v_path not in seen_paths:
                                        seen_paths.add(v_path)
                                        name = f"SD Card ({sub})" if re.match(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$", sub) else f"External ({sub})"
                                        volumes.append(
                                            StorageVolume(
                                                name=name,
                                                path=v_path,
                                                is_removable=True,
                                                is_primary=False,
                                                uuid=sub,
                                            )
                                        )
        except Exception:
            pass

        # 5. Populate volume stats
        for vol in volumes:
            try:
                stats = self.get_storage_stats(vol.path, serial=serial)
                if stats:
                    vol.total_size = stats.get("size", "")
                    vol.free_size = stats.get("free", "")
            except Exception:
                pass

        return volumes

    def get_external_storage_path(self, serial: Optional[str] = None) -> Optional[str]:
        """Return the path of the first external SD card or USB volume, if any."""
        vols = self.get_storage_volumes(serial=serial)
        for v in vols:
            if v.is_removable:
                return v.path
        return None

    def get_device_ip(self, serial: Optional[str] = None) -> Optional[str]:
        """
        Attempt to auto-detect the connected Android device's Wi-Fi IPv4 address.
        Tries multiple standard shell methods across Android versions:
        1. Direct return if serial is already an IP address
        2. 'ip -f inet addr show wlan0' (and wlan1/wlan2/eth0)
        3. 'ip route' looking for src IP
        4. 'getprop dhcp.wlan0.ipaddress'
        5. 'ifconfig wlan0'
        """
        target = serial or self.selected_serial
        if target and re.match(r"^\d+\.\d+\.\d+\.\d+(?::\d+)?$", target):
            return target.split(":")[0]

        # 1. Interface IP address check
        for iface in ["wlan0", "wlan1", "wlan2", "eth0"]:
            try:
                code, stdout, _ = self.run_cmd(["shell", f"ip -f inet addr show {iface}"], serial=serial, timeout=4.0)
                if code == 0 and stdout:
                    for line in stdout.splitlines():
                        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if m:
                            ip = m.group(1)
                            if not ip.startswith("127.") and ip != "0.0.0.0":
                                return ip
            except Exception:
                pass

        # 2. IP route check (often has '... src 192.168.x.x')
        try:
            code, stdout, _ = self.run_cmd(["shell", "ip route"], serial=serial, timeout=4.0)
            if code == 0 and stdout:
                for line in stdout.splitlines():
                    if "wlan" in line or "default" in line:
                        m = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if m:
                            ip = m.group(1)
                            if not ip.startswith("127.") and ip != "0.0.0.0":
                                return ip
        except Exception:
            pass

        # 3. getprop DHCP system properties
        for prop in ["dhcp.wlan0.ipaddress", "dhcp.wlan1.ipaddress"]:
            try:
                code, stdout, _ = self.run_cmd(["shell", f"getprop {prop}"], serial=serial, timeout=3.0)
                if code == 0 and stdout:
                    ip = stdout.strip()
                    if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip) and not ip.startswith("127."):
                        return ip
            except Exception:
                pass

        # 4. ifconfig wlan0 fallback
        try:
            code, stdout, _ = self.run_cmd(["shell", "ifconfig wlan0"], serial=serial, timeout=4.0)
            if code == 0 and stdout:
                m = re.search(r"inet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)", stdout)
                if m:
                    ip = m.group(1)
                    if not ip.startswith("127.") and ip != "0.0.0.0":
                        return ip
        except Exception:
            pass

        return None

    def enable_tcpip(self, port: int = 5555, serial: Optional[str] = None) -> Tuple[bool, str]:
        """
        Switch ADB daemon on the device to listen on TCP/IP port (default 5555).
        Equivalent to: `adb tcpip 5555`.
        """
        code, stdout, stderr = self.run_cmd(["tcpip", str(port)], serial=serial, timeout=10.0)
        out = (stdout + "\n" + stderr).strip()
        if code == 0 or "restarting in tcp mode" in out.lower():
            return True, out or f"Restarting in TCP mode port: {port}"
        return False, out or f"Failed to enable TCP mode on port {port}"

    def connect_wireless(self, host: str, port: int = 5555) -> Tuple[bool, str]:
        """
        Connect to device over Wi-Fi: `adb connect <host>:<port>`.
        """
        clean_host = host.strip()
        if not clean_host:
            return False, "IP address cannot be empty"
        target = clean_host if ":" in clean_host else f"{clean_host}:{port}"
        code, stdout, stderr = self.run_cmd(["connect", target], serial=None, timeout=15.0)
        out = (stdout + "\n" + stderr).strip()
        out_lower = out.lower()
        if "connected to" in out_lower or "already connected to" in out_lower:
            return True, out
        return False, out or f"Failed to connect to {target}"

    def disconnect_wireless(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Disconnect wireless device: `adb disconnect [<target>]`.
        If target is None, disconnects all active network devices.
        """
        cmd = ["disconnect"]
        if target and target.strip():
            cmd.append(target.strip())
        code, stdout, stderr = self.run_cmd(cmd, serial=None, timeout=10.0)
        out = (stdout + "\n" + stderr).strip()
        return code == 0, out or "Disconnected"

    def pair_wireless(self, host_port: str, pairing_code: str) -> Tuple[bool, str]:
        """
        Pair device using Android 11+ wireless debugging: `adb pair <host:port> <code>`.
        """
        clean_host = host_port.strip()
        clean_code = pairing_code.strip()
        if not clean_host or not clean_code:
            return False, "Host:port and pairing code are required"
        code, stdout, stderr = self.run_cmd(["pair", clean_host, clean_code], serial=None, timeout=15.0)
        out = (stdout + "\n" + stderr).strip()
        if "successfully paired" in out.lower():
            return True, out
        return False, out or f"Pairing failed: {out}"
