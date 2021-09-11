#!/usr/bin/env python3

import argparse
import asyncio

from .foundry import Foundry, FoundryJournalEntry, LocalStorage


def validate_args(args):
    """Make sure all arguments required were passed."""
    if args.command == "upload_note":
        if not args.note_path:
            raise RuntimeError("Can not upload a note without --note-path argument.")


async def upload_note(foundry: Foundry, note: FoundryJournalEntry):
    await foundry.upload_note(note)


async def upload_notes(foundry: Foundry, storage: LocalStorage):
    for note in storage.journalentries:
        await upload_note(foundry, note)


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
    "--note-path", dest="note_path", type=str, help="The note to upload."
)
parser.add_argument(
    "--target-format",
    dest="target_format",
    type=str,
    default="org",
    help="The format the notes should be converted to on the local filesystem.",
)
parser.add_argument(
    "command",
    choices=["download_notes", "upload_notes", "upload_note"],
    help="Command to execute. When choosing 'upload_note' '--note-path' must be provided as well.",
)


def main():
    args = parser.parse_args()
    validate_args(args)

    foundry = Foundry(
        url=args.foundry_url, user=args.foundry_user, password=args.foundry_password
    )
    if args.command == "download_notes":
        print("Downloading notes from Foundry.")
        folders, notes = asyncio.run(foundry.download_notes())
        storage = LocalStorage(
            root_directory=args.root_dir,
            format=args.target_format,
            folders=folders,
            journalentries=notes,
        )
        storage.write_all()
    if args.command == "upload_notes":
        storage = LocalStorage.read_all(args.root_dir, args.target_format)
        asyncio.run(upload_notes(foundry, storage))
    if args.command == "upload_note":
        storage = LocalStorage.read_all(args.root_dir, args.target_format)
        note = next(
            filter(
                lambda n: storage.fullpath(n) == args.note_path, storage.journalentries
            )
        )
        print(f"Uploading note: {note}")
        asyncio.run(upload_note(foundry, note))
