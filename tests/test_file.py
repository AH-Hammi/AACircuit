import unittest
from pathlib import Path

from application.controller import Controller
from application.pos import Pos


class FileTest(unittest.TestCase):
    def test_component_name_round_trip(self):
        controller = Controller(component_language='en', symbol_set='iec')
        symbol = controller.complib.get_symbol('D-FF,JK-FF')
        symbol.startpos = Pos(4, 2)
        symbol.ori = 1
        symbol.mirrored = 1
        controller.objects.append(symbol)
        symbol.paste(controller.grid)

        filename = 'tmp/component-name.aac'
        self.assertTrue(controller.on_write_to_file(filename))

        reopened = Controller(component_language='de', symbol_set='iec')
        self.assertTrue(reopened.on_read_from_file(filename))
        saved_symbol = next(item for item in reopened.objects if item.is_symbol)

        self.assertEqual(saved_symbol.component_key, 'D-FF,JK-FF')
        self.assertEqual(saved_symbol.ori, 1)
        self.assertEqual(saved_symbol.mirrored, 1)
        self.assertEqual(saved_symbol.startpos, Pos(4, 2))

    def test_symbol_standard_change_rerenders_current_drawing(self):
        controller = Controller(component_language='en', symbol_set='iec')
        symbol = controller.complib.get_symbol('OR gate')
        symbol.startpos = Pos(8, 4)
        controller.objects.append(symbol)
        symbol.paste(controller.grid)
        iec_grid = symbol.grid
        original_size = (controller._cols, controller._rows)

        controller.on_symbol_set_changed('ansi_ieee')

        ansi_symbol = next(item for item in controller.objects if item.component_key == 'OR gate')
        self.assertEqual(controller.complib.symbol_set, 'ansi_ieee')
        self.assertNotEqual(ansi_symbol.grid, iec_grid)
        self.assertEqual(ansi_symbol.startpos, Pos(8, 4))
        self.assertEqual((controller._cols, controller._rows), original_size)
        self.assertFalse(controller.latest_action)
        self.assertFalse(controller.undone_action)

    def test_read_ascii(self):
        controller = Controller(component_language='en', symbol_set='iec')
        controller.on_new()
        self.assertTrue(controller.on_load_ascii_from_file('tests/files/test_ascii.txt'))

        controller.on_paste_objects(Pos(0, 0))
        self.assertTrue(controller.on_write_to_file('tmp/test_ascii.aac'))

    def test_export_ascii(self):
        controller = Controller(component_language='en', symbol_set='iec')
        symbol = controller.complib.get_symbol('Resistor')
        symbol.startpos = Pos(10, 10)
        controller.objects.append(symbol)
        symbol.paste(controller.grid)

        filename = 'tmp/test_all.txt'
        controller.on_export_as_ascii(filename)
        self.assertTrue(Path(filename).is_file())
