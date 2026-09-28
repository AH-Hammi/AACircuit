"""Main AACircuit window implemented with PySide6."""

import os
import sys
import time

from pubsub import pub
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QButtonGroup,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from application import ERROR, INFO, INSERT, REMOVE
from application import gettext as _
from application.component_view import ComponentView
from application.grid_view import GridView
from application.magic_line_settings import MagicLineSettingsDialog
from application.preferences import Preferences, PreferencesDialog
from application.symbol import Line

_qt_app = None


def ensure_qapplication():
    global _qt_app
    app = QApplication.instance()
    if app is None:
        if os.name != 'nt' and not os.environ.get('DISPLAY'):
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        _qt_app = QApplication(sys.argv[:1])
        app = _qt_app
    return app


class MainWindow(QMainWindow):
    def __init__(self):
        ensure_qapplication()
        super().__init__()
        self.setWindowTitle(_("AACircuit"))
        self.resize(1200, 700)
        self._last_msg_type = None
        self._start_time = time.time()
        self._undo_stack_empty = True

        self._build_menus()
        self._build_central_widget()
        self._subscribe()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu(_("&File"))
        self.menu_new = self._action(file_menu, _("New"), 'NEW_FILE', 'Ctrl+N')
        self.menu_open = self._action(file_menu, _("Open…"), 'OPEN_FILE', 'Ctrl+O')
        self.menu_save = self._action(file_menu, _("Save"), 'SAVE_FILE', 'Ctrl+S')
        self.menu_save_as = self._action(file_menu, _("Save as…"), 'SAVE_AS_FILE', 'Ctrl+Shift+S')
        self.menu_save.setEnabled(False)
        file_menu.addSeparator()
        self._action(file_menu, _("Export as ASCII…"), 'EXPORT_AS_ASCII')
        file_menu.addSeparator()
        quit_action = file_menu.addAction(_("Quit"))
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)

        edit_menu = self.menuBar().addMenu(_("&Edit"))
        self.menu_cut = edit_menu.addAction(_("Cut"))
        self.menu_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.menu_cut.triggered.connect(lambda: self._send_selection_event('CUT'))
        self.menu_copy = edit_menu.addAction(_("Copy selection"))
        self.menu_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.menu_copy.triggered.connect(lambda: self._send_selection_event('COPY'))
        self.menu_paste = edit_menu.addAction(_("Paste grid from clipboard"))
        self.menu_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.menu_paste.triggered.connect(lambda: pub.sendMessage('PASTE_GRID'))
        edit_menu.addSeparator()
        self.menu_undo = self._action(edit_menu, _("Undo"), 'UNDO', 'Ctrl+Z')
        self.menu_redo = self._action(edit_menu, _("Redo"), 'REDO', 'Ctrl+Shift+Z')
        self.menu_undo.setEnabled(False)
        self.menu_redo.setEnabled(False)
        edit_menu.addSeparator()
        self._action(edit_menu, _("Copy grid"), 'COPY_GRID')
        self._action(edit_menu, _("Paste grid"), 'PASTE_GRID')
        self._action(edit_menu, _("Load and paste ASCII…"), 'LOAD_AND_PASTE_GRID')
        edit_menu.addSeparator()
        self._action(edit_menu, _("Edit draw commands…"), 'EDIT_MEMO')

        view_menu = self.menuBar().addMenu(_("&View"))
        size_menu = view_menu.addMenu(_("Grid size"))
        for index, (cols, rows) in enumerate(((72, 36), (72, 49), (100, 49), (200, 70)), 1):
            action = size_menu.addAction(_("{} × {} cells").format(cols, rows))
            action.triggered.connect(
                lambda _checked=False, c=cols, r=rows: pub.sendMessage('GRID_SIZE', cols=c, rows=r)
            )
        self._action(view_menu, _("Redraw schema"), 'REDRAW_GRID', 'F5')
        view_menu.addSeparator()
        self.pickpoint_actions = []
        for label, event in (
            (_("Symbol pickpoints"), 'SHOW_SYMBOL_PICKPOINTS'),
            (_("Line pickpoints"), 'SHOW_LINE_PICKPOINTS'),
            (_("Text pickpoints"), 'SHOW_TEXT_PICKPOINTS'),
        ):
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, name=event: pub.sendMessage(name, state=checked))
            self.pickpoint_actions.append(action)

        symbol_menu = self.menuBar().addMenu(_("&Symbol"))
        self.menu_rotate = self._action(symbol_menu, _("Rotate 90° clockwise"), 'ROTATE_SYMBOL')
        self.menu_mirror = self._action(symbol_menu, _("Mirror vertically"), 'MIRROR_SYMBOL')
        self.menu_rotate.setEnabled(False)
        self.menu_mirror.setEnabled(False)

        app_menu = self.menuBar().addMenu(_("AACircuit"))
        self._action(app_menu, _("About AACircuit"), 'ABOUT')
        app_menu.addSeparator()
        self._action(app_menu, _("Preferences…"), 'PREFERENCES', 'Ctrl+,')
        self._action(app_menu, _("Magic-line settings…"), 'MAGIC_LINE_SETTINGS')

    def _action(self, menu, text, event, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False, name=event: self._dispatch(name))
        menu.addAction(action)
        return action

    def _dispatch(self, event):
        handlers = {
            'ABOUT': self.show_about,
            'PREFERENCES': self.show_preferences,
            'MAGIC_LINE_SETTINGS': self.show_magic_line_settings,
        }
        handler = handlers.get(event)
        if handler is not None:
            handler()
        else:
            pub.sendMessage(event)

    def _build_central_widget(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}

        char_row = QHBoxLayout()
        for char in ('+', 'o', '#', '/', '\\', '|', '-', '(', ')', "'", '.'):
            button = QPushButton(char, central)
            button.setFixedWidth(32)
            self._register_tool_button(button, 'character:' + char)
            button.clicked.connect(lambda _checked=False, value=char: pub.sendMessage('CHARACTER_CHANGED', char=value))
            char_row.addWidget(button)
        space_button = QPushButton(_("Space"), central)
        space_button.clicked.connect(lambda: pub.sendMessage('ERASER', size=(1, 1)))
        char_row.addWidget(space_button)
        copy_grid_button = QPushButton(_("Copy grid"), central)
        copy_grid_button.setObjectName('copy_grid_button')
        copy_grid_button.setToolTip(_("Copy the ASCII drawing to the clipboard"))
        copy_grid_button.clicked.connect(lambda: pub.sendMessage('COPY_GRID'))
        char_row.addWidget(copy_grid_button)
        char_row.addWidget(QLabel(_("Text:"), central))
        self.text_entry = QLineEdit(central)
        self.text_entry.setMaximumWidth(240)
        char_row.addWidget(self.text_entry)
        add_text_button = QPushButton(_("Insert text"), central)
        self._register_tool_button(add_text_button, 'insert_text')
        add_text_button.clicked.connect(lambda: pub.sendMessage('ADD_TEXT'))
        char_row.addWidget(add_text_button)
        add_textblock_button = QPushButton(_("Insert text line"), central)
        self._register_tool_button(add_textblock_button, 'insert_text_line')
        add_textblock_button.clicked.connect(
            lambda: pub.sendMessage('ADD_TEXTBLOCK', text=self.text_entry.text())
        )
        char_row.addWidget(add_textblock_button)
        char_row.addStretch(1)
        layout.addLayout(char_row)

        body = QHBoxLayout()
        tools = QVBoxLayout()
        self._add_tool_button(tools, _("Select object"), lambda: pub.sendMessage('SELECT_OBJECT'), 'select_object')
        self._add_tool_button(tools, _("Select rectangle"), lambda: pub.sendMessage('SELECT_RECT'), 'select_rect')
        self._add_tool_button(tools, _("Eraser"), lambda: pub.sendMessage('SELECTING_ERASER'), 'eraser')
        tools.addWidget(self._separator())
        self._add_tool_button(tools, _("Rotate"), lambda: pub.sendMessage('ROTATE_SYMBOL'))
        self._add_tool_button(tools, _("Mirror"), lambda: pub.sendMessage('MIRROR_SYMBOL'))
        tools.addWidget(self._separator())
        for index, title in enumerate((_("Free line"), _("Line"), _("Line with o terminals"), _("Line with + terminals"), _("Line with terminals")), 0):
            button = QPushButton(title, central)
            self._register_tool_button(button, 'free_line' if index == 0 else 'line_{}'.format(index))
            button.clicked.connect(lambda _checked=False, nr=index: self.on_line(nr))
            tools.addWidget(button)
        self._add_tool_button(tools, _("Automatic line"), lambda: pub.sendMessage('DRAW_MAG_LINE'), 'auto_line')
        self._add_tool_button(tools, _("Rectangle"), lambda: pub.sendMessage('DRAW_RECT'), 'draw_rect')
        self._add_tool_button(tools, _("Arrow"), lambda: pub.sendMessage('DRAW_ARROW'), 'arrow')
        tools.addWidget(self._separator())
        self._add_tool_button(tools, _("Insert row"), lambda: self._selecting_row('insert_row'), 'insert_row')
        self._add_tool_button(tools, _("Insert column"), lambda: self._selecting_col('insert_col'), 'insert_col')
        self._add_tool_button(tools, _("Remove row"), lambda: self._selecting_row('remove_row'), 'remove_row')
        self._add_tool_button(tools, _("Remove column"), lambda: self._selecting_col('remove_col'), 'remove_col')
        self._add_tool_button(tools, _("Edit draw commands"), lambda: pub.sendMessage('EDIT_MEMO'))
        tools.addStretch(1)
        body.addLayout(tools)

        self.grid_view = GridView()
        self.grid_view.setObjectName('grid_view')
        self.grid_scroll = QScrollArea(central)
        self.grid_scroll.setWidgetResizable(False)
        self.grid_scroll.setWidget(self.grid_view)
        body.addWidget(self.grid_scroll, 1)

        self.component_view = ComponentView(central)
        self.component_view.setObjectName('component_list')
        body.addWidget(self.component_view)
        layout.addLayout(body, 1)

        status = QWidget(central)
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(2, 0, 2, 0)
        status_layout.addWidget(QLabel(_("x"), status))
        self.label_xpos = QLineEdit(status)
        self.label_xpos.setReadOnly(True)
        self.label_xpos.setMaximumWidth(55)
        status_layout.addWidget(self.label_xpos)
        status_layout.addWidget(QLabel(_("y"), status))
        self.label_ypos = QLineEdit(status)
        self.label_ypos.setReadOnly(True)
        self.label_ypos.setMaximumWidth(55)
        status_layout.addWidget(self.label_ypos)
        self.label_orientation = QLabel(_("Orientation"), status)
        self.label_orientation.setMinimumWidth(90)
        status_layout.addWidget(self.label_orientation)
        self.msg = QLabel(status)
        status_layout.addWidget(self.msg, 1)
        layout.addWidget(status)
        self.setCentralWidget(central)

    @staticmethod
    def _separator():
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet('background-color: palette(mid);')
        return line

    def _register_tool_button(self, button, tool):
        button.setCheckable(True)
        button.setObjectName('tool_' + tool.replace(':', '_').replace('\\', 'backslash').replace("'", 'quote'))
        button.setStyleSheet(
            'QPushButton:checked { background-color: #b9d9f5; '
            'border: 2px solid #2864a0; font-weight: bold; }'
        )
        self.tool_group.addButton(button)
        self.tool_buttons[tool] = button
        return button

    def _add_tool_button(self, layout, text, callback, tool=None):
        button = QPushButton(text)
        if tool is not None:
            self._register_tool_button(button, tool)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _subscribe(self):
        pub.subscribe(self.on_pointer_moved, 'POINTER_MOVED')
        pub.subscribe(self.on_message, 'STATUS_MESSAGE')
        pub.subscribe(self.on_orientation_changed, 'ORIENTATION_CHANGED')
        pub.subscribe(self.on_file_opened, 'FILE_OPENED')
        pub.subscribe(self.on_new_file, 'NEW_FILE')
        pub.subscribe(self.on_nothing_selected, 'NOTHING_SELECTED')
        pub.subscribe(self.on_component_changed, 'COMPONENT_CHANGED')
        pub.subscribe(self.on_character_changed, 'CHARACTER_CHANGED')
        pub.subscribe(self.on_active_tool_changed, 'ACTIVE_TOOL_CHANGED')
        pub.subscribe(self.on_symbol_selected, 'SYMBOL_SELECTED')
        pub.subscribe(self.on_selection_changed, 'SELECTION_CHANGED')
        pub.subscribe(self.on_undo_changed, 'UNDO_CHANGED')
        pub.subscribe(self.on_redo_changed, 'REDO_CHANGED')

    def _selection_rect(self):
        if self.grid_view._drag_startpos is None or self.grid_view._drag_endpos is None:
            return None
        return self.grid_view.drag_rect

    def _send_selection_event(self, event):
        rect = self._selection_rect()
        if rect is not None:
            pub.sendMessage(event, rect=rect)

    def _selecting_row(self, name):
        pub.sendMessage('NOTHING_SELECTED')
        pub.sendMessage('SELECTING_ROW', action=INSERT if name == 'insert_row' else REMOVE)

    def _selecting_col(self, name):
        pub.sendMessage('NOTHING_SELECTED')
        pub.sendMessage('SELECTING_COL', action=INSERT if name == 'insert_col' else REMOVE)

    def on_line(self, index):
        line_type = {
            1: Line.LINE1,
            2: Line.LINE2,
            3: Line.LINE3,
            4: Line.LINE4,
        }.get(index, Line.LINE1)
        pub.sendMessage(f'DRAW_LINE{index}', type=line_type)

    def _clear_tool_highlight(self):
        self.tool_group.setExclusive(False)
        for button in self.tool_buttons.values():
            button.setChecked(False)
        self.tool_group.setExclusive(True)

    def on_active_tool_changed(self, tool):
        button = self.tool_buttons.get(tool)
        if button is None:
            self._clear_tool_highlight()
        elif not button.isChecked():
            button.setChecked(True)

    def on_component_changed(self, label):
        self._clear_tool_highlight()

    def on_character_changed(self, char):
        self.on_active_tool_changed('character:' + char)

    def on_pointer_moved(self, pos):
        self.label_xpos.setText(str(pos.x))
        self.label_ypos.setText(str(pos.y))

    def on_orientation_changed(self, ori):
        self.label_orientation.setText(ori)

    def on_message(self, msg, type=INFO):
        now = time.time()
        if self._last_msg_type != ERROR or now - self._start_time > 5:
            self._start_time = now
            self._last_msg_type = type
            self.msg.setText(msg)
            color = '#a00000' if type == ERROR else '#805000' if type == 'warning' else ''
            self.msg.setStyleSheet(f'color: {color};' if color else '')

    def on_file_opened(self):
        self.menu_save.setEnabled(True)

    def on_new_file(self):
        self.menu_save.setEnabled(False)

    def on_nothing_selected(self):
        self.on_selection_changed(selected=False)
        self.menu_rotate.setEnabled(False)
        self.menu_mirror.setEnabled(False)

    def on_symbol_selected(self, symbol):
        self.menu_rotate.setEnabled(True)
        self.menu_mirror.setEnabled(True)

    def on_selection_changed(self, selected=False):
        self.menu_copy.setEnabled(selected)
        self.menu_cut.setEnabled(selected)

    def on_undo_changed(self, undo=False):
        self._undo_stack_empty = not undo
        self.menu_undo.setEnabled(undo)

    def on_redo_changed(self, redo=False):
        self.menu_redo.setEnabled(redo)

    def show_about(self):
        QMessageBox.about(
            self,
            _("About AACircuit"),
            _("AACircuit — draw electronic circuits with ASCII characters.\n\n"
              "A Python version of AACircuit by Andreas Weber."),
        )

    def show_preferences(self):
        previous_symbol_set = Preferences.values['SYMBOL_SET']
        dialog = PreferencesDialog(self)
        if dialog.exec():
            self.grid_view.set_grid_size()
            symbol_set = Preferences.values['SYMBOL_SET']
            if symbol_set != previous_symbol_set:
                pub.sendMessage('SYMBOL_SET_CHANGED', symbol_set=symbol_set)

    def show_magic_line_settings(self):
        MagicLineSettingsDialog(self).exec()

    def closeEvent(self, event):
        if self._undo_stack_empty or self.show_confirmation_dlg():
            print(_("Closing application"))
            event.accept()
        else:
            event.ignore()

    def show_confirmation_dlg(self):
        return QMessageBox.question(
            self,
            _("Unsaved changes"),
            _("Close AACircuit and discard the current changes?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
