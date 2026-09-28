"""Qt file and print dialogs."""

from gettext import gettext as _

from pubsub import pub
from PySide6.QtWidgets import QApplication, QFileDialog


def _parent():
    return QApplication.activeWindow()


class InputFileChooser:
    title = _("Please choose a file")
    filters = _("Circuit files (*.aac);;Text files (*.txt);;All files (*)")

    def __init__(self):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            _parent(), self.title, '', self.filters,
        )
        if filename:
            self.filename = filename
            self.action()

    def action(self):
        pub.sendMessage('READ_FROM_FILE', filename=self.filename)


class OutputFileChooser:
    title = _("Save as")
    filters = _("Circuit files (*.aac);;Text files (*.txt);;All files (*)")

    def __init__(self, filename=_("Untitled_schema.aac")):
        self.filename = filename
        filename, _selected_filter = QFileDialog.getSaveFileName(
            _parent(), self.title, self.filename, self.filters,
        )
        if filename:
            self.filename = filename
            self.action()

    def action(self):
        pub.sendMessage('WRITE_TO_FILE', filename=self.filename)


class OutputFileAscii(OutputFileChooser):
    title = _("Export as ASCII")
    filters = _("Text files (*.txt);;All files (*)")

    def action(self):
        pub.sendMessage('WRITE_TO_ASCII_FILE', filename=self.filename)


class InputFileAscii(InputFileChooser):
    title = _("Load ASCII file")
    filters = _("Text files (*.txt);;All files (*)")

    def action(self):
        pub.sendMessage('LOAD_ASCII_FROM_FILE', filename=self.filename)
