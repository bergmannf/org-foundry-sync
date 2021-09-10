#!/usr/bin/env python3

import unittest
from orgfoundrysync.foundry import FoundryFolder, FoundryJournalEntry


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.root = FoundryFolder(_id="1", name="a", parent=None)
        self.root_child = FoundryFolder(_id="2", name="b", parent="1")
        self.root_child2 = FoundryFolder(_id="3", name="c", parent="1")
        self.entry = FoundryJournalEntry(
            _id="1", name="d", folder="3", content="<h1>Hi</h1>", img=None, sort=None
        )
        self.all_folders = [self.root, self.root_child, self.root_child2]

    def test_path(self):
        self.assertEqual(self.root.path(self.all_folders), "a")
        self.assertEqual(self.root_child.path(self.all_folders), "a/b")
        self.assertEqual(self.entry.path(self.all_folders), "a/c/d.org")
