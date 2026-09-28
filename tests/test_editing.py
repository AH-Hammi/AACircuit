# NB to be run with nose, this .py should _not_ be executable (chmod -x)

import unittest

from PySide6.QtWidgets import QApplication, QPushButton

from application import INSERT, REMOVE
from application.controller import Controller
from application.pos import Pos


class EditingTest(unittest.TestCase):

    def test_copy_grid_button_copies_ascii_to_clipboard(self):
        c = Controller(component_language='en', symbol_set='iec')
        c.on_copy_grid()

        self.assertIsNotNone(c.gui.findChild(QPushButton, 'copy_grid_button'))
        self.assertEqual(QApplication.clipboard().text(), c.grid.content_as_str())

    def test_insert_remove(self):

        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()

        # NB test should be run against the default (en_US) component library
        c.on_component_changed('AND gate')
        c.on_paste_objects(Pos(4, 2))

        c.on_component_changed('NAND gate')
        c.on_paste_objects(Pos(14, 2))

        filename = 'tmp/test_edit_insert.aac'
        self.assertTrue(c.on_write_to_file(filename))

        rect = (Pos(4, 2), Pos(5, 3))
        c.on_cut(rect)

        filename = 'tmp/test_edit_remove.aac'
        self.assertTrue(c.on_write_to_file(filename))

    def test_cols(self):

        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()

        grid = c.grid

        nr_cols_before = grid.nr_cols

        # private methods do change the grid dimensions
        grid._insert_col(3)
        self.assertEqual(grid.nr_cols, nr_cols_before + 1)

        grid._remove_col(3)
        self.assertEqual(grid.nr_cols, nr_cols_before)

        # the grid dimensions should stay the same
        c.on_grid_col(3, INSERT)
        self.assertEqual(grid.nr_cols, nr_cols_before)

        c.on_grid_col(3, REMOVE)
        self.assertEqual(grid.nr_cols, nr_cols_before)

        c.on_grid_col(3, REMOVE)
        c.on_grid_col(3, INSERT)
        self.assertEqual(grid.nr_cols, nr_cols_before)

        c.on_grid_col(3, REMOVE)
        c.on_undo()
        self.assertEqual(grid.nr_cols, nr_cols_before)

    def test_rows(self):

        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()
        grid = c.grid

        nr_rows_before = c.grid.nr_rows

        # private methods do change the grid dimensions
        grid._insert_row(3)
        self.assertEqual(grid.nr_rows, nr_rows_before + 1)

        grid._remove_row(3)
        self.assertEqual(grid.nr_rows, nr_rows_before)

        # the grid dimensions should stay the same
        c.on_grid_row(3, INSERT)
        self.assertEqual(grid.nr_rows, nr_rows_before)

        c.on_grid_row(3, REMOVE)
        self.assertEqual(grid.nr_rows, nr_rows_before)

        c.on_grid_row(3, REMOVE)
        c.on_grid_row(3, INSERT)
        self.assertEqual(grid.nr_rows, nr_rows_before)

        c.on_grid_row(3, REMOVE)
        c.on_undo()
        self.assertEqual(grid.nr_rows, nr_rows_before)

    def test_erase(self):

        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()

        # NB test should be run against the default (en_US) component library
        c.on_component_changed('AND gate')
        c.on_paste_objects(Pos(4, 2))

        c.on_eraser_selected((5, 5))
        c.on_paste_objects(Pos(5, 2))

        filename = 'tmp/test_edit_erase.aac'
        self.assertTrue(c.on_write_to_file(filename))

    def test_duplicate(self):

        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()

        # NB test should be run against the default (en_US) component library
        c.on_component_changed('AND gate')
        c.on_paste_objects(Pos(4, 2))

        c.on_component_changed('NAND gate')
        c.on_paste_objects(Pos(4, 2))

        rect = (Pos(4, 2), Pos(5, 3))
        c.on_cut(rect)

        filename = 'tmp/test_edit_duplicate.aac'
        self.assertTrue(c.on_write_to_file(filename))

    def test_component_can_be_selected_moved_and_undone(self):
        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()
        c.on_component_changed('AND gate')
        c.on_paste_objects(Pos(4, 2))
        symbol = c.objects[-1]

        c.on_select_object_at(Pos(6, 4))
        self.assertIs(c.selected_objects[0].symbol, symbol)

        old_start = Pos(symbol.startpos.x, symbol.startpos.y)
        old_end = Pos(symbol.endpos.x, symbol.endpos.y)
        new_start = Pos(9, 4)
        new_end = Pos(old_end.x, old_end.y)
        c.on_move_object(symbol, old_start, old_end, new_start, new_end)
        self.assertEqual(symbol.startpos, new_start)
        self.assertEqual(c.grid.cell(Pos(11, 6)), '&')
        self.assertEqual(c.grid.cell(Pos(6, 4)), ' ')

        c.on_undo()
        self.assertEqual(symbol.startpos, old_start)
        self.assertEqual(c.grid.cell(Pos(6, 4)), '&')
        c.on_redo()
        self.assertEqual(symbol.startpos, new_start)

    def test_multiple_move_undo_redo_and_new_edit_history(self):
        c = Controller(component_language='en', symbol_set='iec')
        c.on_new()
        c.on_component_changed('AND gate')
        c.on_paste_objects(Pos(4, 2))
        symbol = c.objects[-1]
        old_end = Pos(symbol.endpos.x, symbol.endpos.y)

        first = Pos(8, 2)
        c.on_move_object(symbol, Pos(4, 2), old_end, first, old_end)
        second = Pos(12, 2)
        c.on_move_object(symbol, first, old_end, second, old_end)
        c.on_undo()
        c.on_undo()
        self.assertEqual(symbol.startpos, Pos(4, 2))

        c.on_redo()
        self.assertEqual(symbol.startpos, first)
        self.assertTrue(c.undone_action)
        c.on_redo()
        self.assertEqual(symbol.startpos, second)

        c.on_undo()
        c.on_paste_line(Pos(1, 20), Pos(5, 20), 0)
        self.assertFalse(c.undone_action)

    def test_wire_tool_remains_active_and_highlighted_after_drawing(self):
        c = Controller(component_language='en', symbol_set='iec')
        button = c.gui.tool_buttons['line_1']
        button.click()

        grid_view = c.gui.grid_view
        width = 10
        height = 16
        for start_x in (5, 12):
            grid_view.on_drag_begin(None, start_x * width, 5 * height)
            grid_view.on_drag_update(None, 4 * width, 0)
            grid_view.on_drag_end(None, 4 * width, 0)

        self.assertTrue(button.isChecked())
        self.assertEqual(grid_view._selection.state, 0)
        self.assertEqual(sum(symbol.is_line for symbol in c.objects), 2)
