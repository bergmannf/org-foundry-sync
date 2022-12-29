#!/usr/bin/env python3

import dataclasses
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
    type: str
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

class LocalStorage:
    def __init__(
            self,
            root_directory: pathlib.Path,
            format: str,
            folders: List[FoundryFolder],
            journalentries: List[FoundryJournalEntry],
    ):
        self.root_directory = root_directory
        self.format = format
        self.folders = folders
        self.journalentries = journalentries
        self.containers = self.folders + self.journalentries

    def read_metadata(self, f: FoundryTypes):
        path = root_path / self.path(folders).with_suffix(".orgfoundrysync")
        if not os.path.exists(path):
            return {}
        with open(path) as metadata:
            return json.load(metadata)

    def write_metadata(self, f: FoundryTypes, metadatapath: str):
        obj = dataclasses.asdict(f)
        with open(metadatapath, "w") as fd:
            fd.write(json.dumps(obj))

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
            metadatapath = fullpath.with_suffix(".folder.foundrysync")
        elif isinstance(f, FoundryJournalEntry):
            os.makedirs(fullpath, exist_ok=True)
            metadatapath = fullpath.with_suffix(".journalentry.foundrysync")
        elif isinstance(f, FoundryJournalEntryPage):
            with open(fullpath, "w") as fd:
                fd.write(pypandoc.convert_text(f.text["content"], self.format, format="html"))
                metadatapath = fullpath.with_suffix(".journalentrypage.foundrysync")
        self.write_metadata(f, metadatapath)

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

    @classmethod
    def construct_metadata(cls, path):
        """Construct the metadata for a JournalEntry from the path.

        Needed for entries that do not yet exists in the Foundry instance and
        have not .foundrysync file.

        """
        notepath = pathlib.Path(path)
        note = {
            "_id": "",
            "folder": "",
            "name": notepath.name.replace(".org", ""),
            "img": "",
            "sort": 0,
        }
        folder = notepath.parent
        folder_path = str(folder.with_suffix(".folder.foundrysync"))
        logger.info(f"Folder for {path} is {folder_path}")
        if os.path.exists(folder_path):
            with open(folder_path, "r") as f:
                foldermeta = json.load(f)
                note["folder"] = foldermeta["_id"]
        else:
            logger.info("Note is in root directory")
        return note

    @classmethod
    def read_all(
        cls,
        root_dir: pathlib.Path,
        source_format: str,
    ) -> Self:
        logger.info(f"Reading local data from {root_dir}")
        folder_paths = glob.glob(str(root_dir / "**/**.folder.foundrysync"),
                                 recursive=True)
        journal_notes_paths = glob.glob(str(root_dir / "**/**.journalentry.foundrysync"),
                                        recursive=True)
        pages = glob.glob(str(root_dir / f"**/**.{source_format}"),
                              recursive=True)
        fs = []
        for f in folder_paths:
            logger.info(f"Reading folder {f}")
            with open(f, "r") as fd:
                fs.append(FoundryFolder(**json.load(fd)))
        js = []
        for f in journal_notes_paths:
            logger.info(f"Reading journal page {f}")
            page_paths = glob.glob(str(f / "/**.journalentrypage.foundrysync"), recursive=True)
            pages = []
            with open(f, "r") as fd:
                c = fd.read()
                for p in page_paths:
                    with open(p, "r") as pd:
                        c = pd.read()
                        if source_format == "org":
                            # Must wrap the @JournalEntry in = signs for code formatting.
                            # Otherwise it will be handled as a ref.
                            c = re.sub(
                                r"=(?P<entry>@(JournalEntry|Actor|Item)\[.*\]{.*})=",
                                r"\g<entry>",
                                c,
                            )
                            c = re.sub(
                                r"(?P<entry>@(JournalEntry|Actor|Item)\[.*\]{.*})",
                                r"=\g<entry>=",
                                c,
                            )
                        content = pypandoc.convert_text(
                            c,
                            "html",
                            format=source_format,
                        )
                        metadatapath = p + ".journalentrypage.foundrysync"
                        page = cls.load_metadata(metadatapath)
                        page.text["content"] = content
                        pages.append(FoundryJournalEntryPage(**page))
                metadatapath = f + ".journalentry.foundrysync"
                if os.path.exists(metadatapath):
                    logger.info("Loading existing journal entry.")
                    entry = cls.load_metadata(metadatapath)
                    js.pages = pages
                    js.append(FoundryJournalEntry(**entry))
                else:
                    logger.info("Found a new journal entry.")
                    entry = cls.construct_metadata(f)
                    js.pages = pages
                    js.append(FoundryJournalEntry(**entry))
        logger.info(f"Read {len(fs)} folders and {len(js)} journal entries.")
        return LocalStorage(root_dir, source_format, fs, js)
