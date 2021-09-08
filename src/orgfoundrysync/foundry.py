#!/usr/bin/env python3

import asyncio
import dataclasses
import json
import os
import sys
from typing import Any, Dict, Optional, List, Union

from playwright.async_api import async_playwright
import pypandoc


def store_folder(f):
    print(f"Making folder {f}")


def store_journal_entry(e):
    print(f"Storing journal entry {e}")


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

    def store(self, root_path: str, folders: List):
        """Create the folder on the filesystem.#!/usr/bin/env python

        TODO: Store the _id in a hidden file inside the folder."""
        if not root_path:
            root_path = "."
        path = self.path(folders)
        path = "/".join([root_path, path])
        os.makedirs(path, exist_ok=True)
        self.write_metadata(root_path, folders)


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

    def write_metadata(self, root_path: str, folders: List):
        path = self.path(root_path, folders)
        data = self.read_metadata(root_path, folders)
        data[path] = self._id
        location = "/".join(
            [root_path, self.parent(folders).path(folders), ".orgfoundrysync"]
        )
        with open(location, "w") as metadata:
            metadata.write(json.dumps(data))

    def path(self, root_path: str, folders: List):
        if self.folder:
            self.parent(folders).store(root_path, folders)
            path = self.parent(folders).path(folders)
        else:
            path = ""
        return "/".join([path, self.name + ".org"])

    def store(self, root_path: str, folders: List):
        """Save the content in this FoundryJournalEntry to the filesystem.

        TODO: Store the _id in a hidden file inside the folder."""
        if not root_path:
            root_path = "."
        path = self.path(root_path, folders)
        path = "/".join([root_path, path])
        with open(path, "w") as f:
            f.write(pypandoc.convert_text(self.content, "org", format="html"))
        self.write_metadata(root_path, folders)

    def load(self, root_path: str):
        """Load the stored file from the filesystem again."""
        pass


class Foundry:
    def __init__(self, url):
        self.url = url
        self.browser = None
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

    async def _launch(self, playwright=None):
        if not playwright:
            playwright = await async_playwright()
        self.browser = await playwright.chromium.launch(headless=False, slow_mo=50)

    async def login(self, playwright=None):
        async with async_playwright() as p:
            if not self.browser:
                await self._launch(p)
            page = await self.browser.new_page()
            await page.goto(self.url + "/join")
            await page.select_option("select[name=userid]", label="Gamemaster")
            await page.fill("input[name=password]", os.getenv("FOUNDRY_SYNC_PASSWORD"))
            await page.click("button[name=join]")
            return page

    async def download_notes(self, playwright=None):
        async with async_playwright() as p:
            if not self.browser:
                await self._launch(p)
            page = await self.login()
            await page.goto(self.url + "/game", wait_until="networkidle")
            await page.wait_for_selector('a[title="Journal Entries"]')
            print("Getting journal entries")
            self.journal_entries = await page.evaluate(
                "() => { return game.journal.contents.map(j => j.toJSON()) }"
            )
            print("Getting folders")
            self.folders = await page.evaluate(
                '() => { return game.folders.filter(j => j.type === "JournalEntry").map(f => f.toJSON()) }'
            )

    def store_notes(self):
        if not self.journal_entries:
            raise RuntimeError("Journal entries must be downloaded first.")
        for entry in self.journal_entries:
            entry.store("tmp", self.folders)


if __name__ == "__main__":
    f = Foundry(url=sys.argv[1])
    asyncio.run(f.download_notes())
    f.store_notes()
