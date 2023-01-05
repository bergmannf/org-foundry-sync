#!/usr/bin/env python3

from contextlib import closing
import dataclasses
import sqlite3
from enum import Enum
import glob
import json
import logging
import pathlib
import re
import os
from typing import Any, Dict, Optional, List, Union, Self, TypeAlias

from playwright.async_api import Browser
import pypandoc

logger = logging.getLogger("foundry")
logger.setLevel(logging.INFO)


class NoteUploadResult(Enum):
    NoteCreated = 0
    NoteUpdated = 1


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryFolder:
    """Represents a folder in the VTT."""
    _id: str
    name: str
    _stats: Optional[Dict] = dataclasses.field(default_factory=dict, hash=False)
    color: Optional[str] = None
    description: Optional[str] = ""
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    folder: Optional[str] = ""
    parent: Optional[str] = None
    sort: Optional[int] = 0
    sorting: Optional[str] = ""
    type: str = "JournalEntry"

    def get_parent(self):
        return self.parent


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryJournalEntryPage:
    _id: str
    name: str
    sort: int
    src: Optional[str]
    type: str = "JournalEntryPage"
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    image: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    ownership: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    system: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    text: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    title: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    video: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)

    def get_parent(self):
        return self.folder


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryJournalEntry:
    _id: str
    folder: Optional[str]
    name: str
    pages: List[FoundryJournalEntryPage]
    sort: int
    _stats: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    ownership: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    type: str = "JournalEntry"

    def get_parent(self):
        return self.folder


class Foundry:
    def __init__(self, url, browser: Browser, user="Gamemaster", password=None):
        self.url = url
        self.password = password or os.getenv("FOUNDRY_SYNC_PASSWORD")
        if not self.password:
            raise RuntimeError("Can not login to FoundryVTT without a password.")
        self.user = user
        self.browser = browser
        self._page = None
        self._folders = []
        self._journal_entries = []

    @property
    def folders(self) -> List[FoundryFolder]:
        return self._folders

    @folders.setter
    def folders(self, folders):
        self._folders = [FoundryFolder(**folder) for folder in folders]

    @property
    def journal_entries(self) -> List[FoundryJournalEntry]:
        return self._journal_entries

    @journal_entries.setter
    def journal_entries(self, entries):
        _entries = []
        for entry in entries:
            journal_pages = [FoundryJournalEntryPage(**page) for page in
                             entry["pages"]]
            entry["pages"] = journal_pages
            journal_entry = FoundryJournalEntry(**entry)
            _entries.append(journal_entry)
        self._journal_entries = _entries

    def journal_entry_exists(self, entry):
        for e in self.journal_entries:
            if e._id == entry._id:
                logger.info(f"Journal Entry {entry.name} already exists.")
                return True
        logger.info(f"Journal Entry {entry.name} does not exist yet.")
        return False

    async def login(self):
        # If the page is already set we should be logged in already
        if self._page:
            return self._page
        context = await self.browser.new_context()
        self._page = await context.new_page()
        await self._page.goto(self.url + "/join")
        await self._page.select_option("select[name=userid]", label=self.user)
        await self._page.fill("input[name=password]", self.password)
        await self._page.click("button[name=join]")
        return self._page

    async def download_notes(self):
        page = await self.login()
        await page.goto(self.url + "/game", wait_until="networkidle")
        await page.wait_for_selector('a[data-tooltip="DOCUMENT.JournalEntries"]')
        logger.info("Downloading folders")
        self.folders = await page.evaluate(
            '() => { return game.folders.filter(j => j.type === "JournalEntry").map(f => f.toJSON()) }'
        )
        logger.info("Downloading journal entries")
        self.journal_entries = await page.evaluate(
            "() => { return game.journal.contents.map(j => j.toJSON()) }"
        )
        return [self.folders, self.journal_entries]

    async def upload_note(self, note: FoundryJournalEntry, pages: List[FoundryJournalEntryPage]) -> NoteUploadResult:
        update_note_script = """
        () => {{
        var note = game.journal.filter(j => j.id === "{note_id}")[0];
        const page = note.pages.find(p => p.type === "text" && p.name === "{page_name}");
        if page {
            page.update({content: "{page_content}"});
        } else {
            note.createEmbeddedDocuments("JournalEntryPage", [{
            name: "{page_name}",
            type: "text",
            text: {
                content: "{page_content}",
                format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML
            }
            }]);
        }
        }}
        """
        create_note_script = """
        () => {{
        let entry = JournalEntry.create(data = {{"name": "{note_name}", folder": "{note_folder}"}});
        entry.createEmbeddedDocuments("JournalEntryPage", [{
        name: "{note_name}",
        type: "text",
        text: {
            content: "{note_content}",
            format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML
        }
        }]);
        }}
        """
        page = await self.login()
        if not self.journal_entries:
            await self.download_notes()
        if self.journal_entry_exists(note):
            script = update_note_script.format(
                note_id=note._id, note_content=note.content
            )
            result = NoteUploadResult.NoteUpdated
        else:
            # FIXME: After creating a new note a task should be queued to update the local storage
            script = create_note_script.format(
                note_name=note.name, note_content=note.content, note_folder=note.folder
            )
            logger.info(script)
            result = NoteUploadResult.NoteCreated
        await page.goto(self.url + "/game", wait_until="networkidle", timeout=60000)
        await page.wait_for_selector('a[title="Journal Entries"]')
        await page.evaluate(script)
        return result


FoundryTypes: TypeAlias = Union[FoundryFolder, FoundryJournalEntry,
                                FoundryJournalEntryPage]

class MetadataStorage:
    def __init__(self, root_directory: pathlib.Path,
                 dbname: str = "orgfoundrysync-metadata.db"):
        self.root_directory = root_directory
        self.dbname = dbname
        self.dbpath = self.root_directory / self.dbname
        self.init_database()

    def init_database(self):
        with closing(sqlite3.connect(self.dbpath)) as connection:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS foundrymetadata (name varchar(32), type varchar(64), data json)")

    def read(self, f: FoundryTypes) -> dict[Any, Any]:
        with closing(sqlite3.connect(self.dbpath)) as connection:
            with connection:
                result = connection.execute(
                    "SELECT data FROM foundrymetadata WHERE name = (?) AND type = (?)",
                    (f.name, f.type)
                )
                rows = result.fetchall()
                if len(rows) == 0:
                    logger.info(f"Did not find any metadata for name {f.name} and type {f.type}.")
                    raise RuntimeError("No metadata objects found")
                elif len(rows) > 1:
                    logger.info(f"Expected one row of metadata for name {f.name} and type {f.type}, but got {len(rows)}.")
                    raise RuntimeError("Too many fitting metadata objects found")
                row = rows[0]
                return json.loads(row[0])

    def write(self, f: FoundryTypes):
        obj = dataclasses.asdict(f)
        with closing(sqlite3.connect(self.dbpath)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO foundrymetadata (name, type, data) VALUES (?, ?, ?)",
                    (f.name, f.type, json.dumps(obj)))

class LocalStorage:
    def __init__(
            self,
            root_directory: pathlib.Path,
            format: str,
            folders: List[FoundryFolder] = None,
            journalentries: List[FoundryJournalEntry] = None,
    ):
        self.root_directory = root_directory
        self.format = format
        self.folders = folders if folders else []
        self.journalentries = journalentries if journalentries else []
        self.metadatastorage = MetadataStorage(root_directory)

    def read_metadata(self, f: FoundryTypes):
        # TODO: read metadata based on type
        try:
            meta = self.metadatastorage.read(f)
            return meta
        except RuntimeError:
            return None

    def write_metadata(self, f: FoundryTypes):
        self.metadatastorage.write(f)

    def path(self, f: FoundryTypes):
        parents = [f]
        tmp = f
        while tmp.get_parent():
            p = [p for p in self.folders if p._id == tmp.get_parent()][0]
            parents.insert(0, p)
            tmp = p
        parents = [pathlib.Path(p.name) for p in parents]
        return pathlib.PurePath(*parents)

    def fullpath(self, f: Union[FoundryFolder, FoundryJournalEntry]):
        return self.root_directory / self.path(f)

    def write(self, f: Union[FoundryFolder, FoundryJournalEntry,
                             FoundryJournalEntryPage],
              fullpath: pathlib.Path = None):
        """Write a single FoundryObject to the fileysstem."""
        if not fullpath:
            fullpath = self.fullpath(f)
        # TODO: Extract into polymorphism
        if isinstance(f, FoundryFolder):
            os.makedirs(fullpath, exist_ok=True)
        elif isinstance(f, FoundryJournalEntry):
            os.makedirs(fullpath, exist_ok=True)
        elif isinstance(f, FoundryJournalEntryPage):
            with open(fullpath, "w") as fd:
                fd.write(pypandoc.convert_text(f.text["content"], self.format, format="html"))
        self.write_metadata(f)

    def write_all(self):
        """Write all FoundryObjects to the filesystem."""
        for f in self.folders:
            self.write(f)
        for n in self.journalentries:
            self.write(n)
            fullpath = self.fullpath(n)
            for p in n.pages:
                self.write(p, "/".join([fullpath, p.path(self.format)]))

    @classmethod
    def load_metadata(cls, path):
        """Load the metadata for a JournalEntry from the metadata file."""
        with open(path, "r") as f:
            return json.load(f)

    def construct_metadata(self, path):
        """Construct the metadata for a JournalEntry from the path.

        Needed for entries that do not yet exists in the Foundry instance and
        have not .foundrysync file.

        """
        notepath = pathlib.Path(path)
        note = {
            "_id": "",
            "folder": "",
            "name": notepath.name.replace(self.format, ""),
            "img": "",
            "sort": 0,
        }
        folder = notepath.parent
        try:
            foldermeta = self.read_metadata(FoundryFolder(name=folder.name))
            note["folder"] = foldermeta["_id"]
        except:
            logger.info("Note is in root directory")
        return note

    def make_folder(self, folder: pathlib.Path):
        id = None
        if folder.parent != self.root_directory:
            parent = self.read_metadata(FoundryFolder(None, folder.parent.name))
            if parent:
                id = parent['id']
            else:
                logger.error(f"Can not find parent for new folder: {folder.absolute()}")
        return FoundryFolder(None, folder.name, folder=id)

    def make_entry(self, entry: pathlib.Path):
        id = None
        if entry.parent != self.root_directory:
            parent = self.read_metadata(FoundryFolder(None, entry.parent.name))
            if parent:
                id = parent['id']
            else:
                logger.error(f"Can not find parent for new entry: {entry.absolute()}")
        return FoundryJournalEntry(None, id, entry.name, [], False)

    def make_page(self, page: pathlib.Path):
        return FoundryJournalEntryPage(None, page.name, False, None)


    def read_all(self) -> Self:
        folders = set()
        entries = set()
        for child in self.root_directory.rglob("*"):
            logger.info(f"Loading {child.absolute()}")
            if child.absolute() == self.metadatastorage.dbpath:
                logger.info("Skipping database file.")
                continue
            if child.is_dir() and not any([c.is_file() for c in child.iterdir()]):
                folder_metadata = self.read_metadata(FoundryFolder(None, child.name))
                if not folder_metadata:
                    logger.info(f"Did not find matching metadata for folder: {child.name}")
                    folder = self.make_folder(child)
                else:
                    folder = FoundryFolder(**folder_metadata)
                folders.add(folder)
            if child.is_file():
                parent_entry_metadata = self.read_metadata(FoundryJournalEntry(None, child.parent.parent.name, child.parent.name, [], False))
                if not parent_entry_metadata:
                    logger.info(f"Did not find matching metadata for entry: {child.parent.name}")
                    parent_entry = self.make_entry(child.parent)
                else:
                    parent_entry = FoundryJournalEntry(**parent_entry_metadata)
                page_metadata = self.read_metadata(FoundryJournalEntryPage(None, child.name, False, ""))
                if not page_metadata:
                    logger.info(f"Did not find matching metadata for page: {child.name}")
                    page = self.make_page(child)
                else:
                    page = FoundryJournalEntryPage(**page_metadata)
                content = child.read_text()
                if self.format == "org":
                    # Must wrap the @JournalEntry in = signs for code formatting.
                    # Otherwise it will be handled as a ref.
                    content = re.sub(
                        r"=(?P<entry>@(JournalEntry|Actor|Item)\[.*\]{.*})=",
                        r"\g<entry>",
                        content,
                    )
                    content = re.sub(
                        r"(?P<entry>@(JournalEntry|Actor|Item)\[.*\]{.*})",
                        r"=\g<entry>=",
                        content,
                    )
                content = pypandoc.convert_text(
                    content,
                    "html",
                    format=self.format,
                )
                page.text["content"] = content
                parent_entry.pages.append(page)
        return LocalStorage(self.root_directory, self.format, folders, entries)
