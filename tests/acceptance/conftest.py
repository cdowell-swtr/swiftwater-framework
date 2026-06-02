"""Acceptance-tier fixtures. The dev/CI /tmp is RAM-backed (tmpfs); heavy renders + dind layers
must use a disk-backed dir. `disk_tmp` yields a per-test dir under a disk-backed root
(SWIFTWATER_TEST_TMP if set, else /var/tmp/swiftwater-tests)."""

import os
import shutil
from pathlib import Path

import pytest

_DISK_ROOT = Path(os.environ.get("SWIFTWATER_TEST_TMP", "/var/tmp/swiftwater-tests"))


@pytest.fixture
def disk_tmp(request):
    _DISK_ROOT.mkdir(parents=True, exist_ok=True)
    d = _DISK_ROOT / request.node.name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
