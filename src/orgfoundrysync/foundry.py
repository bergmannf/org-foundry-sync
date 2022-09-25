#!/usr/bin/env python3

import dataclasses
from enum import Enum
import glob
import json
import logging
import pathlib
import re
import os
from typing import Any, Dict, Optional, List, Union, Tuple

from playwright.async_api import Browser
import pypandoc

logger = logging.getLogger("foundry")
logger.setLevel(logging.INFO)


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryFolder:
    _id: str
    name: str
    type: str = "JournalEntry"
    description: Optional[str] = ""
    folder: Optional[str] = ""
    parent: Optional[str] = None
    sorting: Optional[str] = "a"
    sort: Optional[int] = 0
    color: Optional[str] = None
    _stats: Optional[Dict] = dataclasses.field(default_factory=dict, hash=False)
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


class NoteUploadResult(Enum):
    NoteCreated = 0
    NoteUpdated = 1


#  'pages': [{'_id': 'vkgd04b9gIaokMrz',
#             'flags': {},
#             'image': {'caption': None},
#             'name': 'Grondir',
#             'ownership': {'default': -1},
#             'sort': 0,
#             'src': None,
#             'system': {},
#             'text': {'content': '<h1>History</h1>\n'
#                                 '<p>Once a beautiful port town, the city has '
#                                 'been washed away by the '
#                                 '@JournalEntry[Xs3hP2jC0Y2aADE8]{Cataclysm}.</p>\n'
#                                 '<p>Most of the city is now sunken deep into '
#                                 'the bubbling muck that makes up the bay and '
#                                 'is hard to access.</p>\n'
#                                 '<p>If stories can be trusted, corpse eaters '
#                                 'and worse have made a home out of it '
#                                 'nowadays.</p>',
#                      'format': 1,
#                      'markdown': None},
#             'title': {'level': 1, 'show': False},
#             'type': 'text',
#             'video': {'autoplay': None,
#                       'controls': True,
#                       'height': None,
#                       'loop': None,
#                       'timestamp': None,
#                       'volume': 0.5,
#                       'width': None}}],
@dataclasses.dataclass(frozen=True, eq=True):
class FoundryJournalEntryPage:
    _id: str
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    image: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    name: str
    ownership: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    sort: int
    src: Optional[str]
    system: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    text: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    title: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    type: str
    video: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)


@dataclasses.dataclass(frozen=True, eq=True)
class FoundryJournalEntry:
    _id: str
    _stats: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    flags: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    folder: Optional[str]
    name: str
    ownership: Dict[Any, Any] = dataclasses.field(default_factory=dict, hash=False)
    pages: List[FoundryJournalEntryPage]
    sort: int

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
        import pdb; pdb.set_trace()
        self._journal_entries = [FoundryJournalEntry(**entry) for entry in entries]

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

    async def upload_note(self, note: FoundryJournalEntry) -> NoteUploadResult:
        update_note_script = """
        () => {{
        var note = game.journal.filter(j => j.id === "{note_id}")[0];
        var data = note.data;
        data.content = `{note_content}`;
        note.update(data)
        }}
        """
        create_note_script = """
        () => {{
        JournalEntry.create(data = {{"name": "{note_name}", "content": `{note_content}`, "folder": "{note_folder}"}});
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
        folder_path = str(folder) + ".folder.foundrysync"
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
        root_dir: str,
        source_format: str,
    ):
        logger.info(f"Reading local data from {root_dir}")
        folder_paths = glob.glob(root_dir + "/**/**.folder.foundrysync", recursive=True)
        journal_entry_paths = glob.glob(root_dir + "/**/**.org", recursive=True)
        fs = []
        for f in folder_paths:
            logger.info(f"Reading folder {f}")
            with open(f, "r") as fd:
                fs.append(FoundryFolder(**json.load(fd)))
        js = []
        for f in journal_entry_paths:
            logger.info(f"Reading journal entry {f}")
            with open(f, "r") as fd:
                c = fd.read()
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
                metadatapath = f + ".journalentry.foundrysync"
                if os.path.exists(metadatapath):
                    logger.info("Loading existing journal entry.")
                    entry = cls.load_metadata(metadatapath)
                    entry["content"] = content
                    js.append(FoundryJournalEntry(**entry))
                else:
                    logger.info("Found a new journal entry.")
                    entry = cls.construct_metadata(f)
                    entry["content"] = content
                    js.append(FoundryJournalEntry(**entry))
        logger.info(f"Read {len(fs)} folders and {len(js)} journal entries.")
        return LocalStorage(root_dir, source_format, fs, js)
