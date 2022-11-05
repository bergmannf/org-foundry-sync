#!/usr/bin/env python3

import argparse
import asyncio
import logging
import queue

from playwright.async_api import async_playwright

from .foundry import Foundry, LocalStorage, NoteUploadResult
from .dbus_service import start_server
from . import commands

logging.basicConfig()
logger = logging.getLogger("cli")
logger.setLevel(logging.INFO)


def validate_args(args):
    """Make sure all arguments required were passed."""
    pass


parser = argparse.ArgumentParser(description="Download foundryvtt journal notes.")
parser.add_argument(
    "--foundry-user",
    dest="foundry_user",
    default="Gamemaster",
    type=str,
    help="FoundryVTT user to login as.",
)
parser.add_argument(
    "--foundry-password",
    dest="foundry_password",
    default=None,
    type=str,
    help="FoundryVTT password - can also be passed via environment variable FOUNDRY_SYNC_PASSWORD.",
)
parser.add_argument(
    "--foundry-url", dest="foundry_url", type=str, help="FoundryVTT url.", required=True
)
parser.add_argument(
    "--root-dir",
    dest="root_dir",
    default="./tmp",
    type=str,
    help="Root directory under which the notes will be stored.",
)
parser.add_argument(
    "--target-format",
    dest="target_format",
    type=str,
    default="org",
    help="The format the notes should be converted to on the local filesystem.",
)
subparsers = parser.add_subparsers(title="commands", help="commands", dest="command")
upload_note_parser = subparsers.add_parser("upload_note", help="Upload note(s)")
group = upload_note_parser.add_mutually_exclusive_group(required=True)
group.add_argument(
    "--note_path",
    dest="note_path",
    type=str,
    default="",
    action="store",
    help="The note to upload. Path should be absolute or relative to root-dir.",
)
group.add_argument(
    "--all",
    dest="all",
    type=bool,
    default=False,
    help="Upload all notes",
)

download_note_parser = subparsers.add_parser("download_note", help="Download note(s)")
group = download_note_parser.add_mutually_exclusive_group(required=True)
group.add_argument(
    "--note_name",
    dest="note_name",
    type=str,
    default="",
    action="store",
    help="The name of the note to download.",
)
group.add_argument(
    "--all", dest="all", type=bool, default=False, help="Download all notes"
)


def queue_single_command(args, queue):
    """A command was passed on the commandline, so non-interactive use will run a
    single command and exit."""
    if args.command == "upload_note":
        if args.all:
            logger.info("Queue upload all notes")
            queue.put(commands.UploadAllNotes())
        else:
            logger.info("Queue upload single note")
            queue.put(commands.UploadNote(args.note_path))
    if args.command == "download_note":
        if args.all:
            logger.info("Queue download all notes")
            queue.put(commands.DownloadAllNotes())
        else:
            logger.info("Queue download single note")
            queue.put(commands.DownloadNote(args.note_name))
    queue.put(commands.Quit())


def input_loop(queue):
    """No command was passed on the commandline.#!/usr/bin/env python

    Interactive mode will be used."""
    logger.info("Starting input loop")
    while task := input(
        "Enter command ['upload_notes', 'upload_note', 'download_notes', 'download_note', 'quit']: "
    ):
        if task == "upload_notes":
            queue.put(commands.UploadAllNotes)
        if task == "download_notes":
            queue.put(commands.DownloadAllNotes)
        if "upload_note" in task:
            try:
                path = task.split()[1]
                queue.put(commands.UploadNote(path))
            except:
                print("Upload note should contain the path.")
        if "download_note" in task:
            try:
                name = task.split()[1]
                queue.put(commands.DownloadNote(name))
            except:
                print("Download note should contain the note name.")
        if task == "quit":
            queue.put(commands.Quit())
            break


async def process_queue(args, queue: queue.Queue):
    logger.info("Starting processing queue")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        foundry = Foundry(
            url=args.foundry_url,
            user=args.foundry_user,
            password=args.foundry_password,
            browser=browser,
        )
        while task := queue.get():
            logger.info(f"Processing task {task}")
            if isinstance(task, commands.DownloadNote):
                logger.info("Downloading a single note from Foundry.")
                folders, notes = await foundry.download_notes()
                storage = LocalStorage(
                    root_directory=args.root_dir,
                    format=args.target_format,
                    folders=folders,
                    journalentries=notes,
                )
                try:
                    note = next(
                        filter(
                            lambda n: n.name == task.name,
                            storage.journalentries,
                        )
                    )
                    storage.write(note)
                except StopIteration:
                    logger.error(f"Could not find the note {task.path} - check path")
                    continue
            if isinstance(task, commands.DownloadAllNotes):
                logger.info("Downloading notes from Foundry.")
                folders, notes = await foundry.download_notes()
                logger.info("Notes Downloaded")
                storage = LocalStorage(
                    root_directory=args.root_dir,
                    format=args.target_format,
                    folders=folders,
                    journalentries=notes,
                )
                storage.write_all()
                logger.info("Notes stored")
            if isinstance(task, commands.UploadAllNotes):
                storage = LocalStorage.read_all(args.root_dir, args.target_format)
                logger.info("Uploading all notes")
                for note in storage.journalentries:
                    await foundry.upload_note(note)
                logger.info("Uploading finished")
            if isinstance(task, commands.UploadNote):
                logger.info(f"Uploading note {task}")
                storage = LocalStorage.read_all(args.root_dir, args.target_format)
                try:
                    note = next(
                        filter(
                            lambda n: storage.fullpath(n) == task.path,
                            storage.journalentries,
                        )
                    )
                    logger.info(f"Uploading note: {note.name}")
                    logger.debug(f"Content: {note.content}")
                    result = await foundry.upload_note(note)
                    if result == NoteUploadResult.NoteCreated:
                        queue.put(commands.DownloadNote(note.name))
                except StopIteration:
                    logger.error(f"Could not find the note {task.path} - check path")
                    continue
            if isinstance(task, commands.Quit):
                logger.info("Exiting loop.")
                break
        await browser.close()


async def run(args, queue: queue.Queue):
    await start_server(queue)
    loop = asyncio.get_event_loop()
    tasks = []
    if not hasattr(args, "command"):
        tasks.append(loop.run_in_executor(None, input_loop, queue))
    else:
        queue_single_command(args, queue)
    tasks.append(process_queue(args, queue))
    await asyncio.gather(*tasks)


def main():
    commands = queue.Queue()
    arguments = parser.parse_args()
    asyncio.run(run(arguments, commands), debug=True)
