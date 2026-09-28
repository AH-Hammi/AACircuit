import unittest

from application.component_library import ComponentLibrary


class ComponentLibraryTest(unittest.TestCase):
    def test_canonical_english_name_is_component_identity(self):
        library = ComponentLibrary(language='en')
        symbol = library.get_symbol('Resistor')

        self.assertEqual(symbol.identity, 'Resistor')
        self.assertNotIn('id', library.components['Resistor'])

    def test_translations_and_symbol_variants_share_language_file(self):
        english = ComponentLibrary(language='en')
        german = ComponentLibrary(language='de')

        self.assertIn('R-Widerstand', german.components)
        self.assertEqual(german.get_symbol('R-Widerstand').identity, 'Resistor')
        self.assertEqual(german.get_symbol('Resistor').identity, 'Resistor')
        self.assertEqual(
            german.get_symbol('OR gate').grid,
            german.components['Logik-OR']['grid']['N'],
        )
        self.assertNotEqual(
            german.get_symbol('OR gate').grid,
            english.get_symbol('OR gate').grid,
        )

        danish = ComponentLibrary(language='da')
        danish_transformer = danish.get_symbol('Transformer')
        english_transformer = english.get_symbol('Transformer')
        danish_transformer.ori = 1
        english_transformer.ori = 1
        self.assertNotEqual(
            danish_transformer.grid,
            english_transformer.grid,
        )

        dutch = ComponentLibrary(language='nl')
        dutch_voltage = dutch.get_symbol('Voltage')
        english_voltage = english.get_symbol('Voltage')
        dutch_voltage.ori = 2
        english_voltage.ori = 2
        self.assertNotEqual(dutch_voltage.grid, english_voltage.grid)

        for language, label in (
            ('de', 'R-Widerstand'),
            ('da', 'Modstand'),
            ('nl', 'Weerstand'),
        ):
            with self.subTest(language=language):
                self.assertIn(label, ComponentLibrary(language=language).components)

    def test_opposite_equal_orientations_need_only_one_grid(self):
        library = ComponentLibrary(language='en')
        for name in ('Resistor', 'Capacitor'):
            with self.subTest(component=name):
                symbol = library.get_symbol(name)
                self.assertEqual(set(library.get_grid(name)), {'N', 'E'})
                vertical = symbol.grid
                symbol.rotate()
                horizontal = symbol.grid
                self.assertNotEqual(vertical, horizontal)
                symbol.rotate()
                self.assertEqual(symbol.grid, vertical)

    def test_rotation_skips_undefined_orientations(self):
        library = ComponentLibrary(language='da')
        source = library.get_symbol('Signal Source')

        self.assertEqual(set(library.get_grid('Signal Source')), {'N'})
        north = source.grid
        self.assertEqual(source.rotate(), north)

    def test_directional_symbol_retains_distinct_orientations(self):
        library = ComponentLibrary(language='en')
        transistor = library.get_symbol('NPN BJT')
        orientations = []
        for _ in range(4):
            orientations.append(tuple(transistor.grid))
            transistor.rotate()

        self.assertEqual(len(set(orientations)), 4)
