"""
AACircuit.py
2020-03-02 JvO
"""

import collections
import heapq
import json
import os
import re

from pubsub import pub
from PySide6.QtWidgets import QApplication

from application import (
    ARROW,
    CHARACTER,
    COL,
    COMPONENT,
    DIR_LINE,
    DRAW_RECT,
    ERASER,
    ERROR,
    INSERT,
    LINE,
    MAG_LINE,
    REMOVE,
    ROW,
    TEXT,
    WARNING,
    WIRE,
)
from application import gettext as _
from application.component_library import ComponentLibrary
from application.file import (
    InputFileAscii,
    InputFileChooser,
    OutputFileAscii,
    OutputFileChooser,
)
from application.grid import Grid
from application.magic_line_settings import MagicLineSettings
from application.main_window import MainWindow
from application.memo_editing import MemoEditingDialog
from application.pos import Pos
from application.preferences import Preferences
from application.symbol import (
    Arrow,
    Character,
    Column,
    DirLine,
    Eraser,
    Line,
    Rect,
    Row,
    Text,
    Wire,
)

SelectedObjects = collections.namedtuple('SelectedObjects', ['startpos', 'symbol'])
Action = collections.namedtuple('Action', ['action', 'symbol'])
MoveRecord = collections.namedtuple(
    'MoveRecord', [
        'symbol', 'old_start', 'old_end', 'new_start', 'new_end', 'old_wires', 'new_wires',
    ],
)
MOVE = 'move'


class Controller:

    def __init__(self, component_language=None, symbol_set=None):
        self.prefs = Preferences()
        self.ml_settings = MagicLineSettings()
        self.gui = MainWindow()
        self.complib = ComponentLibrary(
            language=component_language,
            symbol_set=symbol_set if symbol_set is not None else Preferences.values['SYMBOL_SET'],
        )
        self.filename = None

        self.init_stack()
        self.init_grid()

        all_components = [key for key in self.complib.components]
        if self.complib.nr_libraries() == 1:
            msg = _("One library loaded, total number of components: {0}").format(self.complib.nr_components())
        else:
            msg = _("{0} libraries loaded, total number of components: {1}").format(self.complib.nr_libraries(),
                                                                                    self.complib.nr_components())
        pub.sendMessage('STATUS_MESSAGE', msg=msg)
        pub.sendMessage('ALL_COMPONENTS', list=all_components)

        # subscriptions

        pub.subscribe(self.on_character_changed, 'CHARACTER_CHANGED')
        pub.subscribe(self.on_component_changed, 'COMPONENT_CHANGED')

        pub.subscribe(self.on_rotate_symbol, 'ROTATE_SYMBOL')
        pub.subscribe(self.on_mirror_symbol, 'MIRROR_SYMBOL')

        pub.subscribe(self.on_paste_objects, 'PASTE_OBJECTS')
        pub.subscribe(self.on_paste_mag_line, 'PASTE_MAG_LINE')
        pub.subscribe(self.on_paste_dir_line, 'PASTE_DIR_LINE')
        pub.subscribe(self.on_paste_line, 'PASTE_LINE')
        pub.subscribe(self.on_paste_wire, 'PASTE_WIRE')
        pub.subscribe(self.on_wire_preview_request, 'WIRE_PREVIEW_REQUEST')
        pub.subscribe(self.on_paste_rect, 'PASTE_RECT')
        pub.subscribe(self.on_paste_arrow, 'PASTE_ARROW')
        pub.subscribe(self.on_paste_text, 'PASTE_TEXT')
        pub.subscribe(self.on_paste_text, 'PASTE_TEXTBLOCK')
        pub.subscribe(self.on_undo, 'UNDO')
        pub.subscribe(self.on_redo, 'REDO')

        pub.subscribe(self.on_erase, 'ERASE')
        pub.subscribe(self.on_delete_objects, 'DELETE_OBJECTS')
        pub.subscribe(self.on_eraser_selected, 'ERASER')
        pub.subscribe(self.on_select_rect, 'SELECT_RECT')
        pub.subscribe(self.on_select_object, 'SELECT_OBJECT')
        pub.subscribe(self.on_select_object_at, 'SELECT_OBJECT_AT')
        pub.subscribe(self.on_selector_moved, 'SELECTOR_MOVED')
        pub.subscribe(self.on_preview_move_object, 'PREVIEW_MOVE_OBJECT')
        pub.subscribe(self.on_cancel_move_object, 'CANCEL_MOVE_OBJECT')
        pub.subscribe(self.on_move_object, 'MOVE_OBJECT')

        # insert/remove rows or columns
        pub.subscribe(self.on_grid_col, 'GRID_COL')
        pub.subscribe(self.on_grid_row, 'GRID_ROW')

        # clipboard
        pub.subscribe(self.on_cut, 'CUT')
        pub.subscribe(self.on_copy, 'COPY')

        pub.subscribe(self.on_copy_grid, 'COPY_GRID')
        pub.subscribe(self.on_paste_grid, 'PASTE_GRID')
        pub.subscribe(self.on_load_and_paste_grid, 'LOAD_AND_PASTE_GRID')
        pub.subscribe(self.on_load_ascii_from_file, 'LOAD_ASCII_FROM_FILE')

        pub.subscribe(self.on_edit_memo, 'EDIT_MEMO')
        pub.subscribe(self.on_rerun_memo, 'RERUN_MEMO')

        # file
        pub.subscribe(self.on_new, 'NEW_FILE')
        pub.subscribe(self.on_open, 'OPEN_FILE')
        pub.subscribe(self.on_save, 'SAVE_FILE')
        pub.subscribe(self.on_save_as, 'SAVE_AS_FILE')
        pub.subscribe(self.on_export_as_ascii, 'EXPORT_AS_ASCII')

        # open/save grid from/to file
        pub.subscribe(self.on_read_from_file, 'READ_FROM_FILE')
        pub.subscribe(self.on_write_to_file, 'WRITE_TO_FILE')
        pub.subscribe(self.on_write_to_ascii_file, 'WRITE_TO_ASCII_FILE')

        # grid
        pub.subscribe(self.on_grid_size, 'GRID_SIZE')
        pub.subscribe(self.on_redraw_grid, 'REDRAW_GRID')
        pub.subscribe(self.on_symbol_set_changed, 'SYMBOL_SET_CHANGED')

    def init_stack(self):
        # action stack with the last cut/pasted symbol(s)
        self.latest_action = []
        # redo stack that contains the last undone actions
        self.undone_action = []
        # all objects on the grid
        self.objects = []
        self.selected_objects = []
        self._move_snapshots = {}

    def init_grid(self, cols=None, rows=None):
        if cols is None:
            self._cols = Preferences.values['DEFAULT_COLS']
        else:
            self._cols = cols
        if rows is None:
            self._rows = Preferences.values['DEFAULT_ROWS']
        else:
            self._rows = rows
        self.grid = Grid(self._cols, self._rows)
        pub.sendMessage('NEW_GRID', grid=self.grid)

    def cell_callback(self, pos):
        # prevent calling an old grid instance method
        # FIXME better solution (than that this controller needs to know about a grid method)?
        return self.grid.cell(pos)

    def show_all(self):
        self.gui.show()

    def revert_action(self, stack):

        def cut_symbol():
            self.remove_from_objects(symbol)
            symbol.remove(self.grid)

        def paste_symbol():
            self.objects.append(symbol)
            symbol.paste(self.grid)

        action = None
        symbol = None
        if len(stack) > 0:
            record = stack.pop()
            if isinstance(record, MoveRecord):
                symbol = record.symbol
                self._assign_symbol_position(symbol, record.old_start, record.old_end)
                self._restore_wire_state(record.old_wires)
                self.on_redraw_grid()
                inverse = MoveRecord(
                    symbol, record.new_start, record.new_end,
                    record.old_start, record.old_end,
                    record.new_wires, record.old_wires,
                )
                return inverse, MOVE
            action, symbol = record
            redraw_wires = getattr(symbol, '_is_wire', False)
            # revert action
            if action == REMOVE:
                paste_symbol()
                action = INSERT
            elif action == INSERT:
                cut_symbol()
                action = REMOVE
            if redraw_wires:
                self.on_redraw_grid()
        return symbol, action

    def on_undo(self):
        if len(self.latest_action) > 0:
            symbol, action = self.revert_action(self.latest_action)
            if action:
                self.push_undone(symbol, action)
        if len(self.latest_action) < 1:
            # there are no more actions to undo
            pub.sendMessage('UNDO_CHANGED', undo=False)

    def on_redo(self):
        if len(self.undone_action) > 0:
            symbol, action = self.revert_action(self.undone_action)
            if action:
                self.push_latest_action(symbol, action, preserve_redo=True)
        if len(self.undone_action) < 1:
            # there are no more actions to redo
            pub.sendMessage('REDO_CHANGED', redo=False)

    def _clear_redo(self):
        self.undone_action = []
        pub.sendMessage('REDO_CHANGED', redo=False)

    def push_latest_action(self, symbol, action=INSERT, preserve_redo=False):
        """Add a cut or paste action to the undo stack."""
        if not preserve_redo:
            self._clear_redo()
        if action == MOVE:
            self.latest_action.append(symbol)
            pub.sendMessage('UNDO_CHANGED', undo=True)
            return
        act = Action(action=action, symbol=symbol)
        self.latest_action.append(act)
        pub.sendMessage('UNDO_CHANGED', undo=True)

    def push_undone(self, symbol, action):
        """Add an undone action to the redo stack."""
        if action == MOVE:
            self.undone_action.append(symbol)
            pub.sendMessage('REDO_CHANGED', redo=True)
            return
        act = Action(action=action, symbol=symbol)
        self.undone_action.append(act)
        pub.sendMessage('REDO_CHANGED', redo=True)

    def add_selected_object(self, symbol):
        obj = SelectedObjects(symbol.startpos, symbol)
        self.selected_objects.append(obj)

    # File menu

    def on_new(self):
        self.init_grid()
        self.init_stack()
        self.filename = None
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)
        pub.sendMessage('NOTHING_SELECTED')

    def on_open(self):
        dialog = InputFileChooser()  # noqa: F841

    def on_save(self):
        if self.filename is not None:
            self.on_write_to_file(self.filename)

    def on_save_as(self):
        dialog = OutputFileChooser()  # noqa: F841

    def on_export_as_ascii(self, filename=None):
        if filename is not None:
            pub.sendMessage('WRITE_TO_ASCII_FILE', filename=filename)
            return
        if filename is None:
            if self.filename is None:
                filename = _("Untitled_schema.txt")
            else:
                filename = os.path.splitext(os.path.basename(self.filename))[0] + '.txt'
        dialog = OutputFileAscii(filename)  # noqa: F841

    # Edit menu

    def remove_from_objects(self, symbol):
        for idx, sym in enumerate(self.objects):
            if sym is symbol or (sym.startpos == symbol.startpos and sym.identity == symbol.identity):
                del self.objects[idx]
                break

    def find_selected(self, rect):
        """Find all symbols that are located within the selection rectangle."""
        ul, br = rect
        selected = []
        for symbol in self.objects:
            if symbol.overlaps_rect(rect):
                copy = symbol.copy()
                selection = SelectedObjects(startpos=ul, symbol=copy)
                selected.append(selection)

        # TODO Only one of multiple objects sharing the same position will be selected
        if len(selected) > 0:
            selected.sort(key=lambda x: x.startpos)
            selected_unique = []
            pps = set()
            for sel in selected:
                if sel.symbol.pickpoint_pos in pps:
                    msg = _("More than one item at position: {} !").format(sel.symbol.pickpoint_pos)
                    pub.sendMessage('STATUS_MESSAGE', msg=msg, type=WARNING)
                else:
                    pps.add(sel.symbol.pickpoint_pos)
                    selected_unique.append(sel)
            selected = selected_unique
        self.selected_objects = selected

    def on_select_object_at(self, pos):
        """Select the topmost symbol under the pointer and report it to the canvas."""
        symbol = next((item for item in reversed(self.objects) if item.hit_test(pos)), None)
        self.selected_objects = [] if symbol is None else [SelectedObjects(symbol.startpos, symbol)]
        pub.sendMessage('OBJECT_SELECTION_RESULT', symbol=symbol, pos=pos)
        pub.sendMessage('SELECTION_CHANGED', selected=symbol is not None)
        if symbol is not None:
            pub.sendMessage('ORIENTATION_CHANGED', ori=symbol.ori_as_str)

    def _capture_wire_state(self):
        return [
            (
                wire, [Pos(pos.x, pos.y) for pos in wire.path],
                wire.connected_start, wire.connected_end, wire.terminal_char,
            )
            for wire in self.objects if getattr(wire, '_is_wire', False)
        ]

    @staticmethod
    def _restore_wire_state(states):
        for wire, path, connected_start, connected_end, terminal_char in states:
            wire.path = [Pos(pos.x, pos.y) for pos in path]
            wire.startpos = Pos(path[0].x, path[0].y)
            wire.endpos = Pos(path[-1].x, path[-1].y)
            wire.connected_start = connected_start
            wire.connected_end = connected_end
            wire.terminal_char = terminal_char
            wire._representation()

    @staticmethod
    def _assign_symbol_position(symbol, startpos, endpos):
        symbol.startpos = Pos(startpos.x, startpos.y)
        if getattr(symbol, '_is_wire', False):
            delta = startpos - symbol.path[0]
            symbol.path = [pos + delta for pos in symbol.path]
            symbol.startpos = Pos(symbol.path[0].x, symbol.path[0].y)
            symbol.endpos = Pos(symbol.path[-1].x, symbol.path[-1].y)
            symbol._representation()
        elif symbol.is_line:
            symbol.endpos = Pos(endpos.x, endpos.y)

    def _reroute_attached_wires(self, symbol, old_ports, wire_state):
        new_ports = {port['name']: port for port in symbol.terminal_positions()}
        for wire in self.objects:
            if not getattr(wire, '_is_wire', False):
                continue
            start_port = next((port for port in old_ports.values()
                               if wire.connected_start and wire.path[0] == port['position']), None)
            end_port = next((port for port in old_ports.values()
                             if wire.connected_end and wire.path[-1] == port['position']), None)
            if start_port is None and end_port is None:
                continue
            new_start = new_ports[start_port['name']]['position'] if start_port else wire.path[0]
            new_end = new_ports[end_port['name']]['position'] if end_port else wire.path[-1]
            start_direction = new_ports[start_port['name']]['direction'] if start_port else None
            end_direction = new_ports[end_port['name']]['direction'] if end_port else None
            route = self._wire_path(new_start, new_end, start_direction, end_direction)
            if route is None:
                return False
            wire.path = route
            wire.startpos = Pos(route[0].x, route[0].y)
            wire.endpos = Pos(route[-1].x, route[-1].y)
            wire._representation()
        return True

    def set_symbol_position(self, symbol, startpos, endpos):
        if getattr(symbol, '_is_wire', False):
            self._assign_symbol_position(symbol, startpos, endpos)
            return True

        old_start = Pos(symbol.startpos.x, symbol.startpos.y)
        old_end = Pos(symbol.endpos.x, symbol.endpos.y)
        delta = startpos - old_start
        if not delta.x and not delta.y:
            return True
        old_ports = {port['name']: port for port in symbol.terminal_positions()}
        wire_state = self._capture_wire_state()
        self._assign_symbol_position(symbol, startpos, endpos)
        if self._reroute_attached_wires(symbol, old_ports, wire_state):
            return True
        self._assign_symbol_position(symbol, old_start, old_end)
        self._restore_wire_state(wire_state)
        return False

    def on_preview_move_object(self, symbol, startpos, endpos):
        if not any(item is symbol for item in self.objects):
            return
        key = id(symbol)
        if key not in self._move_snapshots:
            self._move_snapshots[key] = (
                Pos(symbol.startpos.x, symbol.startpos.y),
                Pos(symbol.endpos.x, symbol.endpos.y),
                self._capture_wire_state(),
            )
        if not self.set_symbol_position(symbol, startpos, endpos):
            pub.sendMessage('STATUS_MESSAGE', msg=_("Move cancelled: no route for connected wire."), type=WARNING)
            return
        self.on_redraw_grid()

    def on_cancel_move_object(self, symbol):
        snapshot = self._move_snapshots.pop(id(symbol), None)
        if snapshot is None:
            return
        self._assign_symbol_position(symbol, snapshot[0], snapshot[1])
        self._restore_wire_state(snapshot[2])
        self.on_redraw_grid()

    def on_move_object(self, symbol, old_start, old_end, new_start, new_end):
        if not any(item is symbol for item in self.objects):
            return
        snapshot = self._move_snapshots.pop(id(symbol), None)
        if snapshot is None:
            snapshot = (
                Pos(old_start.x, old_start.y), Pos(old_end.x, old_end.y),
                self._capture_wire_state(),
            )
        if not self.set_symbol_position(symbol, new_start, new_end):
            self._assign_symbol_position(symbol, snapshot[0], snapshot[1])
            self._restore_wire_state(snapshot[2])
            self.on_redraw_grid()
            pub.sendMessage('STATUS_MESSAGE', msg=_("Move cancelled: no route for connected wire."), type=WARNING)
            return
        actual_start = Pos(symbol.startpos.x, symbol.startpos.y)
        actual_end = Pos(symbol.endpos.x, symbol.endpos.y)
        if snapshot[0] != actual_start or snapshot[1] != actual_end:
            self.push_latest_action(
                MoveRecord(
                    symbol, snapshot[0], snapshot[1], actual_start, actual_end,
                    snapshot[2], self._capture_wire_state(),
                ),
                MOVE,
            )
        self.on_redraw_grid()

    def on_selector_moved(self, pos):
        """Show the object (type) that is located at the cursor position."""
        count = 0
        for symbol in self.objects:
            if symbol.pickpoint_pos == pos:
                last_found = symbol
                count += 1
        if count > 1:
            msg = _("More than one item at position: {} !").format(pos)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=WARNING)
        elif count == 1:
            msg = "Object: " + last_found.name
            pub.sendMessage('STATUS_MESSAGE', msg=msg)
        else:
            pub.sendMessage('STATUS_MESSAGE', msg="")

    def on_cut(self, rect):
        self.find_selected(rect)
        action = []
        removed_wire = False
        for obj in self.selected_objects:
            act = Action(action=REMOVE, symbol=obj.symbol)
            action.append(act)
            obj.symbol.remove(self.grid)
            self.remove_from_objects(obj.symbol)
            removed_wire = removed_wire or getattr(obj.symbol, '_is_wire', False)
        if removed_wire:
            self.on_redraw_grid()
        if action:
            self._clear_redo()
        self.latest_action += action
        pub.sendMessage('UNDO_CHANGED', undo=True)
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)
        pub.sendMessage('OBJECTS_SELECTED', objects=self.selected_objects)
        if len(self.selected_objects) > 0:
            first_obj = self.selected_objects[0]
            pub.sendMessage('ORIENTATION_CHANGED', ori=first_obj.symbol.ori_as_str)

    def on_delete_objects(self, symbols=None, rect=None):
        if rect is not None:
            self.find_selected(rect)
            symbols = [item.symbol for item in self.selected_objects]
        symbols = symbols or [item.symbol for item in self.selected_objects]
        targets = []
        for selected in symbols:
            target = next((item for item in self.objects if item is selected), None)
            if target is None:
                target = next((
                    item for item in self.objects
                    if item.startpos == selected.startpos and item.identity == selected.identity
                ), None)
            if target is not None and all(target is not existing for existing in targets):
                targets.append(target)

        connected_ports = {
            port['position']
            for symbol in targets if symbol.component_key is not None
            for port in symbol.terminal_positions()
        }
        for symbol in self.objects:
            if not getattr(symbol, '_is_wire', False):
                continue
            if ((symbol.connected_start and symbol.path[0] in connected_ports) or
                    (symbol.connected_end and symbol.path[-1] in connected_ports)):
                if all(symbol is not existing for existing in targets):
                    targets.append(symbol)

        if not targets:
            return
        actions = [Action(action=REMOVE, symbol=symbol) for symbol in targets]
        self.objects = [symbol for symbol in self.objects
                        if all(symbol is not target for target in targets)]
        self._clear_redo()
        self.latest_action.extend(actions)
        self.on_redraw_grid()
        pub.sendMessage('UNDO_CHANGED', undo=True)
        pub.sendMessage('SELECTION_CHANGED', selected=False)
        pub.sendMessage('OBJECTS_DELETED', objects=targets)

    def on_copy(self, rect):
        """Select all symbols that are located within the selection rectangle."""
        self.find_selected(rect)
        pub.sendMessage('OBJECTS_SELECTED', objects=self.selected_objects)
        if len(self.selected_objects) > 0:
            first_obj = self.selected_objects[0]
            pub.sendMessage('ORIENTATION_CHANGED', ori=first_obj.symbol.ori_as_str)

    def on_edit_memo(self):
        memo = ""
        for symbol in self.objects:
            memo += symbol.memo() + '\n'
        dialog = MemoEditingDialog(memo)
        dialog.run()
        dialog.hide()

    def on_rerun_memo(self, str):
        self.init_stack()
        self.init_grid()
        memo = []
        str = str.splitlines()
        for line in str:
            memo.append(line)
        self.play_memo(memo)

    def on_symbol_set_changed(self, symbol_set):
        if symbol_set == self.complib.symbol_set:
            return

        memo = [symbol.memo() for symbol in self.objects]
        cols, rows = self._cols, self._rows
        language = self.complib.language
        self.complib = ComponentLibrary(language=language, symbol_set=symbol_set)
        pub.sendMessage('ALL_COMPONENTS', list=list(self.complib.components))
        pub.sendMessage('NOTHING_SELECTED')

        self.init_stack()
        self.init_grid(cols, rows)
        self.play_memo(memo)

        # Re-rendering is a style change, not a user drawing action.
        self.latest_action = []
        self.undone_action = []
        pub.sendMessage('UNDO_CHANGED', undo=False)
        pub.sendMessage('REDO_CHANGED', redo=False)
        pub.sendMessage(
            'STATUS_MESSAGE',
            msg=_("Symbol standard changed to {0}").format(symbol_set),
        )

    # grid manipulation

    def on_grid_size(self, cols, rows):
        self._rows = rows
        self._cols = cols
        self.on_redraw_grid()

    def on_redraw_grid(self):
        rows = self._rows
        cols = self._cols
        self.init_grid(cols, rows)
        wires = []
        for symbol in self.objects:
            if getattr(symbol, '_is_wire', False):
                wires.append(symbol)
            else:
                symbol.paste(self.grid)
        for wire in wires:
            wire.paste(self.grid)
        self._render_wire_network(wires)
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)

    def _render_wire_network(self, wires):
        directions_by_pos = collections.defaultdict(set)
        connected_nodes = set()
        terminal_marks = {}
        for wire in wires:
            if wire.connected_start:
                connected_nodes.add(wire.path[0])
            if wire.connected_end:
                connected_nodes.add(wire.path[-1])
            if wire.terminal_char:
                if not wire.connected_start:
                    terminal_marks[wire.path[0]] = wire.terminal_char
                if not wire.connected_end:
                    terminal_marks[wire.path[-1]] = wire.terminal_char
            for first, second in zip(wire.path, wire.path[1:]):
                first_direction = Wire._direction(first, second)
                second_direction = Wire._direction(second, first)
                directions_by_pos[first].add(first_direction)
                directions_by_pos[second].add(second_direction)

        for pos, directions in directions_by_pos.items():
            if pos in connected_nodes:
                char = 'O'
            elif pos in terminal_marks:
                char = terminal_marks[pos]
            elif {'E', 'W', 'N', 'S'}.issubset(directions):
                char = '╳'
            elif len(directions) >= 3:
                char = 'O'
            else:
                char = Wire.glyph_for_directions(directions)
            self.grid.set_cell(pos, char)

    @staticmethod
    def _wire_direction_delta(direction):
        return {
            'N': Pos(0, -1), 'E': Pos(1, 0),
            'S': Pos(0, 1), 'W': Pos(-1, 0),
        }.get(direction)

    def _wire_path(self, start, end, start_direction=None, end_direction=None):
        """Find a low-bend orthogonal path that avoids component footprints."""
        start_key, end_key = start.xy, end.xy
        if start_key == end_key:
            return None
        if not (0 <= start.x < self.grid.nr_cols and 0 <= start.y < self.grid.nr_rows
                and 0 <= end.x < self.grid.nr_cols and 0 <= end.y < self.grid.nr_rows):
            return None

        blocked = set()
        for symbol in self.objects:
            if symbol.component_key is None:
                continue
            upper_left, lower_right = symbol.grid_bounds()
            for y in range(upper_left.y, lower_right.y + 1):
                for x in range(upper_left.x, lower_right.x + 1):
                    blocked.add((x, y))
        blocked.discard(start_key)
        blocked.discard(end_key)

        delta = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
        initial_direction = start_direction if start_direction in delta else None
        target_approach = None
        if end_direction in delta:
            dx, dy = delta[end_direction]
            target_approach = (end.x + dx, end.y + dy)

        origin = (start.x, start.y, '')
        costs = {origin: 0}
        previous = {}
        queue = [(0, origin)]
        destination = None
        while queue:
            cost, state = heapq.heappop(queue)
            if cost != costs.get(state):
                continue
            x, y, previous_direction = state
            if (x, y) == end_key:
                destination = state
                break
            for direction, (dx, dy) in delta.items():
                if previous_direction == '' and initial_direction and direction != initial_direction:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < self.grid.nr_cols and 0 <= ny < self.grid.nr_rows):
                    continue
                if (nx, ny) in blocked:
                    continue
                if (nx, ny) == end_key and target_approach and (x, y) != target_approach:
                    continue
                step_cost = 1 + (0.35 if previous_direction and previous_direction != direction else 0)
                cell = self.grid.cell(Pos(nx, ny))
                if cell != ' ' and not (nx, ny) == end_key:
                    step_cost += 4
                next_state = (nx, ny, direction)
                next_cost = cost + step_cost
                if next_cost < costs.get(next_state, float('inf')):
                    costs[next_state] = next_cost
                    previous[next_state] = state
                    heapq.heappush(queue, (next_cost, next_state))

        if destination is None:
            return None
        path = []
        while destination is not None:
            path.append(Pos(destination[0], destination[1]))
            destination = previous.get(destination)
        return list(reversed(path))

    def _is_connectable_node(self, pos):
        for symbol in self.objects:
            if getattr(symbol, '_is_wire', False) and pos in symbol.path:
                return True
            if any(port['position'] == pos for port in symbol.terminal_positions()):
                return True
        return False

    def on_paste_wire(self, startpos, endpos, start_direction=None, end_direction=None,
                      connected_start=False, connected_end=False, terminal_char=None):
        connected_start = connected_start or self._is_connectable_node(startpos)
        connected_end = connected_end or self._is_connectable_node(endpos)
        path = self._wire_path(startpos, endpos, start_direction, end_direction)
        if path is None:
            pub.sendMessage('STATUS_MESSAGE', msg=_("No clear route between those points."), type=WARNING)
            return
        symbol = Wire(path, connected_start, connected_end, terminal_char)
        self.objects.append(symbol)
        symbol.paste(self.grid)
        self.on_redraw_grid()
        self.push_latest_action(symbol)

    def on_wire_preview_request(self, startpos, endpos, start_direction=None, end_direction=None):
        path = self._wire_path(startpos, endpos, start_direction, end_direction)
        pub.sendMessage('WIRE_PREVIEW_RESULT', path=path)

    def on_grid_col(self, col, action):
        # don't mistake the symbol action for the edit action
        symbol = Column(col, action)
        self.objects.append(symbol)
        symbol.paste(self.grid)
        self.push_latest_action(symbol)
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)

    def on_grid_row(self, row, action):
        # don't mistake the symbol action for the edit action
        symbol = Row(row, action)
        self.objects.append(symbol)
        symbol.paste(self.grid)
        self.push_latest_action(symbol)
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)

    # character/component symbol

    def on_character_changed(self, char):
        symbol = Character(char)
        self.selected_objects = []
        self.add_selected_object(symbol)
        pub.sendMessage('CHARACTER_SELECTED', char=symbol)

    def on_component_changed(self, label):
        symbol = self.complib.get_symbol(label)
        self.selected_objects = []
        self.add_selected_object(symbol)
        pub.sendMessage('STATUS_MESSAGE', msg='')
        pub.sendMessage('SYMBOL_SELECTED', symbol=symbol)
        pub.sendMessage('ORIENTATION_CHANGED', ori=symbol.ori_as_str)

    def on_rotate_symbol(self):
        first = True
        canvas_changed = False
        for obj in self.selected_objects:
            symbol = obj.symbol
            if any(item is symbol for item in self.objects) and symbol.component_key is not None:
                old_orientation = symbol.ori
                old_ports = {port['name']: port for port in symbol.terminal_positions()}
                wire_state = self._capture_wire_state()
                symbol.rotate()
                if self._reroute_attached_wires(symbol, old_ports, wire_state):
                    canvas_changed = True
                else:
                    symbol.ori = old_orientation
                    self._restore_wire_state(wire_state)
                    pub.sendMessage('STATUS_MESSAGE', msg=_("Rotation cancelled: no route for connected wire."), type=WARNING)
            else:
                symbol.rotate()
            # show the orientation of a single, or the first, symbol in the statusbar
            if first:
                first = False
                pub.sendMessage('ORIENTATION_CHANGED', ori=symbol.ori_as_str)
        if canvas_changed:
            self.on_redraw_grid()

    def on_mirror_symbol(self):
        canvas_changed = False
        for obj in self.selected_objects:
            symbol = obj.symbol
            old_mirrored = symbol.mirrored
            if any(item is symbol for item in self.objects) and symbol.component_key is not None:
                old_ports = {port['name']: port for port in symbol.terminal_positions()}
                wire_state = self._capture_wire_state()
                symbol.mirrored = 1 - old_mirrored
                if self._reroute_attached_wires(symbol, old_ports, wire_state):
                    canvas_changed = True
                else:
                    symbol.mirrored = old_mirrored
                    self._restore_wire_state(wire_state)
                    pub.sendMessage('STATUS_MESSAGE', msg=_("Mirror cancelled: no route for connected wire."), type=WARNING)
            else:
                symbol.mirrored = 1 - old_mirrored
        if canvas_changed:
            self.on_redraw_grid()

    def on_paste_text(self, symbol):
        self.paste_symbol(symbol)
        pub.sendMessage('UNDO_CHANGED', undo=True)

    def on_paste_objects(self, pos):
        """
        Paste selection.
        :param pos: the target position in grid (col, row) coordinates.
        """
        action = []
        pasted_wire = False
        for obj in self.selected_objects:
            offset = pos - obj.startpos
            # TODO make the position translation a Symbol method?
            symbol = obj.symbol.copy()
            symbol.startpos += offset
            symbol.endpos += offset
            act = Action(action=INSERT, symbol=symbol)
            action.append(act)
            self.objects.append(symbol)
            symbol.paste(self.grid)
            pasted_wire = pasted_wire or getattr(symbol, '_is_wire', False)
        if action:
            self._clear_redo()
        self.latest_action += action
        pub.sendMessage('UNDO_CHANGED', undo=True)
        if pasted_wire:
            self.on_redraw_grid()
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)

    def paste_symbol(self, symbol):
        self.selected_objects = []
        self.add_selected_object(symbol)
        self.objects.append(symbol)
        symbol.paste(self.grid)
        self.push_latest_action(symbol)
        pub.sendMessage('CANVAS_OBJECTS', objects=self.objects)

    # lines

    def on_paste_line(self, startpos, endpos, type):
        if abs(endpos.x - startpos.x) >= abs(endpos.y - startpos.y):
            endpos = Pos(endpos.x, startpos.y)
        else:
            endpos = Pos(startpos.x, endpos.y)
        self.on_paste_wire(
            startpos, endpos,
            terminal_char=Line.TERMINAL_TYPE.get(type),
        )

    def on_paste_dir_line(self, startpos, endpos):
        symbol = DirLine(startpos, endpos)
        self.paste_symbol(symbol)

    def on_paste_mag_line(self, startpos, endpos):
        self.on_paste_wire(startpos, endpos)

    def on_paste_mag_line_w_type(self, startpos, endpos, type):
        # backward compatibility
        self.on_paste_wire(startpos, endpos)

    def on_paste_rect(self, startpos, endpos):
        symbol = Rect(startpos, endpos)
        self.paste_symbol(symbol)

    def on_paste_arrow(self, startpos, endpos):
        symbol = Arrow(startpos, endpos)
        self.paste_symbol(symbol)

    # clipboard

    def on_copy_grid(self):
        """
        Copy the content of the grid to the clipboard.
        The rows are copied as ASCII lines, terminated by CR.
        """
        QApplication.clipboard().setText(self.grid.content_as_str())

    def on_paste_grid(self):
        """
        Copy the content of the clipboard to the grid.
        ASCII lines, terminated by CR, are interpreted as rows.
        """
        selected = []
        pos = Pos(0, 0)
        relative_pos = Pos(0, 0)
        try:
            content = QApplication.clipboard().text().splitlines()
        except Exception:
            content = []
        for line in content:
            symbol = Text(relative_pos, line)
            selection = SelectedObjects(startpos=pos, symbol=symbol)
            selected.append(selection)
            relative_pos += Pos(0, 1)
        self.selected_objects = selected
        pub.sendMessage('OBJECTS_SELECTED', objects=self.selected_objects)

    def on_load_and_paste_grid(self):
        self.selected_objects = []
        dialog = InputFileAscii()  # noqa: F841

    def on_load_ascii_from_file(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            startpos = Pos(0, 0)
            pos = Pos(0, 0)
            for line in lines:
                # create a TEXT instance for each line
                # fill selected_objects...
                symbol = Text(pos, line)
                selection = SelectedObjects(startpos=startpos, symbol=symbol)
                pos += Pos(0, 1)
                self.selected_objects.append(selection)
            pub.sendMessage('OBJECTS_SELECTED', objects=self.selected_objects)
            return True

        except OSError as e:
            msg = _("Unable to open file for reading: {} error({}): {}").format(filename, e.errno, e.strerror)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=WARNING)
            return False

        except UnicodeDecodeError as e:
            msg = _("Unable to open file for reading: {} error({}): {}").format(filename, e.encoding, e.reason)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=WARNING)
            return False

    # other

    def on_erase(self, startpos, size):
        """Erase an area of the given size."""
        symbol = Eraser(size, startpos)
        self.selected_objects = []
        self.add_selected_object(symbol)
        self.objects.append(symbol)
        symbol.paste(self.grid)
        self.push_latest_action(symbol)
        pub.sendMessage('UNDO_CHANGED', undo=True)

    def on_eraser_selected(self, size):
        """Select eraser of the given size."""
        symbol = Eraser(size)
        self.selected_objects = []
        self.add_selected_object(symbol)
        pub.sendMessage('SYMBOL_SELECTED', symbol=symbol)

    def select_all_objects(self):
        """Select all objects."""
        selection = []
        for symbol in self.objects:
            sel = SelectedObjects(symbol.startpos, symbol)
            selection.append(sel)
        return selection

    def on_select_rect(self):
        """Select multiple objects."""
        pub.sendMessage('NOTHING_SELECTED')
        pub.sendMessage('SELECTING_RECT', objects=self.select_all_objects())
        msg = _("Selecting rectangle...")
        pub.sendMessage('STATUS_MESSAGE', msg=msg)

    def on_select_object(self):
        """Select individual objects."""
        pub.sendMessage('NOTHING_SELECTED')
        pub.sendMessage('SELECTING_OBJECT', objects=self.select_all_objects())

    # file open/save

    # TODO naar eigen file of class zetten

    def on_write_to_file(self, filename):
        try:
            lines = [symbol.memo() for symbol in self.objects]
            with open(filename, 'w', encoding='utf-8', newline='') as fout:
                fout.write(''.join(line + '\n' for line in lines))
            self.filename = filename
            msg = _("Schema has been saved in: {}").format(filename)
            pub.sendMessage('STATUS_MESSAGE', msg=msg)
            # in case we have saved a new file, we now have an opened file
            pub.sendMessage('FILE_OPENED')
            return True

        except OSError:
            msg = _("Unable to open file for writing: {}").format(filename)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=ERROR)
            return False

    def on_write_to_ascii_file(self, filename):
        try:
            with open(filename, 'w', encoding='utf-8', newline='') as fout:
                fout.write(self.grid.content_as_str())
            self.filename = filename
            msg = _("ASCII Schema has been saved in: {}").format(filename)
            pub.sendMessage('STATUS_MESSAGE', msg=msg)
            return True

        except OSError:
            msg = _("Unable to open file for writing: %s" % filename)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=ERROR)
            return False

    def on_read_from_file(self, filename):
        self.filename = filename
        try:
            with open(filename, 'r', encoding='utf-8') as source:
                memo = source.readlines()
            # start with a fresh grid
            self.init_stack()
            self.init_grid()
            skipped = self.play_memo(memo)

            # empty the undo stack (from the played memo actions)
            # self.latest_action = []
            # pub.sendMessage('UNDO_CHANGED', undo=False)

            # TODO only the basename in statusbar, or truncated path, e.g. when the full path exceeds length x
            base = os.path.basename(filename)
            if skipped > 0:
                msg = _("{0} lines skipped in: {1}").format(skipped, base)
            else:
                msg = _("File: {}").format(base)

            pub.sendMessage('STATUS_MESSAGE', msg=msg)
            pub.sendMessage('FILE_OPENED')
            pub.sendMessage('NOTHING_SELECTED')
            return True

        except OSError as e:
            msg = _("Unable to open file for reading: {} error({}): {}").format(filename, e.errno, e.strerror)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=ERROR)
            return False

        except UnicodeDecodeError as e:
            msg = _("Unable to open file for reading: {} error({}): {}").format(filename, e.encoding, e.reason)
            pub.sendMessage('STATUS_MESSAGE', msg=msg, type=ERROR)
            return False

    def play_memo(self, memo):

        def play_component(item):
            prefix = COMPONENT + ':'
            if not item.startswith(prefix):
                return None
            try:
                payload = item[len(prefix):].strip()
                component_name, end = json.JSONDecoder().raw_decode(payload)
                values = payload[end:].lstrip(',').split(',')
                if not isinstance(component_name, str) or len(values) != 4:
                    return 1
                orientation, mirrored, x, y = map(int, values)
                pos = Pos(x, y)
                symbol = self.complib.get_symbol(component_name)
                symbol.ori = orientation
                symbol.mirrored = mirrored
                self.selected_objects = []
                self.add_selected_object(symbol)
                self.on_paste_objects(pos)
                return 0
            except (KeyError, TypeError, ValueError):
                return 1

        def play_wire(item):
            try:
                data = json.loads(item[len(WIRE) + 1:])
                path = [Pos(x, y) for x, y in data['path']]
                if any(not (0 <= pos.x < self.grid.nr_cols and 0 <= pos.y < self.grid.nr_rows)
                       for pos in path):
                    raise ValueError('Wire path is outside the grid')
                wire = Wire(
                    path,
                    data.get('connected_start', False),
                    data.get('connected_end', False),
                    data.get('terminal_char'),
                )
                self.objects.append(wire)
                wire.paste(self.grid)
                self.on_redraw_grid()
                return 0
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return 1

        def play_m1(m):
            skip = 0
            type = m.group(1)
            if type == ERASER:
                w = int(m.group(2))
                h = int(m.group(3))
                size = (w, h)
                x, y = m.group(4, 5)
                pos = Pos(x, y)
                symbol = Eraser(size)
                self.selected_objects = []
                self.add_selected_object(symbol)
                self.on_paste_objects(pos)

            elif type == CHARACTER:
                ascii = m.group(2)
                char = chr(int(ascii))
                x, y = m.group(3, 4)
                pos = Pos(x, y)
                symbol = Character(char)
                self.selected_objects = []
                self.add_selected_object(symbol)
                self.on_paste_objects(pos)

            elif type == LINE:
                line_type = int(m.group(2))
                x, y = m.group(3, 4)
                startpos = Pos(x, y)
                x, y = m.group(5, 6)
                endpos = Pos(x, y)
                self.on_paste_line(startpos, endpos, line_type)

            elif type == DIR_LINE:
                x, y = m.group(2, 3)
                startpos = Pos(x, y)
                x, y = m.group(4, 5)
                endpos = Pos(x, y)
                self.on_paste_dir_line(startpos, endpos)

            elif type == MAG_LINE:
                line_type = int(m.group(2))
                x, y = m.group(3, 4)
                startpos = Pos(x, y)
                x, y = m.group(5, 6)
                endpos = Pos(x, y)
                self.on_paste_mag_line_w_type(startpos, endpos, line_type)

            elif type == DRAW_RECT:
                x, y = m.group(2, 3)
                startpos = Pos(x, y)
                x, y = m.group(4, 5)
                endpos = Pos(x, y)
                self.on_paste_rect(startpos, endpos)

            elif type == ARROW:
                x, y = m.group(2, 3)
                startpos = Pos(x, y)
                x, y = m.group(4, 5)
                endpos = Pos(x, y)
                self.on_paste_arrow(startpos, endpos)
            else:
                skip = 1
            return skip

        def play_m2(m):
            skip = 0
            type = m.group(1)
            if type == 'i':
                action = INSERT
            else:
                action = REMOVE
            what = m.group(2)
            nr = int(m.group(3))
            if what == COL:
                self.on_grid_col(nr, action)
            elif what == ROW:
                self.on_grid_row(nr, action)
            else:
                skip = 1
            return skip

        def play_m3(m):
            skip = 0
            type = m.group(1)
            if type == TEXT:
                orientation = int(m.group(2))
                x, y = m.group(3, 4)
                pos = Pos(x, y)
                str = m.group(5)
                text = json.loads(str)
                symbol = Text(pos, text, orientation)
                self.selected_objects = []
                self.add_selected_object(symbol)
                self.on_paste_objects(pos)
            else:
                skip = 1
            return skip

        skipped = 0
        linenr = 0
        for item in memo:
            linenr += 1
            if item.startswith(WIRE + ':'):
                skipped += play_wire(item)
                continue
            if item.startswith(COMPONENT + ':'):
                skipped += play_component(item)
                continue
            m1 = re.search(r'(^eras|^char|^rect|^line|^magl|^dirl|^arrw):(\d+),(\d+),(\d+),?(\d*),?(\d*),?(\d*)', item)
            m2 = re.search(r'(^d|^i)(row|col):(\d+)', item)
            m3 = re.search(r'(^text):(\d+),(\d+),(\d+),(.*)', item)
            if m1 is not None:
                skipped += play_m1(m1)
            elif m2 is not None:
                skipped += play_m2(m2)
            elif m3 is not None:
                skipped += play_m3(m3)
            else:
                msg = _("skipped linenr: {}").format(linenr)
                pub.sendMessage('STATUS_MESSAGE', msg=msg, type=WARNING)
                skipped += 1
        return skipped
