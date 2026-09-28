"""User settings and the Qt preferences dialog."""

import collections
import json

from pubsub import pub
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from application import get_path_to_prefs
from application import gettext as _

PreferenceSetting = collections.namedtuple('PreferenceSetting', ['type', 'entry'])


class Preferences:
    values = {
        'DEFAULT_ROWS': 36,
        'DEFAULT_COLS': 72,
        'FONTSIZE': 12,
        'GRIDSIZE_W': 10,
        'GRIDSIZE_H': 16,
        'PANGO_FONT': False,
        'FONT': 'monospace',
        'SELECTION_DRAG': False,
        'LINE_HOR': '-',
        'LINE_VERT': '|',
        'CROSSING': ')',
        'LOWER_CORNER': "'",
        'UPPER_CORNER': '.',
        'TERMINAL1': None,
        'TERMINAL2': 'o',
        'TERMINAL3': '+',
        'TERMINAL4': "'",
        'TERMINAL4_VERT': '.',
    }

    def __init__(self, filename=None):
        self._filename = filename or get_path_to_prefs()
        self.read_preferences()
        pub.subscribe(self.on_save_preferences, 'SAVE_PREFERENCES')

    def has_value(self, name):
        return name in self.values

    def nr_values(self):
        return len(self.values)

    def get_value(self, name):
        print("Deprecated method: ", self.get_value.__name__)
        try:
            return self.values[name]
        except KeyError:
            print("Unknown preference name", name)
            raise

    def set_pref(self, name, value):
        self.values[name] = value

    def read_preferences(self):
        try:
            with open(self._filename, 'r', encoding='utf-8') as settings_file:
                saved_values = json.load(settings_file)
            self.values.update(saved_values)
            print(_("Preferences have been read from: %s" % self._filename))
        except (OSError, ValueError):
            print(_("Preferences file not found: %s, default preferences are being used" % self._filename))

    def on_save_preferences(self):
        try:
            with open(self._filename, 'w', encoding='utf-8') as settings_file:
                json.dump(self.values, settings_file)
            pub.sendMessage('STATUS_MESSAGE', msg=_("Preferences have been saved in: %s" % self._filename))
        except OSError:
            pub.sendMessage('STATUS_MESSAGE', msg=_("Unable to open file for writing: %s" % self._filename))


class NumberEntry(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setValidator(QIntValidator(1, 9999, self))


class SingleCharEntry(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.textChanged.connect(self._limit_text)

    def _limit_text(self, text):
        if len(text) > 1:
            self.setText(text[:1])


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Preferences"))
        self.setMinimumWidth(380)
        self.entries = {}

        layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        grid_page = QWidget(self)
        grid_form = QFormLayout(grid_page)
        self._add_dimension(grid_form, _("Number of rows"), 'DEFAULT_ROWS')
        self._add_dimension(grid_form, _("Number of columns"), 'DEFAULT_COLS')
        self._add_dimension(grid_form, _("Cell width"), 'GRIDSIZE_W')
        self._add_dimension(grid_form, _("Cell height"), 'GRIDSIZE_H')
        self._add_dimension(grid_form, _("Font size"), 'FONTSIZE')
        self._add_boolean(grid_form, _("Use selected font"), 'PANGO_FONT')
        font = QFontComboBox(self)
        selected_font = QFont()
        if not selected_font.fromString(str(self._value('FONT'))):
            selected_font.setFamily(str(self._value('FONT')))
        font.setCurrentFont(selected_font)
        self.entries['FONT'] = PreferenceSetting('font', font)
        grid_form.addRow(_("Font"), font)
        self._add_boolean(grid_form, _("Drag selection"), 'SELECTION_DRAG')
        tabs.addTab(grid_page, _("Grid"))

        lines_page = QWidget(self)
        lines_form = QFormLayout(lines_page)
        for label, key in (
            (_("Horizontal line"), 'LINE_HOR'),
            (_("Vertical line"), 'LINE_VERT'),
            (_("Terminal 1"), 'TERMINAL1'),
            (_("Terminal 2"), 'TERMINAL2'),
            (_("Terminal 3"), 'TERMINAL3'),
            (_("Terminal 4"), 'TERMINAL4'),
            (_("Terminal 4 vertical start"), 'TERMINAL4_VERT'),
        ):
            self._add_character(lines_form, label, key)
        tabs.addTab(lines_page, _("Lines"))

        magic_page = QWidget(self)
        magic_form = QFormLayout(magic_page)
        for label, key in (
            (_("Crossing character"), 'CROSSING'),
            (_("Upper corner character"), 'UPPER_CORNER'),
            (_("Lower corner character"), 'LOWER_CORNER'),
        ):
            self._add_character(magic_form, label, key)
        tabs.addTab(magic_page, _("Magic line"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _value(key):
        return Preferences.values[key]

    def _add_dimension(self, form, label, key):
        entry = NumberEntry(self)
        entry.setText(str(self._value(key)))
        self.entries[key] = PreferenceSetting('dim', entry)
        form.addRow(label, entry)

    def _add_character(self, form, label, key):
        entry = SingleCharEntry(self)
        value = self._value(key)
        entry.setText('' if value is None else str(value))
        self.entries[key] = PreferenceSetting('str', entry)
        form.addRow(label, entry)

    def _add_boolean(self, form, label, key):
        entry = QCheckBox(self)
        entry.setChecked(bool(self._value(key)))
        self.entries[key] = PreferenceSetting('bool', entry)
        form.addRow(label, entry)

    def _save(self):
        for key, setting in self.entries.items():
            entry = setting.entry
            if setting.type == 'str':
                value = entry.text()
            elif setting.type == 'dim':
                value = int(entry.text())
            elif setting.type == 'bool':
                value = entry.isChecked()
            else:
                value = entry.currentFont().family()
            Preferences.values[key] = value
        pub.sendMessage('SAVE_PREFERENCES')
        self.accept()
