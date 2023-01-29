#!/usr/bin/env python3
import dataclasses
import pathlib


@dataclasses.dataclass(frozen=True, eq=True)
class UploadNote:
    path: pathlib.Path


@dataclasses.dataclass(frozen=True, eq=True)
class UploadAllNotes:
    pass


@dataclasses.dataclass(frozen=True, eq=True)
class DownloadNote:
    name: str


@dataclasses.dataclass(frozen=True, eq=True)
class DownloadAllNotes:
    pass


class Quit:
    pass
