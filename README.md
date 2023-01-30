# org-foundry-sync

A small tool that allows download
[JournalEntry](https://foundryvtt.com/api/data.JournalEntryData.html) from
[FoundryVTT](https://foundryvtt.com/api/data.JournalEntryData.html).

It will recreate the folder structure from foundryvtt on the filesystem and
convert the nodes to emacs [org-mode](https://orgmode.org/) format.

## Requirements

To run the script the following tools are required on the machine:

- [pandoc](https://pandoc.org/)
- [playwright](https://playwright.dev/)

Before running the script the environment variable `FOUNDRY_SYNC_PASSWORD`
should be set to the correct password.

## Examples

Download all notes in org-mode format:

``` shell
orgfoundrysync --foundry-user Gamemaster \
    --foundry-url '<foundry_url>' \
    --root-dir '/tmp/foundry' \
    --target-format org \
    download_note --all ALL
```

Upload a note back to foundry:

``` shell
orgfoundrysync --foundry-user Gamemaster \
    --foundry-url '<foundry_url>' \
    --root-dir '/tmp/foundry' \
    --target-format org \
    upload_note --note_path /tmp/foundry/<path_to_note_under_root>
```

Right now after uploading a note (especially if it's a newly created one) it is
required to download the note again, so the metadata in the database is populated.
