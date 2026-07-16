"""Fail-closed filesystem and capacity boundary for Product Canvas assets."""
from __future__ import annotations

import os
import hashlib
import shutil
import stat
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator
from uuid import UUID

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

from config import (
    CANVAS_DATA_DIR,
    CANVAS_MIN_FREE_BYTES,
    CANVAS_PROJECT_QUOTA_BYTES,
    CANVAS_TOTAL_QUOTA_BYTES,
)


PROJECT_SUBDIRECTORIES = (
    "source",
    "working",
    "preview",
    "cutout",
    "generated",
    "composed",
    "exports",
    "tmp",
)
CANVAS_MAX_TREE_ENTRIES = 4096

# Every operation that can reserve or allocate Canvas bytes shares this
# process-local lock. SQLite serializes durable reservations, while this lock
# closes the scan-to-file-write window used by uploads and derived assets.
CANVAS_ALLOCATION_LOCK = threading.RLock()

ASSET_TYPE_DIRECTORIES = {
    "source": "source",
    "working": "working",
    "preview": "preview",
    "cutout": "cutout",
    "generated_background": "generated",
    "composed": "composed",
    "export": "exports",
}

_SOURCE_EXTENSIONS_BY_MIME = {
    "image/jpeg": {".jpeg", ".jpg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}
_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

if os.name == "nt":
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _DELETE = 0x00010000
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_ADD_FILE = 0x0002
    _FILE_DELETE_CHILD = 0x0040
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_DISPOSITION_INFO_CLASS = 4
    _FILE_ID_BOTH_DIRECTORY_INFO_CLASS = 10
    _FILE_ID_BOTH_DIRECTORY_RESTART_INFO_CLASS = 11
    _FILE_DISPOSITION_INFO_EX_CLASS = 21
    _FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
    _FILE_ID_INFO_CLASS = 18
    _FILE_BASIC_INFO_CLASS = 0
    _FILE_STANDARD_INFO_CLASS = 1
    _FILE_STREAM_INFO_CLASS = 7
    _ERROR_NO_MORE_FILES = 18
    _ERROR_HANDLE_EOF = 38
    _OBJ_CASE_INSENSITIVE = 0x00000040
    _FILE_OPEN = 0x00000001
    _FILE_CREATE = 0x00000002
    _FILE_OPEN_IF = 0x00000003
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_NON_DIRECTORY_FILE = 0x00000040
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _SYNCHRONIZE = 0x00100000
    _FILE_DISPOSITION_DELETE = 0x00000001
    _FILE_DISPOSITION_POSIX_SEMANTICS = 0x00000002
    _FILE_DISPOSITION_IGNORE_READONLY_ATTRIBUTE = 0x00000010
    _FILE_RENAME_INFORMATION_CLASS = 10
    _FILE_BEGIN = 0
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class _FileDispositionInfo(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOLEAN)]

    class _FileRenameInformation(ctypes.Structure):
        _fields_ = [
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.ULONG),
            ("FileName", wintypes.WCHAR * 1),
        ]

    class _UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        ]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(_UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", wintypes.LPVOID),
            ("SecurityQualityOfService", wintypes.LPVOID),
        ]

    class _IoStatusValue(ctypes.Union):
        _fields_ = [
            ("Status", wintypes.LONG),
            ("Pointer", wintypes.LPVOID),
        ]

    class _IoStatusBlock(ctypes.Structure):
        _anonymous_ = ("Value",)
        _fields_ = [
            ("Value", _IoStatusValue),
            ("Information", ctypes.c_size_t),
        ]

    class _FileIdBothDirectoryInfo(ctypes.Structure):
        _fields_ = [
            ("NextEntryOffset", wintypes.DWORD),
            ("FileIndex", wintypes.DWORD),
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("EndOfFile", ctypes.c_longlong),
            ("AllocationSize", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
            ("FileNameLength", wintypes.DWORD),
            ("EaSize", wintypes.DWORD),
            ("ShortNameLength", ctypes.c_byte),
            ("ShortName", wintypes.WCHAR * 12),
            ("FileId", ctypes.c_longlong),
            ("FileName", wintypes.WCHAR * 1),
        ]

    class _FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    class _FileId128(ctypes.Structure):
        _fields_ = [("Identifier", ctypes.c_ubyte * 16)]

    class _FileIdInfo(ctypes.Structure):
        _fields_ = [
            ("VolumeSerialNumber", ctypes.c_ulonglong),
            ("FileId", _FileId128),
        ]

    class _FileBasicInfo(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
        ]

    class _FileStandardInfo(ctypes.Structure):
        _fields_ = [
            ("AllocationSize", ctypes.c_longlong),
            ("EndOfFile", ctypes.c_longlong),
            ("NumberOfLinks", wintypes.DWORD),
            ("DeletePending", wintypes.BOOLEAN),
            ("Directory", wintypes.BOOLEAN),
        ]

    class _FileStreamInfo(ctypes.Structure):
        _fields_ = [
            ("NextEntryOffset", wintypes.DWORD),
            ("StreamNameLength", wintypes.DWORD),
            ("StreamSize", ctypes.c_longlong),
            ("StreamAllocationSize", ctypes.c_longlong),
            ("StreamName", wintypes.WCHAR * 1),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _CreateFileW.restype = wintypes.HANDLE
    _GetFileInformationByHandle = _kernel32.GetFileInformationByHandle
    _GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    _GetFileInformationByHandle.restype = wintypes.BOOL
    _SetFileInformationByHandle = _kernel32.SetFileInformationByHandle
    _SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _SetFileInformationByHandle.restype = wintypes.BOOL
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL
    _GetFileInformationByHandleEx = _kernel32.GetFileInformationByHandleEx
    _GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _GetFileInformationByHandleEx.restype = wintypes.BOOL
    _ntdll = ctypes.WinDLL("ntdll")
    _NtCreateFile = _ntdll.NtCreateFile
    _NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    ]
    _NtCreateFile.restype = wintypes.LONG
    _NtSetInformationFile = _ntdll.NtSetInformationFile
    _NtSetInformationFile.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        ctypes.c_int,
    ]
    _NtSetInformationFile.restype = wintypes.LONG
    _RtlNtStatusToDosError = _ntdll.RtlNtStatusToDosError
    _RtlNtStatusToDosError.argtypes = [wintypes.LONG]
    _RtlNtStatusToDosError.restype = wintypes.ULONG
    _WriteFile = _kernel32.WriteFile
    _WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _WriteFile.restype = wintypes.BOOL
    _ReadFile = _kernel32.ReadFile
    _ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _ReadFile.restype = wintypes.BOOL
    _FlushFileBuffers = _kernel32.FlushFileBuffers
    _FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _FlushFileBuffers.restype = wintypes.BOOL
    _SetFilePointerEx = _kernel32.SetFilePointerEx
    _SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    ]
    _SetFilePointerEx.restype = wintypes.BOOL
    _SetEndOfFile = _kernel32.SetEndOfFile
    _SetEndOfFile.argtypes = [wintypes.HANDLE]
    _SetEndOfFile.restype = wintypes.BOOL

    if ctypes.sizeof(ctypes.c_void_p) != 8:  # pragma: no cover - deployment guard
        raise RuntimeError("Canvas secure storage requires 64-bit Windows")
    _expected_abis = (
        ("FILE_DISPOSITION_INFO", ctypes.sizeof(_FileDispositionInfo), 1),
        ("UNICODE_STRING", ctypes.sizeof(_UnicodeString), 16),
        ("OBJECT_ATTRIBUTES", ctypes.sizeof(_ObjectAttributes), 48),
        ("IO_STATUS_BLOCK", ctypes.sizeof(_IoStatusBlock), 16),
        ("FILE_ID_BOTH_DIR_INFO", _FileIdBothDirectoryInfo.FileName.offset, 104),
        ("FILE_RENAME_INFO.RootDirectory", _FileRenameInformation.RootDirectory.offset, 8),
        ("FILE_RENAME_INFO.FileNameLength", _FileRenameInformation.FileNameLength.offset, 16),
        ("FILE_RENAME_INFO.FileName", _FileRenameInformation.FileName.offset, 20),
    )
    for _abi_name, _actual_size, _expected_size in _expected_abis:
        if _actual_size != _expected_size:  # pragma: no cover - ABI guard
            raise RuntimeError(f"{_abi_name} ABI mismatch")


class CanvasStorageError(ValueError):
    """Stable fail-closed storage error for later HTTP adapters."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _reject(code: str, message: str) -> None:
    raise CanvasStorageError(code, message)


def _raise_io_failure(exc: OSError) -> None:
    raise CanvasStorageError(
        "canvas_storage_io_failed",
        "canvas storage I/O failed",
    ) from exc


@dataclass
class _PinnedEntry:
    """One no-follow filesystem object held open for an entire operation phase."""

    path: Path
    handle: int
    identity: tuple[object, object]
    legacy_file_id: int
    attributes: int
    change_time: int
    byte_count: int
    is_directory: bool
    parent: "_PinnedEntry | None" = None
    name: str | None = None
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        try:
            if os.name == "nt":
                if not _CloseHandle(self.handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:  # pragma: no cover - exercised on POSIX deployments
                os.close(self.handle)
        except OSError as exc:
            _raise_io_failure(exc)
        self.closed = True


def _validate_child_name(name: object) -> str:
    if (
        not isinstance(name, str)
        or name in {"", ".", ".."}
        or "\x00" in name
        or "/" in name
        or "\\" in name
    ):
        _reject("canvas_storage_unsafe_entry", "canvas tree contains an unsafe name")
    return name


if os.name == "nt":

    def _windows_query(
        handle: int,
        info_class: int,
        info: ctypes.Structure,
    ) -> None:
        if not _GetFileInformationByHandleEx(
            handle,
            info_class,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            raise ctypes.WinError(ctypes.get_last_error())


    def _windows_streams(handle: int, *, is_directory: bool, byte_count: int) -> None:
        buffer = ctypes.create_string_buffer(64 * 1024)
        if not _GetFileInformationByHandleEx(
            handle,
            _FILE_STREAM_INFO_CLASS,
            buffer,
            ctypes.sizeof(buffer),
        ):
            error = ctypes.get_last_error()
            if is_directory and error == _ERROR_HANDLE_EOF:
                return
            raise ctypes.WinError(error)

        offset = 0
        streams: list[tuple[str, int]] = []
        name_offset = _FileStreamInfo.StreamName.offset
        buffer_size = ctypes.sizeof(buffer)
        while True:
            if offset + name_offset > buffer_size:
                _reject("canvas_storage_unsafe_entry", "canvas stream metadata is invalid")
            info = _FileStreamInfo.from_buffer(buffer, offset)
            name_length = int(info.StreamNameLength)
            if name_length % 2 or offset + name_offset + name_length > buffer_size:
                _reject("canvas_storage_unsafe_entry", "canvas stream metadata is invalid")
            name = ctypes.wstring_at(
                ctypes.addressof(buffer) + offset + name_offset,
                name_length // 2,
            )
            streams.append((name, int(info.StreamSize)))
            next_offset = int(info.NextEntryOffset)
            if next_offset == 0:
                break
            if next_offset < name_offset or next_offset % 8 or offset + next_offset >= buffer_size:
                _reject("canvas_storage_unsafe_entry", "canvas stream metadata is invalid")
            offset += next_offset

        if is_directory:
            _reject("canvas_storage_unsafe_entry", "canvas directory has a data stream")
        if streams != [("::$DATA", byte_count)]:
            _reject("canvas_storage_unsafe_entry", "canvas file has an alternate data stream")


    def _windows_metadata(handle: int, *, expected_kind: str) -> tuple[
        tuple[int, bytes], int, int, int, int, bool
    ]:
        tag = _FileAttributeTagInfo()
        file_id = _FileIdInfo()
        basic = _FileBasicInfo()
        standard = _FileStandardInfo()
        try:
            _windows_query(handle, _FILE_ATTRIBUTE_TAG_INFO_CLASS, tag)
            _windows_query(handle, _FILE_ID_INFO_CLASS, file_id)
            _windows_query(handle, _FILE_BASIC_INFO_CLASS, basic)
            _windows_query(handle, _FILE_STANDARD_INFO_CLASS, standard)
        except OSError as exc:
            _raise_io_failure(exc)
        attributes = int(tag.FileAttributes)
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            _reject("canvas_storage_reparse_point", "canvas tree contains a reparse point")
        is_directory = bool(standard.Directory)
        if expected_kind == "directory" and not is_directory:
            _reject("canvas_storage_unsafe_entry", "canvas entry is not a directory")
        if expected_kind == "file" and is_directory:
            _reject("canvas_storage_unsafe_entry", "canvas entry is not a regular file")
        byte_count = int(standard.EndOfFile)
        if byte_count < 0:
            _reject("canvas_storage_unsafe_entry", "canvas entry has an invalid size")
        try:
            _windows_streams(handle, is_directory=is_directory, byte_count=byte_count)
        except CanvasStorageError:
            raise
        except OSError as exc:
            _raise_io_failure(exc)
        identifier = bytes(file_id.FileId.Identifier)
        legacy_file_id = int.from_bytes(identifier[:8], "little")
        return (
            (int(file_id.VolumeSerialNumber), identifier),
            legacy_file_id,
            attributes,
            int(basic.ChangeTime),
            byte_count,
            is_directory,
        )


    def _windows_open_absolute(
        path: Path,
        *,
        kind: str,
        delete: bool,
        writable: bool,
    ) -> int:
        desired = _SYNCHRONIZE | _FILE_READ_ATTRIBUTES
        desired |= _FILE_LIST_DIRECTORY if kind == "directory" else _GENERIC_READ
        if writable:
            desired |= _GENERIC_WRITE
            if kind == "directory":
                desired |= _FILE_ADD_FILE | _FILE_DELETE_CHILD
        if delete:
            desired |= _DELETE
        flags = _FILE_FLAG_OPEN_REPARSE_POINT
        if kind == "directory":
            flags |= _FILE_FLAG_BACKUP_SEMANTICS
        handle = _CreateFileW(
            str(path),
            desired,
            _FILE_SHARE_READ | (_FILE_SHARE_WRITE if kind == "directory" and writable else 0),
            None,
            _OPEN_EXISTING,
            flags,
            None,
        )
        if handle in (None, _INVALID_HANDLE_VALUE):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)


    def _windows_open_relative(
        parent: _PinnedEntry,
        name: str,
        *,
        kind: str,
        delete: bool,
        create: bool,
        writable: bool,
        share_all: bool,
    ) -> int:
        encoded_name = name.encode("utf-16-le")
        name_buffer = ctypes.create_unicode_buffer(name)
        unicode_name = _UnicodeString(
            Length=len(encoded_name),
            MaximumLength=len(encoded_name) + 2,
            Buffer=ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        object_attributes = _ObjectAttributes(
            Length=ctypes.sizeof(_ObjectAttributes),
            RootDirectory=parent.handle,
            ObjectName=ctypes.pointer(unicode_name),
            Attributes=_OBJ_CASE_INSENSITIVE,
            SecurityDescriptor=None,
            SecurityQualityOfService=None,
        )
        io_status = _IoStatusBlock()
        output_handle = wintypes.HANDLE()
        desired = _SYNCHRONIZE | _FILE_READ_ATTRIBUTES
        desired |= _FILE_LIST_DIRECTORY if kind == "directory" else _GENERIC_READ
        if writable:
            desired |= _GENERIC_WRITE
            if kind == "directory":
                desired |= _FILE_ADD_FILE | _FILE_DELETE_CHILD
        if delete:
            desired |= _DELETE
        options = (
            _FILE_SYNCHRONOUS_IO_NONALERT
            | _FILE_OPEN_REPARSE_POINT
            | (_FILE_DIRECTORY_FILE if kind == "directory" else _FILE_NON_DIRECTORY_FILE)
        )
        share_access = (
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
            if share_all
            else _FILE_SHARE_READ
            | (_FILE_SHARE_WRITE if kind == "directory" and writable else 0)
        )
        status = _NtCreateFile(
            ctypes.byref(output_handle),
            desired,
            ctypes.byref(object_attributes),
            ctypes.byref(io_status),
            None,
            0,
            share_access,
            (
                _FILE_OPEN_IF
                if create and kind == "directory"
                else _FILE_CREATE
                if create
                else _FILE_OPEN
            ),
            options,
            None,
            0,
        )
        if status < 0:
            raise ctypes.WinError(int(_RtlNtStatusToDosError(status)))
        return int(output_handle.value)


def _open_pinned_entry_once(
    path: Path,
    *,
    kind: str,
    parent: _PinnedEntry | None = None,
    name: str | None = None,
    delete: bool = False,
    create: bool = False,
    writable: bool = False,
    share_all: bool = False,
    expected_file_id: int | None = None,
) -> _PinnedEntry:
    if kind not in {"directory", "file"}:
        raise AssertionError("invalid pinned entry kind")
    if parent is not None:
        name = _validate_child_name(name)
        if not parent.is_directory or parent.closed:
            _reject("canvas_storage_unsafe_entry", "canvas parent handle is invalid")
    handle: int | None = None
    try:
        if os.name == "nt":
            handle = (
                _windows_open_relative(
                    parent,
                    name,
                    kind=kind,
                    delete=delete,
                    create=create,
                    writable=writable,
                    share_all=share_all,
                )
                if parent is not None
                else _windows_open_absolute(
                    path,
                    kind=kind,
                    delete=delete,
                    writable=writable,
                )
            )
            (
                identity,
                legacy_file_id,
                attributes,
                change_time,
                byte_count,
                is_directory,
            ) = _windows_metadata(handle, expected_kind=kind)
        else:  # pragma: no cover - exercised on POSIX deployments
            flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
            if kind == "directory":
                flags |= getattr(os, "O_DIRECTORY", 0)
            if create and kind == "directory":
                if parent is None:
                    raise AssertionError("relative directory create requires a parent")
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent.handle)
                except FileExistsError:
                    pass
            elif create:
                if parent is None:
                    raise AssertionError("relative file create requires a parent")
                flags |= os.O_CREAT | os.O_EXCL
            handle = (
                os.open(name, flags, dir_fd=parent.handle)
                if parent is not None
                else os.open(path, flags)
            )
            handle_stat = os.fstat(handle)
            is_directory = stat.S_ISDIR(handle_stat.st_mode)
            if kind == "directory" and not is_directory:
                _reject("canvas_storage_unsafe_entry", "canvas entry is not a directory")
            if kind == "file" and not stat.S_ISREG(handle_stat.st_mode):
                _reject("canvas_storage_unsafe_entry", "canvas entry is not a regular file")
            identity = (handle_stat.st_dev, handle_stat.st_ino)
            legacy_file_id = handle_stat.st_ino
            attributes = 0
            change_time = handle_stat.st_ctime_ns
            byte_count = handle_stat.st_size
        if expected_file_id is not None and legacy_file_id != expected_file_id:
            _reject("canvas_storage_unsafe_entry", "canvas entry changed during traversal")
        return _PinnedEntry(
            path=path,
            handle=handle,
            identity=identity,
            legacy_file_id=legacy_file_id,
            attributes=attributes,
            change_time=change_time,
            byte_count=byte_count,
            is_directory=is_directory,
            parent=parent,
            name=name,
        )
    except CanvasStorageError:
        if handle is not None:
            if os.name == "nt":
                _CloseHandle(handle)
            else:  # pragma: no cover - exercised on POSIX deployments
                os.close(handle)
        raise
    except OSError as exc:
        if handle is not None:
            if os.name == "nt":
                _CloseHandle(handle)
            else:  # pragma: no cover - exercised on POSIX deployments
                os.close(handle)
        if create and (
            isinstance(exc, FileExistsError)
            or getattr(exc, "winerror", None) in {80, 183}
        ):
            _reject("canvas_storage_collision", "canvas storage name already exists")
        _raise_io_failure(exc)


def _is_transient_windows_sharing_error(exc: CanvasStorageError) -> bool:
    """Only retry a short-lived Windows handle-sharing conflict."""

    cause: BaseException | None = exc.__cause__
    while cause is not None:
        if isinstance(cause, PermissionError) and getattr(cause, "winerror", None) in {32, 33}:
            return True
        cause = cause.__cause__
    return False


def _open_pinned_entry(
    path: Path,
    *,
    kind: str,
    parent: _PinnedEntry | None = None,
    name: str | None = None,
    delete: bool = False,
    create: bool = False,
    writable: bool = False,
    share_all: bool = False,
    expected_file_id: int | None = None,
) -> _PinnedEntry:
    """Open a pinned entry, tolerating a bounded Windows share-release race."""

    # Browser-backed generation can briefly overlap a worker's verified-result
    # handoff with a preview/read reopen on Windows. Keep the retry strictly
    # limited to share-release errors, but allow the handle close to propagate
    # across a normal scheduler slice before failing a durable compose attempt.
    for attempt in range(20):
        try:
            return _open_pinned_entry_once(
                path,
                kind=kind,
                parent=parent,
                name=name,
                delete=delete,
                create=create,
                writable=writable,
                share_all=share_all,
                expected_file_id=expected_file_id,
            )
        except CanvasStorageError as exc:
            if os.name != "nt" or not _is_transient_windows_sharing_error(exc) or attempt == 19:
                raise
            time.sleep(0.01 * (attempt + 1))
    raise AssertionError("unreachable pinned-entry retry loop")


def _open_pinned_directory(
    path: Path,
    *,
    parent: _PinnedEntry | None = None,
    name: str | None = None,
    delete: bool = False,
    create: bool = False,
    writable: bool = False,
    expected_file_id: int | None = None,
) -> _PinnedEntry:
    return _open_pinned_entry(
        path,
        kind="directory",
        parent=parent,
        name=name,
        delete=delete,
        create=create,
        writable=writable,
        expected_file_id=expected_file_id,
    )


def _open_pinned_file(
    path: Path,
    *,
    parent: _PinnedEntry,
    name: str,
    delete: bool = False,
    create: bool = False,
    writable: bool = False,
    share_all: bool = False,
    expected_file_id: int | None = None,
) -> _PinnedEntry:
    return _open_pinned_entry(
        path,
        kind="file",
        parent=parent,
        name=name,
        delete=delete,
        create=create,
        writable=writable,
        share_all=share_all,
        expected_file_id=expected_file_id,
    )


def _create_pinned_file(parent: _PinnedEntry, name: str) -> _PinnedEntry:
    """Create one new regular file relative to a pinned parent directory."""
    name = _validate_child_name(name)
    return _open_pinned_file(
        parent.path / name,
        parent=parent,
        name=name,
        delete=True,
        create=True,
        writable=True,
    )


def _open_published_file_verifier(
    parent: _PinnedEntry,
    name: str,
) -> _PinnedEntry:
    """Reopen a published name while its writer/deleter handle remains active."""
    name = _validate_child_name(name)
    return _open_pinned_file(
        parent.path / name,
        parent=parent,
        name=name,
        share_all=True,
    )


def _refresh_pinned_file(pin: _PinnedEntry) -> None:
    if pin.closed or pin.is_directory:
        _reject("canvas_storage_unsafe_entry", "canvas file handle is invalid")
    identity, legacy_file_id, attributes, change_time, byte_count, is_directory = (
        _current_entry_metadata(pin)
    )
    if identity != pin.identity or legacy_file_id != pin.legacy_file_id or is_directory:
        _reject("canvas_storage_unsafe_entry", "canvas file identity changed")
    pin.attributes = attributes
    pin.change_time = change_time
    pin.byte_count = byte_count


def _seek_pinned_file_start(pin: _PinnedEntry) -> None:
    try:
        if os.name == "nt":
            if not _SetFilePointerEx(pin.handle, 0, None, _FILE_BEGIN):
                raise ctypes.WinError(ctypes.get_last_error())
        else:  # pragma: no cover - exercised on POSIX deployments
            os.lseek(pin.handle, 0, os.SEEK_SET)
    except OSError as exc:
        _raise_io_failure(exc)


def _write_pinned_file(pin: _PinnedEntry, data: bytes, *, truncate: bool = True) -> None:
    """Write bytes through the already pinned file handle without reopening by path."""
    if type(data) is not bytes:
        _reject("canvas_storage_unsafe_entry", "canvas file data must be bytes")
    _seek_pinned_file_start(pin)
    try:
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            chunk = view[offset : offset + 1024 * 1024]
            if os.name == "nt":
                buffer = ctypes.create_string_buffer(bytes(chunk))
                written = wintypes.DWORD()
                if not _WriteFile(
                    pin.handle,
                    buffer,
                    len(chunk),
                    ctypes.byref(written),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if written.value <= 0:
                    raise OSError("canvas native write made no progress")
                offset += int(written.value)
            else:  # pragma: no cover - exercised on POSIX deployments
                written_count = os.write(pin.handle, chunk)
                if written_count <= 0:
                    raise OSError("canvas native write made no progress")
                offset += written_count
        if truncate:
            if os.name == "nt":
                if not _SetEndOfFile(pin.handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:  # pragma: no cover - exercised on POSIX deployments
                os.ftruncate(pin.handle, len(data))
    except OSError as exc:
        _raise_io_failure(exc)
    _refresh_pinned_file(pin)


def _flush_pinned_file(pin: _PinnedEntry) -> None:
    try:
        if os.name == "nt":
            if not _FlushFileBuffers(pin.handle):
                raise ctypes.WinError(ctypes.get_last_error())
        else:  # pragma: no cover - exercised on POSIX deployments
            os.fsync(pin.handle)
    except OSError as exc:
        _raise_io_failure(exc)
    _refresh_pinned_file(pin)


def _pinned_file_sha256(pin: _PinnedEntry) -> tuple[str, int]:
    """Read and hash the complete file through its already verified native handle."""
    _seek_pinned_file_start(pin)
    digest = hashlib.sha256()
    byte_count = 0
    try:
        while True:
            if os.name == "nt":
                buffer = ctypes.create_string_buffer(1024 * 1024)
                read_count = wintypes.DWORD()
                if not _ReadFile(
                    pin.handle,
                    buffer,
                    ctypes.sizeof(buffer),
                    ctypes.byref(read_count),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if read_count.value == 0:
                    break
                chunk = buffer.raw[: read_count.value]
            else:  # pragma: no cover - exercised on POSIX deployments
                chunk = os.read(pin.handle, 1024 * 1024)
                if not chunk:
                    break
            digest.update(chunk)
            byte_count += len(chunk)
    except OSError as exc:
        _raise_io_failure(exc)
    _refresh_pinned_file(pin)
    if byte_count != pin.byte_count:
        _reject("canvas_storage_unsafe_entry", "canvas file changed while hashing")
    return digest.hexdigest(), byte_count


def _pinned_file_bytes(pin: _PinnedEntry) -> bytes:
    """Read complete bytes through one pin while bounding growth to its opened size."""
    expected_byte_count = pin.byte_count
    _seek_pinned_file_start(pin)
    chunks: list[bytes] = []
    byte_count = 0
    try:
        while True:
            if os.name == "nt":
                buffer = ctypes.create_string_buffer(1024 * 1024)
                read_count = wintypes.DWORD()
                if not _ReadFile(
                    pin.handle,
                    buffer,
                    ctypes.sizeof(buffer),
                    ctypes.byref(read_count),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if read_count.value == 0:
                    break
                chunk = buffer.raw[: read_count.value]
            else:  # pragma: no cover - exercised on POSIX deployments
                chunk = os.read(pin.handle, 1024 * 1024)
                if not chunk:
                    break
            chunks.append(chunk)
            byte_count += len(chunk)
            if byte_count > expected_byte_count:
                _reject("canvas_storage_unsafe_entry", "canvas file changed while reading")
    except CanvasStorageError:
        raise
    except OSError as exc:
        _raise_io_failure(exc)
    _refresh_pinned_file(pin)
    if byte_count != expected_byte_count or byte_count != pin.byte_count:
        _reject("canvas_storage_unsafe_entry", "canvas file changed while reading")
    return b"".join(chunks)


def _rename_pinned_file_no_replace(
    pin: _PinnedEntry,
    destination_parent: _PinnedEntry,
    name: str,
) -> None:
    """Publish a pinned file under a new parent-relative name without replacement."""
    name = _validate_child_name(name)
    if pin.closed or pin.is_directory or pin.parent is None or pin.name is None:
        _reject("canvas_storage_unsafe_entry", "canvas publish handle is invalid")
    if destination_parent.closed or not destination_parent.is_directory:
        _reject("canvas_storage_unsafe_entry", "canvas publish directory is invalid")
    try:
        if os.name == "nt":
            encoded_name = name.encode("utf-16-le")
            file_name_offset = _FileRenameInformation.FileName.offset
            buffer_size = max(24, file_name_offset + len(encoded_name))
            buffer = ctypes.create_string_buffer(buffer_size)
            wintypes.BOOLEAN.from_buffer(
                buffer,
                _FileRenameInformation.ReplaceIfExists.offset,
            ).value = 0
            wintypes.HANDLE.from_buffer(
                buffer,
                _FileRenameInformation.RootDirectory.offset,
            ).value = destination_parent.handle
            wintypes.ULONG.from_buffer(
                buffer,
                _FileRenameInformation.FileNameLength.offset,
            ).value = len(encoded_name)
            ctypes.memmove(
                ctypes.addressof(buffer) + file_name_offset,
                encoded_name,
                len(encoded_name),
            )
            io_status = _IoStatusBlock()
            for attempt in range(20):
                status = _NtSetInformationFile(
                    pin.handle,
                    ctypes.byref(io_status),
                    buffer,
                    buffer_size,
                    _FILE_RENAME_INFORMATION_CLASS,
                )
                if status >= 0:
                    break
                error = int(_RtlNtStatusToDosError(status))
                if error in {80, 183}:
                    _reject("canvas_storage_collision", "canvas publish name already exists")
                if error not in {32, 33} or attempt == 19:
                    raise ctypes.WinError(error)
                # Defender and preview readers can briefly retain a compatible
                # file handle after the write is flushed. Keep the publish
                # no-replace contract, but allow that handle to drain before a
                # durable Provider result is classified as unknown.
                time.sleep(0.01 * (attempt + 1))
        else:  # pragma: no cover - exercised on POSIX deployments
            os.link(
                pin.name,
                name,
                src_dir_fd=pin.parent.handle,
                dst_dir_fd=destination_parent.handle,
                follow_symlinks=False,
            )
            os.unlink(pin.name, dir_fd=pin.parent.handle)
    except CanvasStorageError:
        raise
    except FileExistsError:
        _reject("canvas_storage_collision", "canvas publish name already exists")
    except OSError as exc:
        _raise_io_failure(exc)
    pin.path = destination_parent.path / name
    pin.parent = destination_parent
    pin.name = name


@contextmanager
def _pin_directory_chain(
    path: Path,
    *,
    delete_final: bool = False,
    writable_final: bool = False,
) -> Iterator[list[_PinnedEntry]]:
    absolute = Path(os.path.abspath(path))
    anchor = Path(absolute.anchor)
    if not absolute.anchor:
        _reject("canvas_storage_path_invalid", "canvas path must be absolute")
    pins: list[_PinnedEntry] = []
    try:
        current = anchor
        pin = _open_pinned_directory(current)
        pins.append(pin)
        relative_parts = absolute.relative_to(anchor).parts
        for index, name in enumerate(relative_parts):
            current = current / name
            pin = _open_pinned_directory(
                current,
                parent=pin,
                name=name,
                delete=delete_final and index == len(relative_parts) - 1,
                writable=writable_final and index == len(relative_parts) - 1,
            )
            pins.append(pin)
        yield pins
    finally:
        active_exception = sys.exc_info()[0] is not None
        first_close_error: CanvasStorageError | None = None
        for pin in reversed(pins):
            try:
                pin.close()
            except CanvasStorageError as exc:
                if first_close_error is None:
                    first_close_error = exc
        if first_close_error is not None and not active_exception:
            raise first_close_error


@contextmanager
def _ensure_directory_chain(path: Path) -> Iterator[list[_PinnedEntry]]:
    """Open-or-create an absolute directory chain relative to pinned parents."""
    absolute = Path(os.path.abspath(path))
    anchor = Path(absolute.anchor)
    if not absolute.anchor:
        _reject("canvas_storage_path_invalid", "canvas path must be absolute")
    pins: list[_PinnedEntry] = []
    try:
        current = anchor
        pin = _open_pinned_directory(current)
        pins.append(pin)
        for name in absolute.relative_to(anchor).parts:
            current = current / name
            pin = _open_pinned_directory(
                current,
                parent=pin,
                name=name,
                create=True,
            )
            pins.append(pin)
        yield pins
    finally:
        active_exception = sys.exc_info()[0] is not None
        first_close_error: CanvasStorageError | None = None
        for pin in reversed(pins):
            try:
                pin.close()
            except CanvasStorageError as exc:
                if first_close_error is None:
                    first_close_error = exc
        if first_close_error is not None and not active_exception:
            raise first_close_error


@dataclass(frozen=True)
class _DirectoryRecord:
    name: str
    file_id: int
    attributes: int
    byte_count: int
    is_directory: bool


@dataclass
class _PinnedTree:
    pin: _PinnedEntry
    records: dict[str, _DirectoryRecord]
    children: dict[str, "_PinnedTree"]


@dataclass
class _EntryBudget:
    limit: int
    count: int = 0

    def consume(self) -> None:
        if self.count >= self.limit:
            _reject(
                "canvas_storage_entry_limit_exceeded",
                "canvas tree contains too many entries",
            )
        self.count += 1


if os.name == "nt":

    def _windows_directory_records(
        pin: _PinnedEntry,
        *,
        max_entries: int | None,
    ) -> list[_DirectoryRecord]:
        records: list[_DirectoryRecord] = []
        first = True
        buffer_size = 64 * 1024
        name_offset = _FileIdBothDirectoryInfo.FileName.offset
        while True:
            buffer = ctypes.create_string_buffer(buffer_size)
            info_class = (
                _FILE_ID_BOTH_DIRECTORY_RESTART_INFO_CLASS
                if first
                else _FILE_ID_BOTH_DIRECTORY_INFO_CLASS
            )
            first = False
            if not _GetFileInformationByHandleEx(
                pin.handle,
                info_class,
                buffer,
                buffer_size,
            ):
                error = ctypes.get_last_error()
                if error == _ERROR_NO_MORE_FILES:
                    break
                raise ctypes.WinError(error)
            offset = 0
            while True:
                if offset + name_offset > buffer_size:
                    _reject(
                        "canvas_storage_unsafe_entry",
                        "canvas directory metadata is invalid",
                    )
                info = _FileIdBothDirectoryInfo.from_buffer(buffer, offset)
                name_length = int(info.FileNameLength)
                if name_length % 2 or offset + name_offset + name_length > buffer_size:
                    _reject(
                        "canvas_storage_unsafe_entry",
                        "canvas directory metadata is invalid",
                    )
                name = ctypes.wstring_at(
                    ctypes.addressof(buffer) + offset + name_offset,
                    name_length // 2,
                )
                if name not in {".", ".."}:
                    _validate_child_name(name)
                    if max_entries is not None and len(records) >= max_entries:
                        _reject(
                            "canvas_storage_entry_limit_exceeded",
                            "canvas tree contains too many entries",
                        )
                    attributes = int(info.FileAttributes)
                    records.append(
                        _DirectoryRecord(
                            name=name,
                            file_id=int(info.FileId) & ((1 << 64) - 1),
                            attributes=attributes,
                            byte_count=int(info.EndOfFile),
                            is_directory=bool(attributes & _FILE_ATTRIBUTE_DIRECTORY),
                        )
                    )
                next_offset = int(info.NextEntryOffset)
                if next_offset == 0:
                    break
                if (
                    next_offset < name_offset
                    or next_offset % 8
                    or offset + next_offset >= buffer_size
                ):
                    _reject(
                        "canvas_storage_unsafe_entry",
                        "canvas directory metadata is invalid",
                    )
                offset += next_offset
        return records


def _directory_records(
    pin: _PinnedEntry,
    *,
    max_entries: int | None = None,
) -> list[_DirectoryRecord]:
    if pin.closed or not pin.is_directory:
        _reject("canvas_storage_unsafe_entry", "canvas directory handle is invalid")
    if max_entries is not None and max_entries < 0:
        raise AssertionError("directory record limit must be non-negative")
    try:
        if os.name == "nt":
            records = _windows_directory_records(pin, max_entries=max_entries)
        else:  # pragma: no cover - exercised on POSIX deployments
            records = []
            with os.scandir(pin.handle) as entries:
                for entry in entries:
                    name = _validate_child_name(entry.name)
                    if max_entries is not None and len(records) >= max_entries:
                        _reject(
                            "canvas_storage_entry_limit_exceeded",
                            "canvas tree contains too many entries",
                        )
                    entry_stat = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(entry_stat.st_mode):
                        _reject(
                            "canvas_storage_reparse_point",
                            "canvas tree contains a symbolic link",
                        )
                    is_directory = stat.S_ISDIR(entry_stat.st_mode)
                    if not is_directory and not stat.S_ISREG(entry_stat.st_mode):
                        _reject(
                            "canvas_storage_unsafe_entry",
                            "canvas tree contains a non-regular entry",
                        )
                    records.append(
                        _DirectoryRecord(
                            name=name,
                            file_id=entry_stat.st_ino,
                            attributes=0,
                            byte_count=entry_stat.st_size,
                            is_directory=is_directory,
                        )
                    )
    except CanvasStorageError:
        raise
    except OSError as exc:
        _raise_io_failure(exc)
    by_name = {record.name: record for record in records}
    if len(by_name) != len(records):
        _reject("canvas_storage_unsafe_entry", "canvas directory has duplicate names")
    return records


def _open_record(
    parent: _PinnedEntry,
    record: _DirectoryRecord,
    *,
    delete: bool = False,
) -> _PinnedEntry:
    if record.attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        _reject("canvas_storage_reparse_point", "canvas tree contains a reparse point")
    path = parent.path / record.name
    if record.is_directory:
        return _open_pinned_directory(
            path,
            parent=parent,
            name=record.name,
            delete=delete,
            expected_file_id=record.file_id,
        )
    return _open_pinned_file(
        path,
        parent=parent,
        name=record.name,
        delete=delete,
        expected_file_id=record.file_id,
    )


def _capture_pinned_tree(
    pin: _PinnedEntry,
    stack: ExitStack,
    *,
    delete: bool = False,
    budget: _EntryBudget | None = None,
) -> _PinnedTree:
    if budget is None:
        if (
            isinstance(CANVAS_MAX_TREE_ENTRIES, bool)
            or not isinstance(CANVAS_MAX_TREE_ENTRIES, int)
            or CANVAS_MAX_TREE_ENTRIES < 1
        ):
            _reject(
                "canvas_storage_invalid_capacity",
                "CANVAS_MAX_TREE_ENTRIES must be a positive integer",
            )
        budget = _EntryBudget(CANVAS_MAX_TREE_ENTRIES)
    records = _directory_records(
        pin,
        max_entries=budget.limit - budget.count,
    )
    record_map = {record.name: record for record in records}
    children: dict[str, _PinnedTree] = {}
    for record in sorted(records, key=lambda candidate: candidate.name.casefold()):
        budget.consume()
        child = _open_record(pin, record, delete=delete)
        stack.callback(child.close)
        children[record.name] = (
            _capture_pinned_tree(child, stack, delete=delete, budget=budget)
            if child.is_directory
            else _PinnedTree(pin=child, records={}, children={})
        )
    return _PinnedTree(pin=pin, records=record_map, children=children)


def _current_entry_metadata(pin: _PinnedEntry) -> tuple[
    tuple[object, object], int, int, int, int, bool
]:
    if pin.closed:
        _reject("canvas_storage_unsafe_entry", "canvas entry handle is closed")
    if os.name == "nt":
        return _windows_metadata(
            pin.handle,
            expected_kind="directory" if pin.is_directory else "file",
        )
    try:  # pragma: no cover - exercised on POSIX deployments
        current = os.fstat(pin.handle)
    except OSError as exc:  # pragma: no cover - exercised on POSIX deployments
        _raise_io_failure(exc)
    return (
        (current.st_dev, current.st_ino),
        current.st_ino,
        0,
        current.st_ctime_ns,
        current.st_size,
        stat.S_ISDIR(current.st_mode),
    )


def _reopen_and_compare(pin: _PinnedEntry) -> None:
    reopened = _open_pinned_entry(
        pin.path,
        kind="directory" if pin.is_directory else "file",
        parent=pin.parent,
        name=pin.name,
        expected_file_id=pin.legacy_file_id,
    )
    try:
        if reopened.identity != pin.identity:
            _reject("canvas_storage_unsafe_entry", "canvas entry changed during traversal")
    finally:
        reopened.close()


def _revalidate_pinned_tree(tree: _PinnedTree, *, reopen_names: bool = True) -> None:
    for child in tree.children.values():
        _revalidate_pinned_tree(child, reopen_names=reopen_names)
    pin = tree.pin
    (
        identity,
        legacy_file_id,
        attributes,
        change_time,
        byte_count,
        is_directory,
    ) = _current_entry_metadata(pin)
    if (
        identity != pin.identity
        or legacy_file_id != pin.legacy_file_id
        or attributes != pin.attributes
        or change_time != pin.change_time
        or byte_count != pin.byte_count
        or is_directory != pin.is_directory
    ):
        _reject("canvas_storage_unsafe_entry", "canvas entry changed during traversal")
    if reopen_names:
        _reopen_and_compare(pin)
    if pin.is_directory:
        current_records = {
            record.name: record
            for record in _directory_records(
                pin,
                max_entries=len(tree.records) + 1,
            )
        }
        if current_records != tree.records:
            _reject("canvas_storage_unsafe_entry", "canvas directory changed during traversal")


def _lexists(path: os.PathLike[str] | str) -> bool:
    try:
        return os.path.lexists(path)
    except OSError as exc:
        _raise_io_failure(exc)


def _validate_uuid(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        _reject("canvas_storage_path_invalid", f"{field} must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanvasStorageError(
            "canvas_storage_path_invalid",
            f"{field} must be a canonical UUID",
        ) from exc
    if str(parsed) != value:
        _reject("canvas_storage_path_invalid", f"{field} must be a canonical UUID")
    return value


def _validate_project_id(project_id: str) -> str:
    return _validate_uuid(project_id, field="project_id")


def _data_root() -> Path:
    configured = Path(CANVAS_DATA_DIR).expanduser()
    if not configured.is_absolute():
        configured = Path.cwd() / configured
    return Path(os.path.abspath(configured))


def _require_contained(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise CanvasStorageError(
            "canvas_storage_path_invalid",
            "canvas path escapes CANVAS_DATA_DIR",
        ) from exc


def _is_reparse(path: Path, path_stat: os.stat_result | None = None) -> bool:
    try:
        if path_stat is None:
            path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode):
            return True
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if bool(getattr(path_stat, "st_file_attributes", 0) & reparse_flag):
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction is not None and is_junction())
    except OSError as exc:
        _raise_io_failure(exc)


def _absolute_components(path: Path) -> list[Path]:
    components: list[Path] = []
    current = path
    while True:
        components.append(current)
        if current.parent == current:
            break
        current = current.parent
    components.reverse()
    return components


def _assert_no_reparse_ancestors(path: Path) -> None:
    for component in _absolute_components(path):
        if not _lexists(component):
            continue
        try:
            component_stat = component.lstat()
        except OSError as exc:
            _raise_io_failure(exc)
        if _is_reparse(component, component_stat):
            _reject(
                "canvas_storage_reparse_point",
                "canvas path contains a reparse point",
            )


def _assert_safe_path(
    path: Path,
    *,
    root: Path,
    must_exist: bool = False,
    expected_kind: str | None = None,
) -> None:
    _require_contained(path, root)
    _assert_no_reparse_ancestors(path)
    exists = _lexists(path)
    if not exists:
        if must_exist:
            _reject("canvas_storage_asset_missing", "canvas asset file is missing")
        return
    try:
        path_stat = path.lstat()
    except OSError as exc:
        _raise_io_failure(exc)
    if _is_reparse(path, path_stat):
        _reject("canvas_storage_reparse_point", "canvas path is a reparse point")
    if expected_kind == "directory" and not stat.S_ISDIR(path_stat.st_mode):
        _reject("canvas_storage_unsafe_entry", "canvas path must be a directory")
    if expected_kind == "file" and not stat.S_ISREG(path_stat.st_mode):
        _reject(
            "canvas_storage_asset_not_regular",
            "canvas asset path must be a regular file",
        )


def _validate_relative_path(relative_path: object) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path:
        _reject("canvas_storage_path_invalid", "canvas relative path is invalid")
    if "\x00" in relative_path or "\\" in relative_path or ":" in relative_path:
        _reject("canvas_storage_path_invalid", "canvas relative path is unsafe")
    posix_path = PurePosixPath(relative_path)
    windows_path = PureWindowsPath(relative_path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        _reject("canvas_storage_path_invalid", "canvas relative path must be relative")
    raw_parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        _reject("canvas_storage_path_invalid", "canvas relative path is ambiguous")
    for part in raw_parts:
        if part.endswith((".", " ")):
            _reject("canvas_storage_path_invalid", "canvas path segment has an unsafe suffix")
        device_stem = part.split(".", 1)[0].upper()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            _reject("canvas_storage_path_invalid", "canvas path uses a device name")
    return tuple(raw_parts)


def project_root(project_id: str) -> Path:
    """Return one canonical project root without following reparse points."""
    validated_id = _validate_project_id(project_id)
    data_root = _data_root()
    candidate = data_root / validated_id
    _assert_safe_path(candidate, root=data_root)
    return candidate


def ensure_project_tree(project_id: str) -> Path:
    """Create the fixed tree only relative to pinned, no-follow parent handles."""
    validated_project_id = _validate_project_id(project_id)
    data_root = _data_root()
    root = data_root / validated_project_id
    with _ensure_directory_chain(data_root) as data_pins, ExitStack() as stack:
        data_pin = data_pins[-1]
        project_pin = _open_pinned_directory(
            root,
            parent=data_pin,
            name=validated_project_id,
            create=True,
        )
        stack.callback(project_pin.close)
        child_pins: dict[str, _PinnedEntry] = {}
        for directory_name in PROJECT_SUBDIRECTORIES:
            child = _open_pinned_directory(
                root / directory_name,
                parent=project_pin,
                name=directory_name,
                create=True,
            )
            stack.callback(child.close)
            child_pins[directory_name] = child

        records = {
            record.name: record
            for record in _directory_records(
                project_pin,
                max_entries=CANVAS_MAX_TREE_ENTRIES,
            )
        }
        for directory_name, child in child_pins.items():
            record = records.get(directory_name)
            if (
                record is None
                or not record.is_directory
                or record.file_id != child.legacy_file_id
            ):
                _reject(
                    "canvas_storage_unsafe_entry",
                    "canvas project tree changed during creation",
                )
            _reopen_and_compare(child)
        _reopen_and_compare(project_pin)
    return root


def _expected_asset_extension(asset: Any) -> set[str]:
    if asset.asset_type == "source":
        extensions = _SOURCE_EXTENSIONS_BY_MIME.get(asset.mime_type)
        if extensions is None:
            _reject("canvas_storage_path_invalid", "source MIME is unsupported")
        return extensions
    if asset.mime_type != "image/png":
        _reject("canvas_storage_path_invalid", "derived assets must currently be PNG")
    return {".png"}


def resolve_asset_path(asset: Any, *, project_id: str) -> Path:
    """Resolve an existing DB-backed asset to one contained regular file."""
    validated_project_id = _validate_project_id(project_id)
    if getattr(asset, "project_id", None) != validated_project_id:
        _reject("canvas_storage_path_invalid", "asset belongs to another project")
    if getattr(asset, "deleted_at", None) is not None:
        _reject("canvas_storage_asset_deleted", "asset is soft-deleted")
    asset_id = _validate_uuid(getattr(asset, "id", None), field="asset.id")
    directory = ASSET_TYPE_DIRECTORIES.get(getattr(asset, "asset_type", None))
    if directory is None:
        _reject("canvas_storage_path_invalid", "asset type has no storage directory")
    parts = _validate_relative_path(getattr(asset, "relative_path", None))
    if len(parts) != 2 or parts[0] != directory:
        _reject("canvas_storage_path_invalid", "asset path does not match its type")
    filename = Path(parts[1])
    if filename.stem != asset_id or filename.suffix.lower() not in _expected_asset_extension(asset):
        _reject("canvas_storage_path_invalid", "asset filename or extension is invalid")
    root = project_root(validated_project_id)
    path = root.joinpath(*parts)
    _assert_safe_path(
        path,
        root=_data_root(),
        must_exist=True,
        expected_kind="file",
    )
    return path


def _count_files(tree: _PinnedTree, *, include_uploading: bool) -> int:
    total = 0
    for name, child in tree.children.items():
        if child.pin.is_directory:
            total += _count_files(child, include_uploading=include_uploading)
        elif include_uploading or not name.endswith(".uploading"):
            total += child.pin.byte_count
    return total


def _scan_directory_bytes(directory: Path, *, include_temporary: bool) -> int:
    """Scan a generic directory only through pinned, no-follow native handles."""
    with _pin_directory_chain(directory) as pins, ExitStack() as stack:
        tree = _capture_pinned_tree(pins[-1], stack)
        total = _count_files(tree, include_uploading=include_temporary)
        _revalidate_pinned_tree(tree)
        return total


def _validate_project_tree(tree: _PinnedTree) -> None:
    if set(tree.records) != set(PROJECT_SUBDIRECTORIES):
        _reject("canvas_storage_unsafe_entry", "canvas project tree is not canonical")
    if any(not tree.children[name].pin.is_directory for name in PROJECT_SUBDIRECTORIES):
        _reject("canvas_storage_unsafe_entry", "canvas project entry is not a directory")


def _count_project_tree(tree: _PinnedTree, *, include_temporary: bool) -> int:
    _validate_project_tree(tree)
    total = 0
    for directory_name in PROJECT_SUBDIRECTORIES:
        if directory_name == "tmp" and not include_temporary:
            continue
        total += _count_files(
            tree.children[directory_name],
            include_uploading=include_temporary,
        )
    return total


def _project_usage_bytes(root: Path, *, include_temporary: bool) -> int:
    with _pin_directory_chain(root) as pins, ExitStack() as stack:
        tree = _capture_pinned_tree(pins[-1], stack)
        _validate_project_tree(tree)
        total = _count_project_tree(tree, include_temporary=include_temporary)
        _revalidate_pinned_tree(tree)
        return total


def canvas_usage_bytes(
    *,
    project_id: str | None = None,
    include_temporary: bool = True,
) -> int:
    """Return contained regular-file usage, rejecting ambiguous filesystem state."""
    if not isinstance(include_temporary, bool):
        _reject("canvas_storage_unsafe_entry", "include_temporary must be boolean")
    data_root = _data_root()
    _assert_safe_path(data_root, root=data_root)
    if not _lexists(data_root):
        return 0
    _assert_safe_path(data_root, root=data_root, must_exist=True, expected_kind="directory")
    if project_id is not None:
        root = project_root(project_id)
        if not _lexists(root):
            return 0
        return _project_usage_bytes(root, include_temporary=include_temporary)

    with _pin_directory_chain(data_root) as pins, ExitStack() as stack:
        tree = _capture_pinned_tree(pins[-1], stack)
        total = 0
        for name, child in tree.children.items():
            if not child.pin.is_directory:
                _reject("canvas_storage_unsafe_entry", "canvas data root contains a file")
            try:
                _validate_project_id(name)
            except CanvasStorageError as exc:
                raise CanvasStorageError(
                    "canvas_storage_unsafe_entry",
                    "canvas data root contains a non-project directory",
                ) from exc
            _validate_project_tree(child)
            total += _count_project_tree(child, include_temporary=include_temporary)
        _revalidate_pinned_tree(tree)
        return total


def _validate_capacity_value(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject(
            "canvas_storage_invalid_capacity",
            f"{name} must be a non-negative integer",
        )
    return value


def _disk_usage_target(data_root: Path) -> Path:
    target = data_root
    try:
        while not target.exists() and target.parent != target:
            target = target.parent
    except OSError as exc:
        _raise_io_failure(exc)
    _assert_no_reparse_ancestors(target)
    return target


def _disk_free_bytes(data_root: Path) -> int:
    target = _disk_usage_target(data_root)
    with _pin_directory_chain(target) as pins:
        pin = pins[-1]
        try:
            free_bytes = shutil.disk_usage(target).free
        except OSError as exc:
            _raise_io_failure(exc)
        identity, legacy_file_id, attributes, _, _, is_directory = _current_entry_metadata(pin)
        if (
            identity != pin.identity
            or legacy_file_id != pin.legacy_file_id
            or attributes != pin.attributes
            or not is_directory
        ):
            _reject("canvas_storage_unsafe_entry", "canvas disk target changed")
        _reopen_and_compare(pin)
        return free_bytes


def assert_canvas_capacity(
    *,
    project_id: str,
    additional_bytes: int,
    reserved_project_bytes: int = 0,
    reserved_total_bytes: int = 0,
) -> None:
    """Enforce project, aggregate, and remaining-disk formulas exactly once."""
    additional = _validate_capacity_value("additional_bytes", additional_bytes)
    reserved_project = _validate_capacity_value(
        "reserved_project_bytes", reserved_project_bytes
    )
    reserved_total = _validate_capacity_value("reserved_total_bytes", reserved_total_bytes)
    validated_project_id = _validate_project_id(project_id)

    project_usage = canvas_usage_bytes(project_id=validated_project_id)
    if project_usage + reserved_project + additional > CANVAS_PROJECT_QUOTA_BYTES:
        _reject(
            "canvas_storage_project_quota_exceeded",
            "canvas project quota would be exceeded",
        )
    total_usage = canvas_usage_bytes()
    if total_usage + reserved_total + additional > CANVAS_TOTAL_QUOTA_BYTES:
        _reject(
            "canvas_storage_total_quota_exceeded",
            "canvas total quota would be exceeded",
        )
    free_bytes = _disk_free_bytes(_data_root())
    if free_bytes - reserved_total - additional < CANVAS_MIN_FREE_BYTES:
        _reject("canvas_storage_low_disk", "canvas storage minimum free space would be crossed")


_TEMPORARY_FILE_MAX_AGE = timedelta(hours=24)
_WINDOWS_UNIX_EPOCH_OFFSET_100NS = 116_444_736_000_000_000


def _datetime_to_unix_ns(value: datetime, *, field: str) -> int:
    if not isinstance(value, datetime):
        _reject("canvas_storage_cleanup_invalid", f"{field} must be a datetime")
    normalized = (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None
        else value.astimezone(UTC)
    )
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (
        (delta.days * 86_400 + delta.seconds) * 1_000_000_000
        + delta.microseconds * 1_000
    )


def _cleanup_cutoff_ns(
    *,
    now: datetime | None,
    cutoff: datetime | None,
) -> int:
    if now is not None and cutoff is not None:
        _reject(
            "canvas_storage_cleanup_invalid",
            "now and cutoff are mutually exclusive",
        )
    if cutoff is not None:
        return _datetime_to_unix_ns(cutoff, field="cutoff")
    current = now if now is not None else datetime.now(UTC)
    if not isinstance(current, datetime):
        _reject("canvas_storage_cleanup_invalid", "now must be a datetime")
    normalized = (
        current.replace(tzinfo=UTC)
        if current.tzinfo is None
        else current.astimezone(UTC)
    )
    return _datetime_to_unix_ns(
        normalized - _TEMPORARY_FILE_MAX_AGE,
        field="cutoff",
    )


def _validated_cleanup_references(
    referenced_relative_paths: object,
) -> frozenset[str]:
    if not isinstance(referenced_relative_paths, (set, frozenset)):
        _reject(
            "canvas_storage_cleanup_invalid",
            "referenced_relative_paths must be a set",
        )
    normalized: set[str] = set()
    for raw_reference in referenced_relative_paths:
        parts = _validate_relative_path(raw_reference)
        if len(parts) != 3:
            _reject(
                "canvas_storage_path_invalid",
                "cleanup references must be relative to CANVAS_DATA_DIR",
            )
        _validate_project_id(parts[0])
        if parts[1] not in PROJECT_SUBDIRECTORIES:
            _reject(
                "canvas_storage_path_invalid",
                "cleanup reference uses an unknown project directory",
            )
        normalized.add("/".join(parts))
    return frozenset(normalized)


def _cleanup_entry_limit() -> int:
    if (
        isinstance(CANVAS_MAX_TREE_ENTRIES, bool)
        or not isinstance(CANVAS_MAX_TREE_ENTRIES, int)
        or CANVAS_MAX_TREE_ENTRIES < 1
    ):
        _reject(
            "canvas_storage_invalid_capacity",
            "CANVAS_MAX_TREE_ENTRIES must be a positive integer",
        )
    return CANVAS_MAX_TREE_ENTRIES


def _budgeted_directory_records(
    pin: _PinnedEntry,
    *,
    budget: _EntryBudget,
) -> list[_DirectoryRecord]:
    records = _directory_records(
        pin,
        max_entries=budget.limit - budget.count,
    )
    for _record in records:
        budget.consume()
    return records


def _pinned_file_last_write_ns(pin: _PinnedEntry) -> int:
    if pin.closed or pin.is_directory:
        _reject("canvas_storage_unsafe_entry", "cleanup target is not a regular file")
    if os.name == "nt":
        basic = _FileBasicInfo()
        try:
            _windows_query(pin.handle, _FILE_BASIC_INFO_CLASS, basic)
        except OSError as exc:
            _raise_io_failure(exc)
        last_write_100ns = int(basic.LastWriteTime)
        if last_write_100ns < _WINDOWS_UNIX_EPOCH_OFFSET_100NS:
            _reject("canvas_storage_unsafe_entry", "cleanup target time is invalid")
        return (last_write_100ns - _WINDOWS_UNIX_EPOCH_OFFSET_100NS) * 100
    try:  # pragma: no cover - exercised on POSIX deployments
        return int(os.fstat(pin.handle).st_mtime_ns)
    except OSError as exc:  # pragma: no cover - exercised on POSIX deployments
        _raise_io_failure(exc)


def _revalidate_cleanup_file(pin: _PinnedEntry) -> None:
    identity, legacy_file_id, attributes, change_time, byte_count, is_directory = (
        _current_entry_metadata(pin)
    )
    if (
        identity != pin.identity
        or legacy_file_id != pin.legacy_file_id
        or attributes != pin.attributes
        or change_time != pin.change_time
        or byte_count != pin.byte_count
        or is_directory
    ):
        _reject("canvas_storage_unsafe_entry", "cleanup target changed")


def _revalidate_cleanup_directory(
    pin: _PinnedEntry,
    expected_records: dict[str, _DirectoryRecord],
) -> None:
    identity, legacy_file_id, attributes, change_time, _, is_directory = (
        _current_entry_metadata(pin)
    )
    if (
        identity != pin.identity
        or legacy_file_id != pin.legacy_file_id
        or attributes != pin.attributes
        or change_time != pin.change_time
        or not is_directory
    ):
        _reject("canvas_storage_unsafe_entry", "cleanup directory changed")
    current_records = {
        record.name: record
        for record in _directory_records(
            pin,
            max_entries=len(expected_records) + 1,
        )
    }
    if current_records != expected_records:
        _reject("canvas_storage_unsafe_entry", "cleanup directory changed")
    _reopen_and_compare(pin)


def cleanup_stale_temporary_files(
    *,
    referenced_relative_paths: set[str] | frozenset[str],
    now: datetime | None = None,
    cutoff: datetime | None = None,
) -> int:
    """Delete only stale, unreferenced ``tmp/*.uploading`` files safely.

    References are canonical POSIX paths relative to ``CANVAS_DATA_DIR`` in the
    form ``<project UUID>/<asset relative path>``. The whole cleanup target set
    is validated and pinned before the first deletion, so an unsafe tree never
    produces a partial cleanup.
    """

    references = _validated_cleanup_references(referenced_relative_paths)
    stale_cutoff_ns = _cleanup_cutoff_ns(now=now, cutoff=cutoff)
    data_root = _data_root()
    _assert_safe_path(data_root, root=data_root)
    if not _lexists(data_root):
        return 0
    _assert_safe_path(
        data_root,
        root=data_root,
        must_exist=True,
        expected_kind="directory",
    )

    budget = _EntryBudget(_cleanup_entry_limit())
    candidates: list[_PinnedEntry] = []
    directory_snapshots: list[tuple[_PinnedEntry, dict[str, _DirectoryRecord]]] = []
    with _pin_directory_chain(data_root) as data_chain, ExitStack() as stack:
        data_pin = data_chain[-1]
        data_records = _budgeted_directory_records(data_pin, budget=budget)
        directory_snapshots.append(
            (data_pin, {record.name: record for record in data_records})
        )

        for project_record in sorted(
            data_records,
            key=lambda record: record.name.casefold(),
        ):
            try:
                project_id = _validate_project_id(project_record.name)
            except CanvasStorageError as exc:
                raise CanvasStorageError(
                    "canvas_storage_unsafe_entry",
                    "canvas data root contains a non-project entry",
                ) from exc
            if project_record.attributes & getattr(
                stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            ):
                _reject(
                    "canvas_storage_reparse_point",
                    "canvas data root contains a reparse point",
                )
            if not project_record.is_directory:
                _reject(
                    "canvas_storage_unsafe_entry",
                    "canvas data root contains a file",
                )

            project_pin = _open_record(data_pin, project_record)
            stack.callback(project_pin.close)
            project_records = _budgeted_directory_records(project_pin, budget=budget)
            project_record_map = {
                record.name: record
                for record in project_records
            }
            directory_snapshots.append((project_pin, project_record_map))
            if set(project_record_map) != set(PROJECT_SUBDIRECTORIES):
                _reject(
                    "canvas_storage_unsafe_entry",
                    "canvas project tree is not canonical",
                )

            project_directory_pins: dict[str, _PinnedEntry] = {}
            for directory_record in project_records:
                if directory_record.attributes & getattr(
                    stat,
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    0x400,
                ):
                    _reject(
                        "canvas_storage_reparse_point",
                        "canvas project tree contains a reparse point",
                    )
                if not directory_record.is_directory:
                    _reject(
                        "canvas_storage_unsafe_entry",
                        "canvas project entry is not a directory",
                    )
                directory_pin = _open_record(project_pin, directory_record)
                stack.callback(directory_pin.close)
                project_directory_pins[directory_record.name] = directory_pin

            tmp_pin = project_directory_pins["tmp"]
            temporary_records = _budgeted_directory_records(tmp_pin, budget=budget)
            temporary_record_map = {
                record.name: record
                for record in temporary_records
            }
            directory_snapshots.append((tmp_pin, temporary_record_map))
            for temporary_record in sorted(
                temporary_records,
                key=lambda record: record.name.casefold(),
            ):
                if temporary_record.attributes & getattr(
                    stat,
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    0x400,
                ):
                    _reject(
                        "canvas_storage_reparse_point",
                        "canvas temporary tree contains a reparse point",
                    )
                strict_uploading_file = (
                    not temporary_record.is_directory
                    and Path(temporary_record.name).suffix == ".uploading"
                )
                reference = f"{project_id}/tmp/{temporary_record.name}"
                may_delete = strict_uploading_file and reference not in references
                temporary_pin = _open_record(
                    tmp_pin,
                    temporary_record,
                    delete=may_delete,
                )
                stack.callback(temporary_pin.close)
                if (
                    may_delete
                    and _pinned_file_last_write_ns(temporary_pin) <= stale_cutoff_ns
                ):
                    candidates.append(temporary_pin)

        for directory_pin, expected_records in directory_snapshots:
            _revalidate_cleanup_directory(directory_pin, expected_records)
        confirmed_candidates: list[_PinnedEntry] = []
        for candidate in candidates:
            _revalidate_cleanup_file(candidate)
            if _pinned_file_last_write_ns(candidate) > stale_cutoff_ns:
                continue
            confirmed_candidates.append(candidate)

        deleted = 0
        for candidate in confirmed_candidates:
            if candidate.closed:
                continue
            _revalidate_cleanup_file(candidate)
            if _pinned_file_last_write_ns(candidate) > stale_cutoff_ns:
                continue
            _dispose_pinned_entry(candidate)
            deleted += 1
        return deleted


def _dispose_pinned_entry(pin: _PinnedEntry) -> None:
    if pin.closed:
        return
    if pin.parent is None or pin.name is None:
        _reject("canvas_storage_unsafe_entry", "canvas delete target has no pinned parent")
    try:
        if os.name == "nt":
            flags = wintypes.DWORD(
                _FILE_DISPOSITION_DELETE
                | _FILE_DISPOSITION_POSIX_SEMANTICS
                | _FILE_DISPOSITION_IGNORE_READONLY_ATTRIBUTE
            )
            if not _SetFileInformationByHandle(
                pin.handle,
                _FILE_DISPOSITION_INFO_EX_CLASS,
                ctypes.byref(flags),
                ctypes.sizeof(flags),
            ):
                error = ctypes.get_last_error()
                if error not in {1, 50, 87}:
                    raise ctypes.WinError(error)
                fallback = _FileDispositionInfo(DeleteFile=1)
                if not _SetFileInformationByHandle(
                    pin.handle,
                    _FILE_DISPOSITION_INFO_CLASS,
                    ctypes.byref(fallback),
                    ctypes.sizeof(fallback),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
        else:  # pragma: no cover - exercised on POSIX deployments
            current = os.stat(pin.name, dir_fd=pin.parent.handle, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != pin.identity:
                _reject("canvas_storage_unsafe_entry", "canvas delete target changed")
            if pin.is_directory:
                os.rmdir(pin.name, dir_fd=pin.parent.handle)
            else:
                os.unlink(pin.name, dir_fd=pin.parent.handle)
    except CanvasStorageError:
        raise
    except OSError as exc:
        _raise_io_failure(exc)
    pin.close()


def _dispose_pinned_tree(tree: _PinnedTree) -> None:
    for child in tree.children.values():
        _dispose_pinned_tree(child)
    pin = tree.pin
    if pin.is_directory:
        if _directory_records(pin, max_entries=1):
            _reject("canvas_storage_unsafe_entry", "canvas delete directory changed")
        identity, legacy_file_id, attributes, _, _, is_directory = _current_entry_metadata(pin)
        if (
            identity != pin.identity
            or legacy_file_id != pin.legacy_file_id
            or attributes != pin.attributes
            or not is_directory
        ):
            _reject("canvas_storage_unsafe_entry", "canvas delete directory changed")
    else:
        identity, legacy_file_id, attributes, change_time, byte_count, is_directory = (
            _current_entry_metadata(pin)
        )
        if (
            identity != pin.identity
            or legacy_file_id != pin.legacy_file_id
            or attributes != pin.attributes
            or change_time != pin.change_time
            or byte_count != pin.byte_count
            or is_directory
        ):
            _reject("canvas_storage_unsafe_entry", "canvas delete file changed")
    _dispose_pinned_entry(pin)


def remove_project_tree(project_id: str) -> None:
    """Remove one project through pinned handles, never path-based recursion."""
    root = project_root(project_id)
    if not _lexists(root):
        return
    with _pin_directory_chain(root, delete_final=True) as pins, ExitStack() as stack:
        tree = _capture_pinned_tree(pins[-1], stack, delete=True)
        _revalidate_pinned_tree(tree, reopen_names=False)
        _dispose_pinned_tree(tree)
