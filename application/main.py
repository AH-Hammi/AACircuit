"""AACircuit application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from application.controller import Controller


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    controller = Controller()
    controller.show_all()
    return app.exec()
