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
