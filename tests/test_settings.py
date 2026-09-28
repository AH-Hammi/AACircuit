import unittest

from PySide6.QtWidgets import QComboBox

from application.main_window import ensure_qapplication
from application.preferences import Preferences, PreferencesDialog


class PreferencesTest(unittest.TestCase):

    def test_get(self):
        self.assertEqual(Preferences.values['FONTSIZE'], 12)

    def test_set(self):
        Preferences.values['FONTSIZE'] = 14
        self.assertEqual(Preferences.values['FONTSIZE'], 14)

    def test_nr_settings(self):
        p = Preferences()
        self.assertEqual(p.nr_values(), 19)

    def test_has_value(self):
        p = Preferences()
        self.assertTrue(p.has_value('FONTSIZE'))
        self.assertFalse(p.has_value('ONBEKEND'))

    def test_preferences_file(self):
        p = Preferences(filename='tests/files/test_aacircuit.ini')

        # test integer
        self.assertEqual(p.values['FONTSIZE'], 12)

        # test boolean
        self.assertEqual(p.values['SELECTION_DRAG'], False)

        # test string
        self.assertEqual(p.values['LINE_HOR'], '-')
        self.assertEqual(p.values['SYMBOL_SET'], 'iec')

    def test_symbol_standard_selector(self):
        ensure_qapplication()
        previous = Preferences.values['SYMBOL_SET']
        try:
            Preferences.values['SYMBOL_SET'] = 'iec'
            dialog = PreferencesDialog()
            selector = dialog.findChild(QComboBox, 'symbol_set')
            self.assertIsNotNone(selector)
            self.assertEqual(selector.currentData(), 'iec')
            selector.setCurrentIndex(selector.findData('ansi_ieee'))
            self.assertEqual(selector.currentData(), 'ansi_ieee')
            dialog.close()
        finally:
            Preferences.values['SYMBOL_SET'] = previous
