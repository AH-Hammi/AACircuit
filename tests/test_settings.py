import unittest

from application.preferences import Preferences


class PreferencesTest(unittest.TestCase):

    def test_get(self):
        self.assertEqual(Preferences.values['FONTSIZE'], 12)

    def test_set(self):
        Preferences.values['FONTSIZE'] = 14
        self.assertEqual(Preferences.values['FONTSIZE'], 14)

    def test_nr_settings(self):
        # 2020-05-28 number of settings in the preferences testfile: 18
        p = Preferences()
        self.assertEqual(p.nr_values(), 18)

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
