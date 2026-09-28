import unittest

from application.component_library import ComponentLibrary


class ComponentLibraryTest(unittest.TestCase):
    def test_canonical_english_name_is_component_identity(self):
        library = ComponentLibrary(language='en')
        symbol = library.get_symbol('Resistor')

        self.assertEqual(symbol.identity, 'Resistor')
        self.assertNotIn('id', library.components['Resistor'])

    def test_iec_is_default_and_ansi_ieee_is_an_override(self):
        iec = ComponentLibrary(language='en')
        ansi_ieee = ComponentLibrary(language='en', symbol_set='ansi_ieee')

        self.assertEqual(iec.symbol_set, 'iec')
        self.assertNotEqual(iec.get_grid('OR gate'), ansi_ieee.get_grid('OR gate'))
        self.assertNotEqual(iec.get_grid('AND gate'), ansi_ieee.get_grid('AND gate'))
        self.assertEqual(iec.get_grid('Diode'), ansi_ieee.get_grid('Diode'))

    def test_symbol_set_does_not_change_translated_names(self):
        iec = ComponentLibrary(language='de', symbol_set='iec')
        ansi_ieee = ComponentLibrary(language='de', symbol_set='ansi_ieee')

        self.assertIn('Logik-OR', iec.components)
        self.assertIn('Logik-OR', ansi_ieee.components)
        self.assertEqual(
            iec.get_symbol('Logik-OR').identity,
            ansi_ieee.get_symbol('Logik-OR').identity,
        )
        self.assertNotEqual(
            iec.get_symbol('Logik-OR').grid,
            ansi_ieee.get_symbol('Logik-OR').grid,
        )

    def test_iec_grids_are_independent_of_display_language(self):
        english = ComponentLibrary(language='en', symbol_set='iec')
        for language in ('de', 'da', 'nl'):
            localized = ComponentLibrary(language=language, symbol_set='iec')
            for name in english.components:
                with self.subTest(language=language, component=name):
                    self.assertEqual(english.get_grid(name), localized.get_grid(name))

    def test_locale_translations_are_loaded(self):
        expected_labels = {
            'de': 'Widerstand',
            'da': 'Modstand',
            'nl': 'Weerstand',
        }
        for language, label in expected_labels.items():
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

    def test_directional_symbol_retains_distinct_orientations(self):
        library = ComponentLibrary(language='en')
        transistor = library.get_symbol('NPN BJT')
        orientations = []
        for _ in range(4):
            orientations.append(tuple(transistor.grid))
            transistor.rotate()

        self.assertEqual(len(set(orientations)), 4)

    def test_all_components_expose_terminals_and_box_art(self):
        library = ComponentLibrary(language='en')
        for name in library.components:
            with self.subTest(component=name):
                symbol = library.get_symbol(name)
                self.assertTrue(symbol.terminal_positions())

        resistor = library.get_grid('Resistor')['N']
        self.assertTrue(any(char in '┌┐└┘' for row in resistor for char in row))
        self.assertEqual(len(library.get_symbol('DIL 8-pin IC').terminal_positions()), 8)

    def test_ports_follow_gate_leads_and_dil_pin_glyphs(self):
        library = ComponentLibrary(language='en')
        gate = library.get_symbol('OR gate')
        self.assertEqual(
            [(port['direction'], port['position'].xy) for port in gate.terminal_positions()],
            [('W', (0, 1)), ('W', (0, 3)), ('E', (5, 2))],
        )

        dil = library.get_symbol('DIL 8-pin IC')
        dil.ori = 1
        points = {port['position'].xy for port in dil.terminal_positions()}
        self.assertEqual(
            points,
            {(x, y) for x in (1, 3, 5, 7) for y in (1, 4)},
        )
