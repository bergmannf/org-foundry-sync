#!/usr/bin/env python3
import dataclasses
import pathlib
from orgfoundrysync.foundry import LocalStorage, FoundryFolder, MetadataStorage


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
    page = entry / "Page.org"
    page.touch()

    storage = LocalStorage(root_dir, "org").read_all()
    assert len(storage.folders) == 1


def test_writing_metadata(tmp_path: pathlib.Path):
    metadata = MetadataStorage(root_directory=tmp_path)
    f1 = FoundryFolder(_id="1", name="root")
    metadata.write(f1)
    data = metadata.read(f1)
    obj = dataclasses.asdict(f1)
    assert data == obj
