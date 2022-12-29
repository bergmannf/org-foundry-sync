#!/usr/bin/env python3
import pathlib
from orgfoundrysync.foundry import LocalStorage, FoundryFolder


def test_relative_path():
    f1 = FoundryFolder(_id="1", name="root")
    f2 = FoundryFolder(_id="2", name="sub", parent="1")
    s = LocalStorage(pathlib.Path(), "org", [f1, f2], [])
    relative_path = s.path(f2)
    assert str(relative_path) == "root/sub"


def test_write_folder(tmp_path: pathlib.Path):
    f = FoundryFolder(_id="1", name="Folder")
    s = LocalStorage(tmp_path, "org", [], [])
    s.write(f)
    assert (tmp_path / "Folder").is_dir()


def test_load_folder(tmp_path: pathlib.Path):
    root_dir = tmp_path.absolute()
    folder = root_dir / "Folder"
    folder.mkdir()
    entry = folder / "Entry"
    entry.mkdir()
    page = folder / "Page.org"
    page.touch()

    storage = LocalStorage.read_all(root_dir, "org")
    assert len(storage.folders) == 1
