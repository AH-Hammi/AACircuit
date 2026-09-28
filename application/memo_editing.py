"""Editor for AACircuit's textual drawing commands."""

from pubsub import pub
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from application import gettext as _


class MemoEditingDialog(QDialog):
    def __init__(self, memo, parent=None):
        super().__init__(parent or QApplication.activeWindow())
        self.setWindowTitle(_("Edit draw commands"))
        self.resize(600, 400)
        self._memo_editable = False

        layout = QVBoxLayout(self)
        self.search_entry = QLineEdit(self)
        self.search_entry.setPlaceholderText(_("Search"))
        self.search_entry.textChanged.connect(self.search_and_mark)
        layout.addWidget(self.search_entry)

        self.memo_tv = QPlainTextEdit(self)
        self.memo_tv.setPlainText(memo)
        self.memo_tv.setReadOnly(True)
        self.memo_tv.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.memo_tv.setStyleSheet("font-family: monospace;")
        self.memo_tv.moveCursor(QTextCursor.MoveOperation.End)
        layout.addWidget(self.memo_tv)

        controls = QHBoxLayout()
        self.edit_memo = QCheckBox(_("Edit draw commands"), self)
        self.edit_memo.toggled.connect(self.on_edit_memo)
        controls.addWidget(self.edit_memo)
        controls.addStretch(1)

        draw = QPushButton(_("Draw"), self)
        draw.clicked.connect(self.on_draw_clicked)
        controls.addWidget(draw)
        close = QPushButton(_("Close"), self)
        close.clicked.connect(self.accept)
        controls.addWidget(close)
        layout.addLayout(controls)

        self.search_and_mark('')

    def run(self):
        return self.exec()

    def on_edit_memo(self, enabled):
        self._memo_editable = enabled
        self.memo_tv.setReadOnly(not enabled)
        palette = self.memo_tv.palette()
        palette.setColor(
            palette.ColorRole.Text,
            QColor('#000000' if enabled else '#7f7f7f'),
        )
        self.memo_tv.setPalette(palette)

    def on_draw_clicked(self):
        pub.sendMessage('RERUN_MEMO', str=self.memo_tv.toPlainText())

    def search_and_mark(self, text):
        extra_selections = []
        if text:
            document = self.memo_tv.document()
            start = 0
            first = None
            highlight = QTextCharFormat()
            highlight.setBackground(QColor('yellow'))
            while True:
                found = document.find(text, start, QTextDocument.FindFlag.FindCaseSensitively)
                if found.isNull():
                    break
                if first is None:
                    first = found
                selection = QTextEdit.ExtraSelection()
                selection.cursor = found
                selection.format = highlight
                extra_selections.append(selection)
                start = found.selectionEnd()
            if first is not None:
                self.memo_tv.setTextCursor(first)
        self.memo_tv.setExtraSelections(extra_selections)

    def on_next_match(self, _item=None):
        self._find_next(1)

    def on_previous_match(self, _item=None):
        self._find_next(-1)

    def _find_next(self, direction):
        query = self.search_entry.text()
        if not query:
            return
        flags = QTextDocument.FindFlag.FindBackward if direction < 0 else QTextDocument.FindFlag(0)
        if not self.memo_tv.find(query, flags):
            cursor = self.memo_tv.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if direction < 0 else QTextCursor.MoveOperation.Start
            )
            self.memo_tv.setTextCursor(cursor)
            self.memo_tv.find(query, flags)

    def on_stop_search(self, _item=None):
        self.search_entry.clear()
