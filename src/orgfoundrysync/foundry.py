#!/usr/bin/env python3

import asyncio
import dataclasses
import queue
import graphlib
import os
import sys
from typing import Any, Dict, Optional, List, Union

from playwright.async_api import async_playwright


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

    def store(self):
        pass


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

    def store(self):
        pass


def foundry_linearize(fs: List[Union[FoundryFolder, FoundryJournalEntry]]):
    """Build a linearization for Foundry dataclasses.

    In this case all instances should come before their childrens.

    :returns: List[FoundryClass]
    """
    ordering: List = []
    q = queue.Queue()
    for f in fs:
        q.put(f)
    while not q.empty():
        f = q.get(True)
        if f.parent:
            if f.parent not in g:
                q.put(f)
            else:
                ordering.append(f)
        else:
            ordering.append(f)
    return ordering


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
        for folder in self.folders:
            store_folder(folder)

        for entry in self.journal_entries:
            store_journal_entry(entry)


if __name__ == "__main__":
    f = Foundry(url=sys.argv[1])
    asyncio.run(f.download_notes())
    f.store_notes()
