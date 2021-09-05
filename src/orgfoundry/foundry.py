#!/usr/bin/env python3

import asyncio
import os
import sys

from playwright.async_api import async_playwright


def store_folder(f):
    print(f"Making folder {f}")


def store_journal_entry(e):
    print(f"Storing journal entry {e}")


class Foundry:
    def __init__(self, url):
        self.url = url
        self.browser = None
        self.folders = None
        self.journal_entries = None

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
            await page.fill("input[name=password]", os.getenv("FOUNDRY_GM"))
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
