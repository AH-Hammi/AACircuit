"""Qt component list used by the main window."""

from pubsub import pub
from PySide6.QtWidgets import QListWidget

from application import gettext as _


class ComponentView(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(190)
        self.itemSelectionChanged.connect(self.on_changed)
        pub.subscribe(self.set_components, 'ALL_COMPONENTS')

    def set_components(self, list):
        self.clear()
        self.addItems(list)

    def on_changed(self):
        items = self.selectedItems()
        label = items[0].text() if items else _("Resistor")
        pub.sendMessage('COMPONENT_CHANGED', label=label)
