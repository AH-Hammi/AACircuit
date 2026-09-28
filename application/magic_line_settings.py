"""Magic-line matching rules and their Qt editor."""

import collections
import copy
import json

from pubsub import pub
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from application import HORIZONTAL, LONGEST_FIRST, VERTICAL
from application import gettext as _
from application.preferences import SingleCharEntry

LineMatchingData = collections.namedtuple('line_matching_data', ['pattern', 'ori', 'char'])


class MagicLineSettings:
    LMD = []

    def __init__(self, filename='magic_line.ini'):
        self._filename = filename
        self.read_settings()
        pub.subscribe(self.on_save_settings, 'SAVE_MAGIC_LINE_SETTINGS')
        pub.subscribe(self.load_default_settings, 'RESTORE_DEFAULT_MAGIC_LINE_SETTINGS')

    def read_settings(self):
        try:
            with open(self._filename, 'r', encoding='utf-8') as settings_file:
                self.load_settings_from_str(settings_file.read())
            print(_("Magic-line settings have been read from: %s" % self._filename))
        except (OSError, ValueError, KeyError):
            self.load_default_settings()
            print(_("Magic line default settings are being used"))

    def on_save_settings(self):
        try:
            with open(self._filename, 'w', encoding='utf-8') as settings_file:
                settings_file.write(self.settings_to_str())
            pub.sendMessage('STATUS_MESSAGE', msg=_("Magic line settings have been saved in: %s" % self._filename))
        except OSError:
            pub.sendMessage('STATUS_MESSAGE', msg=_("Unable to open file for writing: %s" % self._filename))

    def settings_to_str(self):
        return ''.join(json.dumps({
            'pattern': lmd.pattern,
            'ori': lmd.ori,
            'char': lmd.char,
        }) + '\n' for lmd in self.LMD)

    def load_settings_from_str(self, text):
        parsed = []
        for line in text.splitlines():
            item = json.loads(line)
            parsed.append(LineMatchingData(item['pattern'], item['ori'], item['char']))
        if parsed:
            MagicLineSettings.LMD = parsed
        else:
            self.load_default_settings()

    def load_default_settings(self):
        MagicLineSettings.LMD = [
            LineMatchingData([[' ', ' ', ' '], [' ', ' ', ' '], [' ', ' ', ' ']], LONGEST_FIRST, 'o'),
            LineMatchingData([['x', 'x', 'x'], ['-', 'x', '-'], ['x', 'x', 'x']], VERTICAL, 'o'),
            LineMatchingData([['x', '|', 'x'], ['x', 'x', 'x'], ['x', '|', 'x']], HORIZONTAL, 'o'),
            LineMatchingData([['x', 'x', 'x'], ['x', 'x', '-'], ['x', 'x', 'x']], HORIZONTAL, '-'),
            LineMatchingData([['x', 'x', 'x'], ['-', 'x', 'x'], ['x', 'x', 'x']], HORIZONTAL, '-'),
            LineMatchingData([['x', 'x', 'x'], ['x', 'x', 'x'], [' ', '|', ' ']], VERTICAL, '|'),
            LineMatchingData([[' ', '|', ' '], ['x', 'x', 'x'], ['x', 'x', 'x']], VERTICAL, '|'),
            LineMatchingData([['x', 'x', 'x'], ['x', 'x', 'x'], ['x', '|', 'x']], HORIZONTAL, '.'),
            LineMatchingData([['x', '|', 'x'], ['x', 'x', 'x'], ['x', 'x', 'x']], HORIZONTAL, "'"),
            LineMatchingData([['x', 'x', 'x'], ['x', '|', 'x'], ['x', 'x', 'x']], VERTICAL, '|'),
        ]


class MagicLineSettingsDialog(QDialog):
    DIRECTIONS = (
        (HORIZONTAL, _("Horizontal")),
        (VERTICAL, _("Vertical")),
        (LONGEST_FIRST, _("Longest first")),
    )

    def __init__(self, parent=None):
        super().__init__(parent or QApplication.activeWindow())
        self.setWindowTitle(_("Magic-line settings"))
        self.resize(520, 330)
        self.matrix_nr = 0
        self.lmd = copy.deepcopy(MagicLineSettings.LMD)
        self._updating_matrix = False

        layout = QVBoxLayout(self)
        settings_layout = QHBoxLayout()
        layout.addLayout(settings_layout)

        self.matrix_group = QGroupBox(self)
        matrix_layout = QVBoxLayout(self.matrix_group)
        self.matrix_view = QTableWidget(3, 3, self.matrix_group)
        self.matrix_view.horizontalHeader().hide()
        self.matrix_view.verticalHeader().hide()
        self.matrix_view.setFixedSize(150, 140)
        self.matrix_view.setColumnWidth(0, 42)
        self.matrix_view.setColumnWidth(1, 42)
        self.matrix_view.setColumnWidth(2, 42)
        for row in range(3):
            self.matrix_view.setRowHeight(row, 38)
        self.matrix_view.itemChanged.connect(self.on_matrix_changed)
        matrix_layout.addWidget(self.matrix_view, alignment=Qt.AlignmentFlag.AlignCenter)
        settings_layout.addWidget(self.matrix_group)

        form = QFormLayout()
        settings_layout.addLayout(form)
        self.start_direction = QComboBox(self)
        for value, title in self.DIRECTIONS:
            self.start_direction.addItem(title, value)
        self.start_direction.currentIndexChanged.connect(self.on_start_direction_changed)
        form.addRow(_("Start direction"), self.start_direction)

        self.start_character = SingleCharEntry(self)
        self.start_character.textChanged.connect(self.on_start_character_changed)
        form.addRow(_("Start character"), self.start_character)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton(_("‹ Previous"), self)
        self.previous_button.clicked.connect(self.on_previous_matrix)
        navigation.addWidget(self.previous_button)
        self.next_button = QPushButton(_("Next ›"), self)
        self.next_button.clicked.connect(self.on_next_matrix)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)

        actions = QHBoxLayout()
        self.restore_button = QPushButton(_("Restore defaults"), self)
        self.restore_button.clicked.connect(self.on_restore_defaults_clicked)
        actions.addWidget(self.restore_button)
        self.delete_button = QPushButton(_("Delete"), self)
        self.delete_button.clicked.connect(self.on_delete_matrix)
        actions.addWidget(self.delete_button)
        self.create_button = QPushButton(_("Create new"), self)
        self.create_button.clicked.connect(self.on_create_new_matrix)
        actions.addWidget(self.create_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.on_save_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_line_matching_data()

    def update_line_matching_data(self):
        if not self.lmd:
            return
        self.matrix_nr = min(self.matrix_nr, len(self.lmd) - 1)
        lmd = self.lmd[self.matrix_nr]
        self.matrix_group.setTitle(_("Decision matrix [{}]").format(self.matrix_nr + 1))
        self._updating_matrix = True
        self.matrix_view.clearContents()
        for row in range(3):
            for col in range(3):
                item = QTableWidgetItem(str(lmd.pattern[row][col]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.matrix_view.setItem(row, col, item)
        self.start_character.setText(lmd.char)
        self.start_direction.setCurrentIndex(
            next((i for i, (value, _) in enumerate(self.DIRECTIONS) if value == lmd.ori), 0)
        )
        self._updating_matrix = False
        pub.sendMessage('MATCHING_DATA_CHANGED', lmd=lmd)

    def on_matrix_changed(self, item):
        if self._updating_matrix or not self.lmd:
            return
        lmd = self.lmd[self.matrix_nr]
        pattern = copy.deepcopy(lmd.pattern)
        pattern[item.row()][item.column()] = item.text()[:1]
        self.lmd[self.matrix_nr] = LineMatchingData(pattern, lmd.ori, lmd.char)
        pub.sendMessage('MATCHING_DATA_CHANGED', lmd=self.lmd[self.matrix_nr])

    def on_next_matrix(self):
        if self.lmd:
            self.matrix_nr = (self.matrix_nr + 1) % len(self.lmd)
            self.update_line_matching_data()

    def on_previous_matrix(self):
        if self.lmd:
            self.matrix_nr = (self.matrix_nr - 1) % len(self.lmd)
            self.update_line_matching_data()

    def on_start_direction_changed(self, index):
        if self._updating_matrix or not self.lmd or index < 0:
            return
        lmd = self.lmd[self.matrix_nr]
        self.lmd[self.matrix_nr] = LineMatchingData(lmd.pattern, self.start_direction.currentData(), lmd.char)

    def on_start_character_changed(self, char):
        if self._updating_matrix or not self.lmd:
            return
        lmd = self.lmd[self.matrix_nr]
        self.lmd[self.matrix_nr] = LineMatchingData(lmd.pattern, lmd.ori, char)

    def on_create_new_matrix(self):
        pattern = [['x', 'x', 'x'], ['x', 'x', 'x'], ['x', 'x', 'x']]
        self.lmd.append(LineMatchingData(pattern, HORIZONTAL, '-'))
        self.matrix_nr = len(self.lmd) - 1
        self.update_line_matching_data()

    def on_delete_matrix(self):
        if len(self.lmd) <= 1:
            QMessageBox.information(self, _("Magic-line settings"), _("At least one matrix is required."))
            return
        del self.lmd[self.matrix_nr]
        self.matrix_nr = min(self.matrix_nr, len(self.lmd) - 1)
        self.update_line_matching_data()

    def on_save_clicked(self):
        MagicLineSettings.LMD = copy.deepcopy(self.lmd)
        pub.sendMessage('SAVE_MAGIC_LINE_SETTINGS')
        self.accept()

    def on_restore_defaults_clicked(self):
        pub.sendMessage('RESTORE_DEFAULT_MAGIC_LINE_SETTINGS')
        self.lmd = copy.deepcopy(MagicLineSettings.LMD)
        self.matrix_nr = 0
        self.update_line_matching_data()
