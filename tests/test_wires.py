import unittest

from application.controller import Controller
from application.pos import Pos
from application.symbol import Wire


class WireTest(unittest.TestCase):
    def setUp(self):
        self.controller = Controller(component_language='en', symbol_set='iec')
        self.controller.on_new()

    def test_disconnected_crossing_and_connected_junction_use_distinct_glyphs(self):
        horizontal = Wire(Wire.manhattan_path(Pos(1, 8), Pos(5, 8)))
        vertical = Wire(Wire.manhattan_path(Pos(3, 6), Pos(3, 10)))
        self.controller.objects = [horizontal, vertical]
        self.controller.on_redraw_grid()
        self.assertEqual(self.controller.grid.cell(Pos(3, 8)), '╳')

        branch = Wire([Pos(3, 8), Pos(3, 9)], connected_start=True)
        self.controller.objects.append(branch)
        self.controller.on_redraw_grid()
        self.assertEqual(self.controller.grid.cell(Pos(3, 8)), 'O')

    def test_terminal_drag_route_connects_two_components(self):
        self.controller.on_component_changed('Resistor')
        self.controller.on_paste_objects(Pos(5, 5))
        first = self.controller.objects[-1]
        self.controller.on_component_changed('Resistor')
        self.controller.on_paste_objects(Pos(15, 5))
        second = self.controller.objects[-1]
        start = next(port for port in first.terminal_positions() if port['direction'] == 'S')
        end = next(port for port in second.terminal_positions() if port['direction'] == 'S')

        self.controller.on_paste_wire(
            start['position'], end['position'],
            start_direction=start['direction'], end_direction=end['direction'],
        )

        wire = next(symbol for symbol in self.controller.objects if getattr(symbol, '_is_wire', False))
        self.assertTrue(wire.connected_start)
        self.assertTrue(wire.connected_end)
        self.assertEqual(self.controller.grid.cell(start['position']), 'O')
        self.assertEqual(self.controller.grid.cell(end['position']), 'O')

    def test_wire_memo_round_trips_path_and_junctions(self):
        wire = Wire(Wire.manhattan_path(Pos(2, 3), Pos(7, 6)), True, False)
        restored = Controller(component_language='en', symbol_set='iec')
        restored.on_new()

        self.assertEqual(restored.play_memo([wire.memo()]), 0)
        loaded = restored.objects[-1]
        self.assertEqual([(p.x, p.y) for p in loaded.path], [(p.x, p.y) for p in wire.path])
        self.assertTrue(loaded.connected_start)
        self.assertFalse(loaded.connected_end)

    def test_moving_a_component_keeps_its_wire_terminal_attached(self):
        self.controller.on_component_changed('Resistor')
        self.controller.on_paste_objects(Pos(5, 5))
        first = self.controller.objects[-1]
        self.controller.on_component_changed('Resistor')
        self.controller.on_paste_objects(Pos(15, 5))
        second = self.controller.objects[-1]
        start = next(port for port in first.terminal_positions() if port['direction'] == 'S')
        end = next(port for port in second.terminal_positions() if port['direction'] == 'S')
        self.controller.on_paste_wire(
            start['position'], end['position'],
            start_direction=start['direction'], end_direction=end['direction'],
        )
        wire = next(symbol for symbol in self.controller.objects if getattr(symbol, '_is_wire', False))
        original_path = [(pos.x, pos.y) for pos in wire.path]

        old_start = Pos(first.startpos.x, first.startpos.y)
        old_end = Pos(first.endpos.x, first.endpos.y)
        new_start = old_start + Pos(5, 0)
        self.controller.on_move_object(first, old_start, old_end, new_start, old_end)
        moved_port = next(port for port in first.terminal_positions() if port['name'] == start['name'])
        self.assertEqual(wire.path[0], moved_port['position'])

        self.controller.on_undo()
        original_port = next(port for port in first.terminal_positions() if port['name'] == start['name'])
        self.assertEqual(wire.path[0], original_port['position'])
        self.assertEqual([(pos.x, pos.y) for pos in wire.path], original_path)
