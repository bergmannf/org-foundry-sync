#!/usr/bin/env python3

import unittest
from orgfoundrysync.foundry import FoundryFolder, foundry_graph


class GraphTests(unittest.TestCase):
    def test_build_graph(self):
        f1 = FoundryFolder(_id="1", name="A", parent=None)
        f2 = FoundryFolder(_id="2", name="B", parent=None)
        g = foundry_graph([f1, f2])
        self.assertEqual(g, {f1: [], f2: []})
