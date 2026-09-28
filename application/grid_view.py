"""
AACircuit
2020-03-02 JvO
"""

import time

import cairo
from pubsub import pub
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from application import (
    ARROW,
    CHARACTER,
    COL,
    COMPONENT,
    DIR_LINE,
    DRAW_RECT,
    ERASER,
    HORIZONTAL,
    IDLE,
    LINE,
    MAG_LINE,
    MARK_CHAR,
    OBJECT,
    OBJECTS,
    RECT,
    ROW,
    SELECTED,
    SELECTING,
    TEXT,
    TEXT_BLOCK,
    VERTICAL,
)
from application.pos import Pos
from application.preferences import Preferences
from application.selection import (
    Selection,
    SelectionArrow,
    SelectionCol,
    SelectionEraser,
    SelectionObject,
    SelectionRect,
    SelectionRow,
)
from application.symbol import Arrow, DirLine, Line, MagLine, Rect, Text, Wire


class GridView(QWidget):

    def __init__(self):
        super().__init__()

        self.surface = None
        self._grid = None
        self._objects = None
        self._hover_pos = Pos(0, 0)
        self._hover_previous_pos = Pos(0, 0)

        self._selection = Selection(None)
        self._selected_canvas_symbol = None
        self._moving_symbol = None
        self._move_anchor = None
        self._move_old_start = None
        self._move_old_end = None
        self._move_bounds = None
        self._canvas_objects = []
        self._wire_dragging = False
        self._wire_start = None
        self._wire_start_terminal = None
        self._wire_preview_end = None
        self._wire_preview_path = None

        # selection position
        self._drag_dir = None
        self._drag_startpos = None
        self._drag_endpos = None
        self._drag_currentpos = None
        self._drag_prevpos = []

        # text
        self._cursor_on = True
        self._text = ""

        # pickpoints
        self._show_symbol_pickpoints = True
        self._show_line_pickpoints = True
        self._show_text_pickpoints = True

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mouse_dragging = False

        self.start_time = time.time()
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(250)
        self.cursor_timer.timeout.connect(self.toggle_cursor)
        self.cursor_timer.start()

        # subscriptions

        pub.subscribe(self.set_grid, 'NEW_GRID')

        pub.subscribe(self.on_add_text, 'ADD_TEXT')
        pub.subscribe(self.on_add_textblock, 'ADD_TEXTBLOCK')

        pub.subscribe(self.on_character_selected, 'CHARACTER_SELECTED')
        pub.subscribe(self.on_symbol_selected, 'SYMBOL_SELECTED')
        pub.subscribe(self.on_objects_selected, 'OBJECTS_SELECTED')
        pub.subscribe(self.on_object_selection_result, 'OBJECT_SELECTION_RESULT')
        pub.subscribe(self.on_canvas_objects, 'CANVAS_OBJECTS')
        pub.subscribe(self.on_wire_preview_result, 'WIRE_PREVIEW_RESULT')

        pub.subscribe(self.on_selecting_eraser, 'SELECTING_ERASER')
        pub.subscribe(self.on_selecting_rect, 'SELECTING_RECT')
        pub.subscribe(self.on_selecting_object, 'SELECTING_OBJECT')
        pub.subscribe(self.on_selecting_row, 'SELECTING_ROW')
        pub.subscribe(self.on_selecting_col, 'SELECTING_COL')

        pub.subscribe(self.on_nothing_selected, 'NOTHING_SELECTED')

        pub.subscribe(self.on_draw_mag_line, 'DRAW_MAG_LINE')
        pub.subscribe(self.on_draw_dir_line, 'DRAW_LINE0')
        pub.subscribe(self.on_draw_line, 'DRAW_LINE1')
        pub.subscribe(self.on_draw_line, 'DRAW_LINE2')
        pub.subscribe(self.on_draw_line, 'DRAW_LINE3')
        pub.subscribe(self.on_draw_line, 'DRAW_LINE4')
        pub.subscribe(self.on_draw_rect, 'DRAW_RECT')
        pub.subscribe(self.on_draw_arrow, 'DRAW_ARROW')

        # pickpoints
        pub.subscribe(self.on_show_symbol_pickpoints, 'SHOW_SYMBOL_PICKPOINTS')
        pub.subscribe(self.on_show_line_pickpoints, 'SHOW_LINE_PICKPOINTS')
        pub.subscribe(self.on_show_text_pickpoints, 'SHOW_TEXT_PICKPOINTS')

    def set_grid(self, grid):
        self._grid = grid
        self.set_viewport_size()

    def set_viewport_size(self):
        width = self._grid.nr_cols * Preferences.values['GRIDSIZE_W']
        height = self._grid.nr_rows * Preferences.values['GRIDSIZE_H']
        self.setMinimumSize(width, height)
        self.resize(width, height)
        self.update()

    @property
    def max_pos(self):
        x_max = self.surface.get_width()
        y_max = self.surface.get_height()
        return Pos(x_max, y_max)

    @property
    def max_pos_grid(self):
        x_max = self._grid.nr_cols * Preferences.values['GRIDSIZE_W']
        y_max = self._grid.nr_rows * Preferences.values['GRIDSIZE_H']
        return Pos(x_max, y_max)

    @property
    def drag_rect(self):
        """Return the selected rectangle (upper-left and bottom-right) position."""
        if self._drag_startpos <= self._drag_endpos:
            ul = self._drag_startpos
            br = self._drag_endpos
        else:
            ul = self._drag_endpos
            br = self._drag_startpos
        ul = ul.grid_cr()
        br = br.grid_cr()
        return ul, br

    def init_surface(self, width, height):
        """Initialize Cairo surface."""
        width = max(1, int(width))
        height = max(1, int(height))
        if self.surface is not None:
            # destroy previous buffer
            self.surface.finish()
            self.surface = None
        # create a new buffer
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

    def paintEvent(self, event):
        width = max(self.width(), self._grid.nr_cols * Preferences.values['GRIDSIZE_W'] if self._grid else 1)
        height = max(self.height(), self._grid.nr_rows * Preferences.values['GRIDSIZE_H'] if self._grid else 1)
        if self.surface is None or self.surface.get_width() != width or self.surface.get_height() != height:
            self.init_surface(width, height)
        context = cairo.Context(self.surface)
        self.do_drawing(context)
        self.surface.flush()
        data = self.surface.get_data()
        image = QImage(
            data,
            self.surface.get_width(),
            self.surface.get_height(),
            self.surface.get_stride(),
            QImage.Format.Format_ARGB32_Premultiplied,
        ).copy()
        painter = QPainter(self)
        painter.drawImage(0, 0, image)
        painter.end()

    # (don't) show pickpoints

    def on_show_symbol_pickpoints(self, state):
        self._show_symbol_pickpoints = state

    def on_show_line_pickpoints(self, state):
        self._show_line_pickpoints = state

    def on_show_text_pickpoints(self, state):
        self._show_text_pickpoints = state

    # SELECTIONs

    def on_nothing_selected(self):
        self._cancel_wire_gesture()
        self._selection = Selection(None)
        self._selected_canvas_symbol = None
        self._moving_symbol = None
        self._send_active_tool(None)
        self.update()

    def _cancel_wire_gesture(self):
        self._wire_dragging = False
        self._wire_start = None
        self._wire_start_terminal = None
        self._wire_preview_end = None
        self._wire_preview_path = None

    def on_add_text(self):
        self._cancel_wire_gesture()
        self._selection = Selection(item=TEXT, state=SELECTING)
        self._text = ""
        self._symbol = Text(Pos(0, 0), self._text)
        self._send_active_tool('insert_text')
        self.setFocus()

    def on_add_textblock(self, text):
        self._cancel_wire_gesture()
        self._selection = Selection(item=TEXT_BLOCK, state=SELECTING)
        self._symbol = Text(Pos(0, 0), text)
        self._text = text
        self._send_active_tool('insert_text_line')

    def on_character_selected(self, char):
        self._cancel_wire_gesture()
        self._selection = Selection(item=CHARACTER, state=SELECTED)
        self._symbol = char
        self._send_active_tool('character:' + chr(char.identity))

    def on_symbol_selected(self, symbol):
        self._cancel_wire_gesture()
        # only components (can be rotated or mirrored)
        self._selection = Selection(item=COMPONENT, state=SELECTED)
        self._symbol = symbol
        self._send_active_tool(None)

    def on_objects_selected(self, objects):
        self._cancel_wire_gesture()
        # one object or multiple objects have been selected
        self._selection = Selection(item=OBJECTS)
        self._selection.state = SELECTED
        self._objects = objects
        self._send_active_tool(None)

    def on_canvas_objects(self, objects):
        self._canvas_objects = objects
        if self._selected_canvas_symbol is not None:
            self._set_object_selection_bounds(self._selected_canvas_symbol)
        self.update()

    def _set_object_selection_bounds(self, symbol):
        upper_left, lower_right = symbol.grid_bounds()
        self._drag_startpos = upper_left.view_xy()
        self._drag_endpos = Pos(lower_right.x + 1, lower_right.y + 1).view_xy()
        self._selection.startpos = self._drag_startpos
        self._selection.endpos = self._drag_endpos
        self._selection.maxpos = self.max_pos_grid

    def on_object_selection_result(self, symbol, pos):
        self._selected_canvas_symbol = symbol
        self._selection = SelectionObject()
        if symbol is not None:
            self._set_object_selection_bounds(symbol)
        else:
            self._drag_startpos = None
            self._drag_endpos = None
        self.update()

    def on_selecting_object(self, objects):
        self._cancel_wire_gesture()
        # select a single object
        self._selection = SelectionObject()
        self._objects = objects
        self._selected_canvas_symbol = None
        self._send_active_tool('select_object')

    def on_selecting_eraser(self):
        self._cancel_wire_gesture()
        self._selection = SelectionEraser()
        self._send_active_tool('eraser')

    def on_selecting_rect(self, objects):
        self._cancel_wire_gesture()
        self._selection = SelectionRect()
        self._objects = objects
        self._send_active_tool('select_rect')

    def on_selecting_arrow(self, objects):
        self._selection = SelectionArrow()
        self._objects = objects

    def on_selecting_row(self, action):
        self._cancel_wire_gesture()
        self._selection = SelectionRow(action)
        self._send_active_tool('insert_row' if action == 'insert' else 'remove_row')
        pub.sendMessage('STATUS_MESSAGE', msg='')

    def on_selecting_col(self, action):
        self._cancel_wire_gesture()
        self._selection = SelectionCol(action)
        self._send_active_tool('insert_col' if action == 'insert' else 'remove_col')
        pub.sendMessage('STATUS_MESSAGE', msg='')

    # LINES

    def on_draw_mag_line(self):
        self._cancel_wire_gesture()
        self._selection = Selection(item=MAG_LINE)
        self._symbol = MagLine(Pos(0, 0), Pos(1, 1), self._grid.cell)
        self._send_active_tool('auto_line')

    def on_draw_dir_line(self, type):
        self._cancel_wire_gesture()
        self._selection = Selection(item=DIR_LINE)
        self._symbol = DirLine(Pos(0, 0), Pos(1, 1))
        self._send_active_tool('free_line')
        pub.sendMessage('STATUS_MESSAGE', msg='')

    def on_draw_line(self, type):
        self._cancel_wire_gesture()
        self._selection = Selection(item=LINE)
        self._symbol = Line(Pos(0, 0), Pos(1, 1), type=type)
        line_tool = {
            Line.LINE2: 'line_2', Line.LINE3: 'line_3', Line.LINE4: 'line_4',
        }.get(type, 'line_1')
        self._send_active_tool(line_tool)
        pub.sendMessage('STATUS_MESSAGE', msg='')

    def on_draw_rect(self):
        self._cancel_wire_gesture()
        self._selection = Selection(item=DRAW_RECT)
        self._symbol = Rect(Pos(0, 0), Pos(1, 1))
        self._send_active_tool('draw_rect')
        pub.sendMessage('STATUS_MESSAGE', msg='')

    def on_draw_arrow(self):
        self._cancel_wire_gesture()
        self._selection = Selection(item=ARROW)
        self._symbol = Arrow(Pos(0, 0), Pos(1, 1))
        self._send_active_tool('arrow')
        pub.sendMessage('STATUS_MESSAGE', msg='')

    # TEXT ENTRY

    # DRAWING

    def do_drawing(self, ctx):
        if self._grid is None:
            return
        self.draw_background(ctx)
        self.draw_gridlines(ctx)
        self.draw_content(ctx)
        self.draw_terminal_handles(ctx)
        self.draw_selection(ctx)

    def draw_border(self, ctx, w, h):
        """draw a border at 1% of the page-size."""
        ctx.save()
        ctx.set_source_rgb(0.75, 0.75, 0.75)
        ctx.set_line_width(0.25)
        ctx.rectangle(w * 0.01, h * 0.01, w * 0.99, h * 0.99)
        ctx.stroke()
        ctx.restore()

    def draw_background(self, ctx):
        """Draw a background with the size of the grid."""
        ctx.set_source_rgb(0.95, 0.95, 0.85)
        ctx.set_line_width(0.5)
        ctx.set_tolerance(0.1)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        x_max, y_max = self.max_pos_grid.xy
        ctx.new_path()
        ctx.rectangle(0, 0, x_max, y_max)
        ctx.fill()

    def draw_gridlines(self, ctx):
        # TODO use CSS for uniform colors?
        ctx.set_source_rgb(0.75, 0.75, 0.75)
        ctx.set_line_width(0.5)
        ctx.set_tolerance(0.1)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        x_max, y_max = self.max_pos.xy
        x_incr = Preferences.values['GRIDSIZE_W']
        y_incr = Preferences.values['GRIDSIZE_H']

        # horizontal lines
        y = Preferences.values['GRIDSIZE_H']
        while y <= y_max:
            ctx.new_path()
            ctx.move_to(0, y)
            ctx.line_to(x_max, y)
            ctx.stroke()
            y += y_incr
        # vertical lines
        x = 0
        while x <= x_max:
            ctx.new_path()
            ctx.move_to(x, 0)
            ctx.line_to(x, y_max)
            ctx.stroke()
            x += x_incr

    def draw_content(self, ctx):
        if self._grid is None:
            return
        ctx.set_source_rgb(0.1, 0.1, 0.1)
        family = Preferences.values['FONT'] if Preferences.values['PANGO_FONT'] else 'monospace'
        ctx.set_font_size(Preferences.values['FONTSIZE'])
        ctx.select_font_face(family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        y = 0
        for r in self._grid.grid:
            x = 0
            for c in r:
                # Cairo's text glyph origin is its left-bottom corner.
                ctx.move_to(x, y + Preferences.values['FONTSIZE'])
                ctx.show_text(str(c))
                x += Preferences.values['GRIDSIZE_W']
            y += Preferences.values['GRIDSIZE_H']
            # no reference to surface dimension, to allow to be run from (nose) test (w/o GUI)
            # if y >= self.surface.get_height():
            #     break

    def draw_selection(self, ctx):
        ctx.save()
        if self._selection.state == IDLE:
            if self._selection.item == RECT:
                self.mark_all_objects(ctx)
        elif self._selection.state == SELECTING:
            self.draw_selecting_state(ctx)
        elif self._selection.state == SELECTED:
            self.draw_selected_state(ctx)
        ctx.restore()

    def draw_selected_state(self, ctx):
        if self._selection.item in (CHARACTER, COMPONENT):
            self._symbol.draw(ctx, self._hover_pos)
        elif self._selection.item in (OBJECT, RECT):
            if self._selected_canvas_symbol is not None:
                self.draw_object_outline(ctx, self._selected_canvas_symbol)
            else:
                self._selection.startpos = self._drag_startpos
                self._selection.endpos = self._drag_endpos
                self._selection.maxpos = self.max_pos_grid
                self._selection.draw(ctx)
                self.mark_all_objects(ctx)
        elif self._selection.item == OBJECTS:
            self.mark_all_objects(ctx)
            self.draw_selected_objects(ctx)

    def draw_selecting_state(self, ctx):
        if self._selection.item == OBJECT:
            self.mark_all_objects(ctx)
            if self._selected_canvas_symbol is None:
                self.draw_cursor(ctx)
            else:
                self.draw_object_outline(ctx, self._selected_canvas_symbol)
        elif self._selection.item in (TEXT, TEXT_BLOCK):
            self.draw_cursor(ctx)
            self._symbol.startpos = self._hover_pos.grid_cr()
            self._symbol.text = self._text
            self._symbol.draw(ctx)
        elif self._selection.item == MAG_LINE and self._wire_start is not None:
            end = self._wire_preview_end or self._wire_start
            terminal = self._terminal_at(end)
            if self._wire_preview_path:
                Wire(
                    self._wire_preview_path,
                    connected_start=self._wire_start_terminal is not None,
                    connected_end=terminal is not None or self._wire_at(end),
                ).draw(ctx)
        else:
            ctx.set_source_rgb(0.5, 0.5, 0.75)
            ctx.set_line_join(cairo.LINE_JOIN_ROUND)

            if self._selection.item in (ROW, COL):
                self._selection.startpos = self._hover_pos
            else:
                self._selection.startpos = self._drag_startpos
            self._selection.endpos = self._drag_currentpos
            self._selection.maxpos = self.max_pos_grid

            if self._selection.item == RECT:
                self.mark_all_objects(ctx)
                self._selection.draw(ctx)
            elif self._selection.item in (MAG_LINE, LINE, DIR_LINE, DRAW_RECT, ARROW):
                self._symbol.startpos = self._selection.startpos.grid_cr()
                self._symbol.endpos = self._selection.endpos.grid_cr()
                self._symbol.draw(ctx)
            elif self._selection.item:
                # draw it, if we have any valid (not None) selection
                self._selection.draw(ctx)

    def draw_cursor(self, ctx):
        ctx.save()
        ctx.set_line_width(1.5)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        if self._cursor_on:
            ctx.set_source_rgb(0.75, 0.75, 0.75)
        else:
            ctx.set_source_rgb(0.5, 0.5, 0.5)
        x, y = self._hover_pos.xy  # TODO meelopen met de tekst (blijft nu aan 't begin staan)
        ctx.rectangle(x, y, Preferences.values['GRIDSIZE_W'], Preferences.values['GRIDSIZE_H'])
        ctx.stroke()
        ctx.restore()

    def mark_all_objects(self, ctx):
        """Mark all objects on the grid canvas."""
        ctx.save()
        for ref in self._objects or []:
            if ref.symbol.has_pickpoint:
                if (self._show_symbol_pickpoints and ref.symbol.is_symbol) or \
                        (self._show_line_pickpoints and ref.symbol.is_line) or \
                        (self._show_text_pickpoints and ref.symbol.is_text):
                    ctx.set_source_rgb(1, 0, 0)
                    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                    # FIXME the pickpoint of a mostleft position (x=0) will not show as it falls of the grid
                    pos = ref.symbol.pickpoint_pos.view_xy()
                    # the text glyph origin is its left-bottom corner
                    y_xbase = pos.y + Preferences.values['FONTSIZE']
                    ctx.move_to(pos.x, y_xbase)
                    ctx.show_text(MARK_CHAR)  # mark the upper-left corner
        ctx.restore()

    def draw_object_outline(self, ctx, symbol):
        upper_left, lower_right = symbol.grid_bounds()
        top_left = upper_left.view_xy()
        size = Pos(lower_right.x - upper_left.x + 1, lower_right.y - upper_left.y + 1).view_xy()
        ctx.save()
        ctx.set_source_rgb(0.05, 0.48, 0.85)
        ctx.set_line_width(2)
        ctx.rectangle(top_left.x + 1, top_left.y + 1, size.x - 2, size.y - 2)
        ctx.stroke()
        ctx.restore()

    def draw_terminal_handles(self, ctx):
        if self._selection.item not in (OBJECT, LINE, MAG_LINE) and self._selected_canvas_symbol is None:
            return
        ctx.save()
        ctx.set_source_rgb(0.0, 0.35, 0.75)
        ctx.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        for symbol in self._canvas_objects:
            for terminal in symbol.terminal_positions():
                pos = terminal['position'].view_xy()
                ctx.move_to(pos.x, pos.y + Preferences.values['FONTSIZE'])
                ctx.show_text('O')
        ctx.restore()

    def _terminal_at(self, pos):
        for symbol in reversed(self._canvas_objects):
            for terminal in symbol.terminal_positions():
                if terminal['position'] == pos:
                    return terminal
        return None

    def _wire_at(self, pos):
        return any(getattr(symbol, '_is_wire', False) and pos in symbol.path
                   for symbol in self._canvas_objects)

    def on_wire_preview_result(self, path):
        self._wire_preview_path = path
        self.update()

    def draw_selected_objects(self, ctx):
        """Draw multiple objects selection."""
        ctx.save()
        for ref in self._objects:
            ctx.set_source_rgb(1, 0, 0)
            ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            # offset between the current position and the ul position of the original selection rectangle
            offset = self._hover_pos - ref.startpos.view_xy()
            pos = ref.symbol.startpos.view_xy() + offset
            ref.symbol.draw(ctx, pos)
        ctx.restore()

    def calc_position(self, x, y):
        """Calculate the grid view position."""
        pos = Pos(x, y)
        pos.snap_to_grid()
        return pos

    def on_drag_begin(self, widget, x_start, y_start):
        if self._selection.state == IDLE and self._selection.item in (DRAW_RECT, ARROW, RECT, ERASER, LINE, MAG_LINE, DIR_LINE):
            pass
        else:
            return
        pos = self.calc_position(x_start, y_start)
        self._drag_dir = None
        self._drag_startpos = pos
        self._drag_currentpos = pos
        self._drag_prevpos = []
        self._drag_prevpos.append(pos)
        self._selection.state = SELECTING

    def on_drag_end(self, widget, x_offset, y_offset):
        if self._selection.state == SELECTING and self._selection.item in (DRAW_RECT, ARROW, RECT, ERASER, LINE, MAG_LINE, DIR_LINE):
            pass
        else:
            return
        offset = self.calc_position(x_offset, y_offset)
        self._drag_endpos = self._drag_startpos + offset
        # position to grid (col, row) coordinates
        startpos = self._drag_startpos.grid_cr()
        endpos = self._drag_endpos.grid_cr()
        self._selection.state = SELECTED

        if self._selection.item == DRAW_RECT:
            pub.sendMessage('PASTE_RECT', startpos=startpos, endpos=endpos)

        elif self._selection.item == ARROW:
            pub.sendMessage('PASTE_ARROW', startpos=startpos, endpos=endpos)

        elif self._selection.item == RECT:
            pub.sendMessage('SELECTION_CHANGED', selected=True)

        elif self._selection.item == ERASER:
            size = offset.grid_cr().xy
            pub.sendMessage('ERASE', startpos=startpos, size=size)

        elif self._selection.item == LINE:
            if self._drag_dir == HORIZONTAL:
                endpos.y = startpos.y
            elif self._drag_dir == VERTICAL:
                endpos.x = startpos.x
            pub.sendMessage("PASTE_LINE", startpos=startpos, endpos=endpos, type=self._symbol.type)

        elif self._selection.item == MAG_LINE:
            pub.sendMessage("PASTE_MAG_LINE", startpos=startpos, endpos=endpos)

        elif self._selection.item == DIR_LINE:
            pub.sendMessage("PASTE_DIR_LINE", startpos=startpos, endpos=endpos)

        # Keep the chosen tool active, but reset its gesture for the next draw.
        self._selection.state = IDLE

    def on_drag_update(self, widget, x_offset, y_offset):
        if self._selection.state == SELECTING and self._selection.item in (DRAW_RECT, ARROW, RECT, ERASER, LINE, MAG_LINE, DIR_LINE):
            pass
        else:
            return
        offset = self.calc_position(x_offset, y_offset)
        pos = self._drag_startpos + offset
        pos.snap_to_grid()

        if self._selection.item in (DRAW_RECT, ARROW, RECT, ERASER, DIR_LINE, MAG_LINE):
            self._drag_currentpos = pos

        elif self._selection.item == LINE:
            self._drag_currentpos = pos
            # snap to either a horizontal or a vertical straight line
            self._drag_dir = self.pointer_dir()

    def pointer_dir(self):
        """Return the pointer direction in relation to the start position."""
        dx = abs(self._drag_currentpos.x - self._drag_startpos.x)
        dy = abs(self._drag_currentpos.y - self._drag_startpos.y)
        if dx > dy:
            dir = HORIZONTAL
        else:
            dir = VERTICAL
        return dir

    def pointer_dir_avg(self):
        """Return the pointer direction in relation to the previous position."""
        (x, y) = self._drag_currentpos.xy
        length = len(self._drag_prevpos)
        assert length > 0

        x_sum = 0
        y_sum = 0
        for pos in self._drag_prevpos:
            x_sum += pos.x
            y_sum += pos.y
        x_avg = x_sum / length
        y_avg = y_sum / length

        dx = abs(x - x_avg)
        dy = abs(y - y_avg)
        if dx > dy:
            dir = HORIZONTAL
        else:
            dir = VERTICAL

        # previous position keeps a list of the last n pointer locations
        self._drag_prevpos.append(Pos(x, y))
        if len(self._drag_prevpos) > 5:
            self._drag_prevpos.pop(0)
        return dir

    def set_grid_size(self):
        if self._grid is not None:
            self.set_viewport_size()

    def toggle_cursor(self):
        if time.time() - self.start_time > 0.5:
            self.start_time = time.time()
            self._cursor_on = not self._cursor_on
        self.update()

    def keyPressEvent(self, event):
        value = event.key()
        text = event.text()
        if value == Qt.Key.Key_Escape:
            self._wire_dragging = False
            self._wire_start = None
            self._wire_start_terminal = None
            self._wire_preview_end = None
            self._wire_preview_path = None
            if self._moving_symbol is not None:
                pub.sendMessage('CANCEL_MOVE_OBJECT', symbol=self._moving_symbol)
            self._selection = Selection(None)
            self._selected_canvas_symbol = None
            self._moving_symbol = None
            self._mouse_dragging = False
            self._send_active_tool(None)
            self.update()
            return
        if text.lower() == 'r' and self._selection.item in (CHARACTER, COMPONENT, OBJECTS, TEXT_BLOCK):
            pub.sendMessage('ROTATE_SYMBOL')
            return
        if text.lower() == 'm' and self._selection.item in (COMPONENT, OBJECTS, TEXT_BLOCK):
            pub.sendMessage('MIRROR_SYMBOL')
            return
        if value in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
            self._text = self._text[:-1]
        elif value in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._text += '\n'
        elif text and text.isprintable():
            self._text += text
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        self.setFocus()
        point = event.position()
        x, y = point.x(), point.y()
        pos = self.calc_position(x, y)
        pub.sendMessage('POINTER_MOVED', pos=pos.grid_cr())

        if self._selection.item == MAG_LINE and event.button() == Qt.MouseButton.LeftButton:
            self._wire_start = pos.grid_cr()
            self._wire_start_terminal = self._terminal_at(self._wire_start)
            self._wire_preview_end = self._wire_start
            self._wire_preview_path = [self._wire_start]
            self._wire_dragging = True
            self._mouse_dragging = True
            self._drag_startpos = pos
            self._drag_currentpos = pos
            self._selection.state = SELECTING
            self.update()
            event.accept()
            return

        if self._selection.item == OBJECT and event.button() == Qt.MouseButton.LeftButton:
            self._moving_symbol = None
            self._move_anchor = pos.grid_cr()
            pub.sendMessage('SELECT_OBJECT_AT', pos=pos.grid_cr())
            if self._selected_canvas_symbol is not None:
                symbol = self._selected_canvas_symbol
                self._moving_symbol = symbol
                self._move_old_start = Pos(symbol.startpos.x, symbol.startpos.y)
                self._move_old_end = Pos(symbol.endpos.x, symbol.endpos.y)
                self._move_bounds = symbol.grid_bounds()
                self._move_grab_offset = self._move_anchor - self._move_old_start
                self._mouse_dragging = True
            self.update()
            event.accept()
            return

        draw_items = (DRAW_RECT, ARROW, ERASER, RECT, LINE, MAG_LINE, DIR_LINE)
        if not Preferences.values['SELECTION_DRAG'] and self._selection.item in draw_items:
            if self._selection.state == IDLE:
                self.on_drag_begin(None, x, y)
            elif self._selection.state == SELECTING:
                offset = Pos(x, y) - self._drag_startpos
                self.on_drag_end(None, offset.x, offset.y)
        elif self._selection.state == SELECTING:
            self.selecting_state(pos, event)
        elif self._selection.state == SELECTED:
            self.selected_state(event)
        elif Preferences.values['SELECTION_DRAG'] and event.button() == Qt.MouseButton.LeftButton:
            self._mouse_dragging = True
            self.on_drag_begin(None, x, y)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        point = event.position()
        if self._wire_dragging:
            self._wire_preview_end = self.calc_position(point.x(), point.y()).grid_cr()
            terminal = self._terminal_at(self._wire_preview_end)
            pub.sendMessage(
                'WIRE_PREVIEW_REQUEST', startpos=self._wire_start,
                endpos=self._wire_preview_end,
                start_direction=(self._wire_start_terminal or {}).get('direction'),
                end_direction=(terminal or {}).get('direction'),
            )
        elif self._moving_symbol is not None:
            current = self.calc_position(point.x(), point.y()).grid_cr()
            candidate = current - self._move_grab_offset
            upper_left, lower_right = self._move_bounds
            dx = candidate.x - self._move_old_start.x
            dy = candidate.y - self._move_old_start.y
            dx = max(-upper_left.x, min(dx, self._grid.nr_cols - 1 - lower_right.x))
            dy = max(-upper_left.y, min(dy, self._grid.nr_rows - 1 - lower_right.y))
            new_start = self._move_old_start + Pos(dx, dy)
            delta = new_start - self._move_old_start
            new_end = self._move_old_end + delta if self._moving_symbol.is_line else self._move_old_end
            pub.sendMessage(
                'PREVIEW_MOVE_OBJECT', symbol=self._moving_symbol,
                startpos=new_start, endpos=new_end,
            )
        elif self._mouse_dragging and self._drag_startpos is not None:
            offset = Pos(point.x(), point.y()) - self._drag_startpos
            self.on_drag_update(None, offset.x, offset.y)
        self.on_hover(None, event)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._wire_dragging and event.button() == Qt.MouseButton.LeftButton:
            end = self.calc_position(event.position().x(), event.position().y()).grid_cr()
            terminal = self._terminal_at(end)
            if end != self._wire_start:
                pub.sendMessage(
                    'WIRE_PREVIEW_REQUEST', startpos=self._wire_start,
                    endpos=end,
                    start_direction=(self._wire_start_terminal or {}).get('direction'),
                    end_direction=(terminal or {}).get('direction'),
                )
                pub.sendMessage(
                    'PASTE_WIRE',
                    startpos=self._wire_start,
                    endpos=end,
                    start_direction=(self._wire_start_terminal or {}).get('direction'),
                    end_direction=(terminal or {}).get('direction'),
                    connected_start=self._wire_start_terminal is not None or self._wire_at(self._wire_start),
                    connected_end=terminal is not None or self._wire_at(end),
                )
            self._wire_dragging = False
            self._wire_start = None
            self._wire_start_terminal = None
            self._wire_preview_end = None
            self._wire_preview_path = None
            self._mouse_dragging = False
            self._selection.state = IDLE
        elif self._moving_symbol is not None and event.button() == Qt.MouseButton.LeftButton:
            symbol = self._moving_symbol
            new_start = Pos(symbol.startpos.x, symbol.startpos.y)
            new_end = Pos(symbol.endpos.x, symbol.endpos.y)
            pub.sendMessage(
                'MOVE_OBJECT', symbol=symbol,
                old_start=self._move_old_start, old_end=self._move_old_end,
                new_start=new_start, new_end=new_end,
            )
            self._moving_symbol = None
            self._mouse_dragging = False
            self._set_object_selection_bounds(symbol)
            self._selection.state = SELECTING
        elif self._mouse_dragging and event.button() == Qt.MouseButton.LeftButton:
            point = event.position()
            offset = Pos(point.x(), point.y()) - self._drag_startpos
            self.on_drag_update(None, offset.x, offset.y)
            self.on_drag_end(None, offset.x, offset.y)
            self._mouse_dragging = False
        self.update()
        event.accept()

    @staticmethod
    def _send_active_tool(tool):
        pub.sendMessage('ACTIVE_TOOL_CHANGED', tool=tool)

    def on_hover(self, widget, event):
        if not self.hasFocus():
            self.setFocus()
        point = event.position()
        width = Preferences.values['GRIDSIZE_W']
        height = Preferences.values['GRIDSIZE_H']
        self._hover_pos = self.calc_position(point.x(), point.y())
        delta = self._hover_previous_pos - self._hover_pos
        moved_enough = abs(delta.x) > width / 2 or abs(delta.y) > height / 2
        if moved_enough:
            self._hover_previous_pos = self._hover_pos
            pub.sendMessage('POINTER_MOVED', pos=self._hover_pos.grid_cr())
        if self._selection.state == SELECTING and self._selection.item == OBJECT and moved_enough:
            pub.sendMessage('SELECTOR_MOVED', pos=self._hover_pos.grid_cr())
        if not Preferences.values['SELECTION_DRAG'] and self._selection.state == SELECTING and \
                self._selection.item in (DRAW_RECT, ARROW, RECT, ERASER, LINE, MAG_LINE, DIR_LINE):
            offset = Pos(point.x(), point.y()) - self._drag_startpos
            if moved_enough:
                self.on_drag_update(None, offset.x, offset.y)

    def selected_state(self, event):
        pos = self._hover_pos.grid_cr()
        if self._selection.item in (CHARACTER, COMPONENT, OBJECTS):
            if event.button() == Qt.MouseButton.LeftButton:
                pub.sendMessage('PASTE_OBJECTS', pos=pos)
            elif event.button() == Qt.MouseButton.RightButton:
                pub.sendMessage('ROTATE_SYMBOL')

    def selecting_state(self, pos, event):
        button = event.button()
        if self._selection.item == ROW:
            pub.sendMessage('GRID_ROW', row=pos.grid_cr().y, action=self._selection.action)
        elif self._selection.item == COL:
            pub.sendMessage('GRID_COL', col=pos.grid_cr().x, action=self._selection.action)
        elif self._selection.item in (TEXT, TEXT_BLOCK):
            if button == Qt.MouseButton.LeftButton:
                self._selection.state = SELECTED
                self._symbol.startpos = pos.grid_cr()
                pub.sendMessage('PASTE_TEXT', symbol=self._symbol)
            elif button == Qt.MouseButton.RightButton:
                self._symbol.rotate()
                pub.sendMessage('ORIENTATION_CHANGED', ori=self._symbol.ori_as_str)
        elif self._selection.item == OBJECT and button == Qt.MouseButton.LeftButton:
            self._selection.state = SELECTED
            ul = pos
            br = ul + Pos(Preferences.values['GRIDSIZE_W'], Preferences.values['GRIDSIZE_H'])
            self._drag_startpos = ul
            self._drag_endpos = br
            self._selection.startpos = ul
            self._selection.endpos = br
            self._selection.maxpos = self.max_pos_grid
            pub.sendMessage('SELECTION_CHANGED', selected=True)
