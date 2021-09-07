#!/usr/bin/env python3

import unittest
from orgfoundrysync.foundry import FoundryFolder, foundry_graph, foundry_linearize


class LinearizationTests(unittest.TestCase):
    def test_linearize_no_parents(self):
        f1 = FoundryFolder(_id="1", name="A", parent=None)
        f2 = FoundryFolder(_id="2", name="B", parent=None)
        g = foundry_linearize([f1, f2])
        self.assertEqual(g, [f1, f2])

    def test_linearize_with_parents(self):
        f1 = FoundryFolder(_id="1", name="A", parent="2")
        f2 = FoundryFolder(_id="2", name="B", parent=None)
        g = foundry_linearize([f1, f2])
        self.assertEqual(g, [f2, f1])
        f3 = FoundryFolder(_id="3", name="C", parent="1")
        g = foundry_linearize([f1, f2, f3])
        self.assertEquals(g, [f2, f1, f3])
