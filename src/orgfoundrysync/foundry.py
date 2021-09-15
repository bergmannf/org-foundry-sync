#!/usr/bin/env python3

import asyncio
import dataclasses
import glob
import json
import re
import os
import sys
from typing import Any, Dict, Optional, List, Union, Tuple

from playwright.async_api import Browser
import pypandoc


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryFolder:
    _id: str
    name: str
    type: str = "JournalEntry"
    description: Optional[str] = ""
    parent: Optional[str] = None
    sorting: Optional[str] = "a"
    sort: Optional[int] = 0
    color: Optional[str] = None
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)

    def read_metadata(self, root_path: str, folders: List):
        path = "/".join([root_path, self.path(folders), ".orgfoundrysync"])
        if not os.path.exists(path):
            return {}
        with open(path) as metadata:
            return json.load(metadata)

    def write_metadata(self, root_path: str, folders: List):
        path = "/".join([root_path, self.path(folders), ".orgfoundrysync"])
        data = self.read_metadata(root_path, folders)
        data[self.path(folders)] = self._id
        with open(path, "w") as metadata:
            metadata.write(json.dumps(data))

    def path(self, folders: List):
        if self.parent == None:
            return self.name
        parent_folder = [f for f in folders if f._id == self.parent][0]
        return "/".join([parent_folder.path(folders), self.name])


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryJournalEntry:
    _id: str
    name: str
    content: str
    img: Optional[str]
    folder: Optional[str]
    sort: int
    permission: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)

    def parent(self, folders: List) -> FoundryFolder:
        if not self.folder:
            return None
        else:
            return [f for f in folders if f._id == self.folder][0]

    def read_metadata(self, root_path: str, folders: List):
        path = "/".join(
            [root_path, self.parent(folders).path(folders), ".orgfoundrysync"]
        )
        with open(path) as metadata:
            return json.load(metadata)

    def path(self, folders: List, format: str):
        if self.folder:
            path = self.parent(folders).path(folders)
        else:
            path = ""
        return "/".join([path, self.name + "." + format])


class Foundry:
    def __init__(self, url, browser: Browser, user="Gamemaster", password=None):
        self.url = url
        self.password = password or os.getenv("FOUNDRY_SYNC_PASSWORD")
        if not self.password:
            raise RuntimeError("Can not login to FoundryVTT without a password.")
        self.user = user
        self.browser = browser
        self._folders = None
        self._journal_entries = None

    @property
    def folders(self):
        return self._folders

    @folders.setter
    def folders(self, folders):
        self._folders = [FoundryFolder(**folder) for folder in folders]

    @property
    def journal_entries(self):
        return self._journal_entries

    @journal_entries.setter
    def journal_entries(self, entries):
        self._journal_entries = [FoundryJournalEntry(**entry) for entry in entries]

    async def login(self):
        page = await self.browser.new_page()
        await page.goto(self.url + "/join")
        await page.select_option("select[name=userid]", label=self.user)
        await page.fill("input[name=password]", self.password)
        await page.click("button[name=join]")
        return page

    async def download_notes(self):
        page = await self.login()
        await page.goto(self.url + "/game", wait_until="networkidle")
        await page.wait_for_selector('a[title="Journal Entries"]')
        print("Downloading folders")
        self.folders = await page.evaluate(
            '() => { return game.folders.filter(j => j.type === "JournalEntry").map(f => f.toJSON()) }'
        )
        print("Downloading journal entries")
        self.journal_entries = await page.evaluate(
            "() => { return game.journal.contents.map(j => j.toJSON()) }"
        )
        return [self.folders, self.journal_entries]

    async def upload_note(self, note: FoundryJournalEntry):
        script = """
        () => {{
        var note = game.journal.filter(j => j.id === "{note_id}")[0];
        var data = note.data;
        data.content = `{note_content}`;
        note.update(data)
        }}
        """.format(
            note_id=note._id, note_content=note.content
        )
        page = await self.login()
        await page.goto(self.url + "/game", wait_until="networkidle")
        await page.wait_for_selector('a[title="Journal Entries"]')
        await page.evaluate(script)


class LocalStorage:
    def __init__(
        self,
        root_directory: str,
        format: str,
        folders: List[FoundryFolder],
        journalentries: List[FoundryJournalEntry],
    ):
        self.root_directory = root_directory
        self.format = format
        self.folders = folders
        self.journalentries = journalentries

    def write_metadata(self, f: Union[FoundryFolder, FoundryJournalEntry]):
        obj = dataclasses.asdict(f)
        if isinstance(f, FoundryFolder):
            path = ".".join([self.fullpath(f), "folder", "foundrysync"])
        elif isinstance(f, FoundryJournalEntry):
            path = ".".join([self.fullpath(f), "journalentry", "foundrysync"])
        else:
            raise RuntimeError(f"Can not handle type {type(f)}.")
        with open(path, "w") as fd:
            fd.write(json.dumps(obj))

    def fullpath(self, f: Union[FoundryFolder, FoundryJournalEntry]):
        if isinstance(f, FoundryFolder):
            return "/".join([self.root_directory, f.path(self.folders)])
        if isinstance(f, FoundryJournalEntry):
            return "/".join([self.root_directory, f.path(self.folders, self.format)])

    def write(self, f: Union[FoundryFolder, FoundryJournalEntry]):
        """Write a single FoundryObject to the fileysstem."""
        fullpath = self.fullpath(f)
        # TODO: Extract into polymorphism
        if isinstance(f, FoundryFolder):
            os.makedirs(fullpath, exist_ok=True)
        elif isinstance(f, FoundryJournalEntry):
            with open(fullpath, "w") as fd:
                fd.write(pypandoc.convert_text(f.content, self.format, format="html"))
        self.write_metadata(f)

    def write_all(self):
        """Write all FoundryObjects to the filesystem."""
        for f in self.folders:
            self.write(f)
        for n in self.journalentries:
            self.write(n)

    @staticmethod
    def read_all(
        root_dir: str,
        source_format: str,
    ):
        print(f"Reading local data from {root_dir}")
        folder_paths = glob.glob(root_dir + "/**/**.folder.foundrysync", recursive=True)
        journal_entry_paths = glob.glob(
            root_dir + "/**/**.journalentry.foundrysync", recursive=True
        )
        fs = []
        for f in folder_paths:
            print(f"Reading folder {f}")
            with open(f, "r") as fd:
                fs.append(FoundryFolder(**json.load(fd)))
        js = []
        for f in journal_entry_paths:
            print(f"Reading journal entry {f}")
            with open(f, "r") as fd:
                contentpath = f.replace(".journalentry.foundrysync", "")
                with open(contentpath, "r") as fd2:
                    c = fd2.read()
                    if source_format == "org":
                        # Must wrap the @JournalEntry in = signs for code formatting.
                        # Otherwise it will be handled as a ref.
                        c = re.sub(
                            "(?P<entry>@JournalEntry\[.*\]{.*})", "=\g<entry>=", c
                        )
                    content = pypandoc.convert_text(
                        c,
                        "html",
                        format=source_format,
                    )
                    entry = json.load(fd)
                    entry["content"] = content
                    js.append(FoundryJournalEntry(**entry))
        print(f"Read {len(fs)} folders and {len(js)} journal entries.")
        return LocalStorage(root_dir, source_format, fs, js)
