#!/usr/bin/env python3

import unittest
from orgfoundrysync.foundry import FoundryFolder


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.root = FoundryFolder(_id="1", name="a", parent=None)
        self.root_child = FoundryFolder(_id="2", name="b", parent="1")
        self.root_child2 = FoundryFolder(_id="3", name="c", parent="1")
        self.all_folders = [self.root, self.root_child, self.root_child2]

    def test_path(self):
        self.assertEqual(self.root.path(self.all_folders), "a")
        self.assertEqual(self.root_child.path(self.all_folders), "a/b")

    def test_store(self):
        self.root.store("", self.all_folders)
