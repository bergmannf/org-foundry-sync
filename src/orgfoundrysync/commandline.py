#!/usr/bin/env python3

import argparse
import asyncio

from playwright.async_api import async_playwright

from .foundry import Foundry, LocalStorage


def validate_args(args):
    """Make sure all arguments required were passed."""
    if args.command == "upload_note":
        if not args.note_path:
            raise RuntimeError("Can not upload a note without --note-path argument.")


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


async def run(args):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        foundry = Foundry(
            url=args.foundry_url,
            user=args.foundry_user,
            password=args.foundry_password,
            browser=browser,
        )
        if args.command == "download_notes":
            print("Downloading notes from Foundry.")
            folders, notes = await foundry.download_notes()
            print("Notes Downloaded")
            storage = LocalStorage(
                root_directory=args.root_dir,
                format=args.target_format,
                folders=folders,
                journalentries=notes,
            )
            storage.write_all()
            print("Notes stored")
        if args.command == "upload_notes":
            storage = LocalStorage.read_all(args.root_dir, args.target_format)
            print("Uploading all notes")
            for note in storage.journalentries:
                await foundry.upload_note(note)
            print("Uploading finished")
        if args.command == "upload_note":
            storage = LocalStorage.read_all(args.root_dir, args.target_format)
            try:
                note = next(
                    filter(
                        lambda n: storage.fullpath(n) == args.note_path,
                        storage.journalentries,
                    )
                )
                print(f"Uploading note: {note}")
                await foundry.upload_note(note)
            except StopIteration:
                print(f"Could not find the note {args.note_path} - check path")
                exit(1)
        await browser.close()


def main():
    args = parser.parse_args()
    validate_args(args)

    asyncio.run(run(args), debug=True)
