# NB to be run with nose, this .py should _not_ be executable (chmod -x)

import unittest

from application.pos import Pos


class PosTest(unittest.TestCase):

    def test_in_rect(self):

        a = Pos(10, 15)
        b = Pos(12, 21)

        ul = Pos(9, 14)
        br = Pos(12, 20)
        r = (ul, br)

        self.assertTrue(a.in_rect(r))
        self.assertFalse(b.in_rect(r))

    def test_comparison(self):

        a = Pos(10, 15)
        b = Pos(12, 21)
        c = Pos(12, 21)

        self.assertTrue(a < b)
        self.assertFalse(a > b)

        self.assertTrue(a <= b)
        self.assertFalse(a >= b)

        self.assertTrue(b == c)
        self.assertFalse(a == b)

    def test_conversion(self):

        a = Pos(10, 15)
        b = Pos(12, 21)

        tmp = a.grid_cr()
        self.assertEqual(tmp.x, 1)
        self.assertEqual(tmp.y, 0)

        tmp = a.view_xy()
        self.assertEqual(tmp.x, 100)
        self.assertEqual(tmp.y, 240)

        a.snap_to_grid()
        self.assertEqual(a.x, 10)
        self.assertEqual(a.y, 0)

        b = Pos(10, 16)

        tmp = b.grid_cr()
        self.assertEqual(tmp.x, 1)
        self.assertEqual(tmp.y, 1)

        tmp = b.view_xy()
        self.assertEqual(tmp.x, 100)
        self.assertEqual(tmp.y, 256)

        b.snap_to_grid()
        self.assertEqual(b.x, 10)
        self.assertEqual(b.y, 16)

        c = Pos(11, 17)

        tmp = c.grid_cr()
        self.assertEqual(tmp.x, 1)
        self.assertEqual(tmp.y, 1)

        tmp = c.view_xy()
        self.assertEqual(tmp.x, 110)
        self.assertEqual(tmp.y, 272)

        c.snap_to_grid()
        self.assertEqual(c.x, 10)
        self.assertEqual(c.y, 16)
