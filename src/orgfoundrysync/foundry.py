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
    type: Optional[str] = ""
    metadata_type: str = "Folder"

    def get_parent(self):
        return self.parent


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryJournalEntryPage:
    _id: str
    name: str
    sort: int
    src: Optional[str]
    metadata_type: str = "JournalEntryPage"
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    image: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    ownership: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    system: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    text: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    type: Optional[str] = ""
    title: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    video: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)

    def get_parent(self):
        return None


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
    metadata_type: str = "JournalEntry"

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

    def create_upload_script(self, note: FoundryJournalEntry) -> str:
        CREATE_ENTRY="""let entry = JournalEntry.create(data = {{"name": "{note.name}", "folder": "{note.folder}"}});"""
        FIND_ENTRY="""let entry = game.journal.filter(j => j.id === "{note._id}")[0];"""

        CREATE_PAGE="""
        entry.createEmbeddedDocuments("JournalEntryPage", [{{
            name: "{page.name}",
            type: "text",
            text: {{
                content: "{page.text[content]}",
                format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML
            }}
        }}]);
        """
        UPDATE_PAGE="""
        const page = entry.pages.find(p => p._id === "{page._id}");
        page?.update({{content: "{page.text[content]}"}});
        """
        if not note._id:
            logger.info(f"Creating a new note for: {note.name}")
            entry_script = CREATE_ENTRY.format(note=note)
        else:
            entry_script = FIND_ENTRY.format(note=note)
        page_script = ""
        for page in note.pages:
            import pdb; pdb.set_trace()
            if not page._id:
                logger.info(f"Creating a new page for: {page.name}")
                page_script += CREATE_PAGE.format(page=page)
            else:
                page_script += UPDATE_PAGE.format(page=page)
        script = f"""() => {{
        {entry_script}
        {page_script}
        }}"""
        return script

    async def upload_note(self, note: FoundryJournalEntry):
        script = self.create_upload_script(note)
        page = await self.login()
        if not self.journal_entries:
            await self.download_notes()
        await page.goto(self.url + "/game", wait_until="networkidle", timeout=60000)
        await page.wait_for_selector('a[title="Journal Entries"]')
        await page.evaluate(script)


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
                    (f.name, f.metadata_type)
                )
                rows = result.fetchall()
                if len(rows) == 0:
                    logger.info(f"Did not find any metadata for '{f.name}' ({f.metadata_type})")
                    raise RuntimeError("No metadata objects found")
                elif len(rows) > 1:
                    logger.info(f"Expected one row of metadata for '{f.name}' ({f.metadata_type}), but got {len(rows)}.")
                    raise RuntimeError("Too many fitting metadata objects found")
                row = rows[0]
                return json.loads(row[0])

    def write(self, f: FoundryTypes):
        logger.info(f"Writing metadata for '{f.name}' ({f.metadata_type})")
        obj = dataclasses.asdict(f)
        with closing(sqlite3.connect(self.dbpath)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO foundrymetadata (name, type, data) VALUES (?, ?, ?)",
                    (f.name, f.metadata_type, json.dumps(obj)))

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

    # Need to be able to pass in the parent as an additional type, as the
    # JournalEntryPages do *not* keep a reference to the JournalEntry they are
    # contained in.
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
            logger.info("Writing folder: %s", fullpath)
            os.makedirs(fullpath, exist_ok=True)
        elif isinstance(f, FoundryJournalEntry):
            logger.info("Writing entry: %s", fullpath)
            os.makedirs(fullpath, exist_ok=True)
        elif isinstance(f, FoundryJournalEntryPage):
            with open(fullpath.with_suffix("." + self.format), "w") as fd:
                logger.info("Writing page: %s", fullpath)
                fd.write(pypandoc.convert_text(
                    f.text["content"],
                    self.format,
                    format="html"))
        self.write_metadata(f)

    def write_all(self):
        """Write all FoundryObjects to the filesystem."""
        for folder in self.folders:
            self.write(folder)
        for note in self.journalentries:
            self.write(note)
            fullpath = self.fullpath(note)
            for page in note.pages:
                self.write(page, fullpath / self.path(page))

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
                id = parent['_id']
            else:
                logger.error(f"Can not find parent for new entry: {entry.absolute()}")
        return FoundryJournalEntry(None, id, entry.name, [], False)

    def make_page(self, page: pathlib.Path):
        return FoundryJournalEntryPage(None, page.name, False, None)

    def read_all(self) -> Self:
        folders = set()
        entries = dict()
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
                if child.parent.name in entries:
                    parent_entry = entries[child.parent.name]
                else:
                    parent_entry_metadata = self.read_metadata(
                        FoundryJournalEntry(None, child.parent.parent.name,
                                            child.parent.name, [], False))
                    if not parent_entry_metadata:
                        logger.info(f"Did not find matching metadata for entry: {child.parent.name}")
                        parent_entry = self.make_entry(child.parent)
                    else:
                        parent_entry = FoundryJournalEntry(**parent_entry_metadata)
                        # Metadata loaded entries contain the pages as dicts already
                        parent_entry.pages.clear()
                    entries[parent_entry.name] = parent_entry
                tmp_page = FoundryJournalEntryPage(
                    None, child.name.split(".")[0],
                    False, "")
                page_metadata = self.read_metadata(tmp_page)
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
        return LocalStorage(self.root_directory,
                            self.format,
                            folders,
                            entries.values())
