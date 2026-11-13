import hashlib
import zipfile

import pytest

from phosphor import installer
from phosphor.apps import AppSpec
from phosphor.updater import Release, UpdateError

APP = AppSpec("count", "Phosphor Count", "o/r", "PhosphorCount-windows.zip", "PhosphorCount.exe", ("." * 11,) * 9)


def make_zip(path, body=b"exe-v1"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("PhosphorCount/PhosphorCount.exe", body)
        z.writestr("PhosphorCount/_internal/base_library.zip", b"lib")
        z.writestr("PhosphorCount/READ ME FIRST.txt", b"hi")
    data = path.read_bytes()
    return Release("v1.5", (1, 5), "https://x", path.as_uri(), len(data), hashlib.sha256(data).hexdigest())


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOSPHOR_TOOLS_APPS", str(tmp_path / "apps"))
    return tmp_path


def test_install_then_reinstall(root):
    rel = make_zip(root / "a.zip")
    seen = []
    exe = installer.install(APP, progress=seen.append, latest=lambda: rel)
    assert exe == installer.exe_path(APP) and exe.read_bytes() == b"exe-v1"
    assert installer.installed(APP) and installer.installed_tag(APP) == "v1.5" and seen[-1] == 1.0
    (installer.folder(APP) / "user-file.txt").write_text("x")      # replaced wholesale on reinstall
    rel2 = make_zip(root / "b.zip", b"exe-v2")
    installer.install(APP, latest=lambda: rel2)
    assert exe.read_bytes() == b"exe-v2"
    assert sorted(p.name for p in installer.apps_root().iterdir()) == ["count"]   # no leftovers


def test_failed_download_keeps_the_old_copy(root):
    installer.install(APP, latest=lambda: make_zip(root / "a.zip"))
    bad = make_zip(root / "b.zip", b"exe-v2")
    bad.sha256 = "0" * 64
    with pytest.raises(UpdateError):
        installer.install(APP, latest=lambda: bad)
    assert installer.exe_path(APP).read_bytes() == b"exe-v1"


def test_no_release():
    with pytest.raises(UpdateError, match="NO PHOSPHOR COUNT RELEASE"):
        installer.install(APP, latest=lambda: None)
