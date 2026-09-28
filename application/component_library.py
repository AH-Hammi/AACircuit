"""Canonical English component definitions and locale-specific display variants."""

import copy
import json
import locale
from collections import OrderedDict
from pathlib import Path

from pubsub import pub

from application import ERROR, get_path_to_data
from application import gettext as _
from application.symbol import Symbol


class ComponentLibrary:
    ORIENTATION = ('N', 'E', 'S', 'W')

    def __init__(self, language=None, symbol_set='iec'):
        language = language or locale.getlocale()[0] or 'en'
        self.language = language[:2].lower()
        self.symbol_set = (symbol_set or 'iec').lower().replace('-', '_').replace('/', '_')
        if self.symbol_set not in ('iec', 'ansi_ieee'):
            raise ValueError("Unknown symbol set {!r}".format(symbol_set))

        self._libraries = ['component_en.json']
        components = self._read_json('component_en.json', required=True)

        # Optional component libraries use canonical English names as keys.
        for number in range(1, 6):
            filename = 'user_component_{}.json'.format(number)
            if Path(get_path_to_data('components/' + filename)).is_file():
                components.update(self._read_json(filename, required=True))
                self._libraries.append(filename)

        self._validate_definitions(components)
        self._canonical_components = OrderedDict(components)

        translation_file = 'translations/component_{}.json'.format(self.language)
        translation_path = Path(get_path_to_data('components/' + translation_file))
        translations = {}
        if self.language != 'en' and translation_path.is_file():
            translations = self._read_json(translation_file, required=True)
        self._validate_translations(translations, self._canonical_components)

        symbol_overrides = {}
        if self.symbol_set == 'ansi_ieee':
            symbol_overrides = self._read_json(
                'translations/symbol_set_ansi_ieee.json', required=True,
            )
            self._validate_symbol_overrides(symbol_overrides, self._canonical_components)

        self._components = OrderedDict()
        self._canonical_by_name = {}
        for canonical_name, base_definition in self._canonical_components.items():
            localized = translations.get(canonical_name, {})
            definition = copy.deepcopy(base_definition)
            if canonical_name in symbol_overrides:
                definition['grid'] = copy.deepcopy(symbol_overrides[canonical_name]['grid'])
            definition['grid'] = self._unicode_grid(definition['grid'])
            definition['terminals'] = self._terminal_layout(canonical_name, definition['grid'])
            display_name = localized.get('name', canonical_name)
            existing_name = self._canonical_by_name.get(display_name)
            if existing_name is not None and existing_name != canonical_name:
                raise ValueError(
                    "Duplicate component display name {!r} for {!r} and {!r}".format(
                        display_name, existing_name, canonical_name,
                    )
                )
            self._components[display_name] = definition
            self._canonical_by_name[display_name] = canonical_name
            self._canonical_by_name.setdefault(canonical_name, canonical_name)

        self._key = None
        self._dir = None

    @staticmethod
    def _read_json(filename, required=False):
        path = get_path_to_data('components/' + filename)
        try:
            with open(path, 'r', encoding='utf-8') as source:
                data = json.load(source)
        except (OSError, ValueError) as error:
            if not required:
                return {}
            message = _("Failed to load component library {0}: {1}").format(filename, error)
            pub.sendMessage('STATUS_MESSAGE', msg=message, type=ERROR)
            raise
        if not isinstance(data, dict):
            raise ValueError("Component file {!r} must contain a JSON object".format(filename))
        return data

    @classmethod
    def _validate_grid(cls, name, grid):
        if not isinstance(grid, dict) or not grid:
            raise ValueError("Component {!r} must define at least one orientation".format(name))
        unsupported = set(grid) - set(cls.ORIENTATION)
        if unsupported:
            raise ValueError(
                "Component {!r} has unknown orientations: {}".format(
                    name, ', '.join(sorted(unsupported)),
                )
            )
        for orientation, rows in grid.items():
            if not isinstance(rows, list) or not rows or any(not isinstance(row, str) for row in rows):
                raise ValueError(
                    "Component {!r} orientation {} must contain text rows".format(name, orientation)
                )
            if not any(row.strip() for row in rows):
                raise ValueError(
                    "Component {!r} orientation {} is blank; omit unsupported orientations".format(
                        name, orientation,
                    )
                )

    @classmethod
    def _validate_definitions(cls, components):
        for name, definition in components.items():
            if not isinstance(definition, dict) or 'grid' not in definition:
                raise ValueError("Component {!r} must define a grid".format(name))
            cls._validate_grid(name, definition['grid'])

    @classmethod
    def _validate_translations(cls, translations, components):
        unknown = set(translations) - set(components)
        if unknown:
            raise ValueError(
                "Translations refer to unknown components: {}".format(', '.join(sorted(unknown)))
            )
        for name, variant in translations.items():
            if not isinstance(variant, dict) or set(variant) - {'name'}:
                raise ValueError("Translation for {!r} may contain only a display name".format(name))
            display_name = variant.get('name', name)
            if not isinstance(display_name, str) or not display_name:
                raise ValueError("Translation for {!r} must be a non-empty string".format(name))

    @classmethod
    def _validate_symbol_overrides(cls, overrides, components):
        unknown = set(overrides) - set(components)
        if unknown:
            raise ValueError(
                "Symbol overrides refer to unknown components: {}".format(', '.join(sorted(unknown)))
            )
        for name, override in overrides.items():
            if not isinstance(override, dict) or set(override) != {'grid'}:
                raise ValueError("Symbol override for {!r} must define a complete grid".format(name))
            cls._validate_grid(name, override['grid'])

    @staticmethod
    def _unicode_grid(grid):
        """Use single-cell Unicode box glyphs for ordinary symbol strokes."""
        horizontal = {'-', '_', '─', '═'}
        vertical = {'|', '│', '║'}
        result = {}
        for orientation, rows in grid.items():
            width = max(map(len, rows))
            matrix = [list(row.ljust(width)) for row in rows]
            converted = [row[:] for row in matrix]
            for y, row in enumerate(matrix):
                for x, char in enumerate(row):
                    left = x > 0 and row[x - 1] in horizontal
                    right = x + 1 < width and row[x + 1] in horizontal
                    up = y > 0 and matrix[y - 1][x] in vertical
                    down = y + 1 < len(matrix) and matrix[y + 1][x] in vertical
                    if char in horizontal:
                        converted[y][x] = '─'
                    elif char in vertical:
                        converted[y][x] = '│'
                    elif char in ('.', ',', "'"):
                        if right and down:
                            converted[y][x] = '┌'
                        elif left and down:
                            converted[y][x] = '┐'
                        elif right and up:
                            converted[y][x] = '└'
                        elif left and up:
                            converted[y][x] = '┘'
                    elif char == 'o':
                        converted[y][x] = 'O'
            result[orientation] = [''.join(row) for row in converted]
        return result

    @staticmethod
    def _terminal_layout(name, grid):
        """Find pin glyphs on the actual symbol edge and expose them as pull nodes."""
        multi_pin = name == 'DIL 8-pin IC'
        gate = 'gate' in name.lower() or name == 'Opamp'
        transistor = any(token in name for token in ('BJT', 'JFET', 'MOSFET', 'Triac', 'SCR', 'Unijunction'))
        if name == 'Ground/Vcc':
            count = 1
        elif name in ('Crossed diagonals', 'Bridge rectifier'):
            count = 4
        elif multi_pin:
            count = 8
        elif name == 'Opamp':
            count = 5
        elif name == 'FlipFlop':
            count = 6
        elif name == 'D-FF,JK-FF':
            count = 8
        elif name == 'Inverter gate':
            count = 2
        elif gate or transistor or name in ('Potentiometer', 'SPDT switch', 'Voltage regulator 7-series'):
            count = 3
        else:
            count = 2

        layouts = {}
        for orientation, rows in grid.items():
            points = [
                (x, y) for y, row in enumerate(rows)
                for x, char in enumerate(row) if char != ' '
            ]
            min_x = min(x for x, _ in points)
            max_x = max(x for x, _ in points)
            min_y = min(y for _, y in points)
            max_y = max(y for _, y in points)
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            horizontal_strokes = {'─', '-', '_', '=', 'O', '+'}
            vertical_strokes = {'│', '|', 'O', '+'}

            sides = {
                'W': [(min_x, y) for y, row in enumerate(rows) if row[min_x] in horizontal_strokes],
                'E': [(max_x, y) for y, row in enumerate(rows) if row[max_x] in horizontal_strokes],
                'N': [(x, min_y) for x, char in enumerate(rows[min_y]) if char in vertical_strokes],
                'S': [(x, max_y) for x, char in enumerate(rows[max_y]) if char in vertical_strokes],
            }

            def closest_to_center(candidates, axis):
                if not candidates:
                    if axis == 'y':
                        return [(center_x, center_y)]
                    return [(center_x, center_y)]
                return sorted(candidates, key=lambda point: abs(point[1 if axis == 'y' else 0] -
                                                                (center_y if axis == 'y' else center_x)))

            def side_ports(side, number=1):
                fallback = {
                    'W': (min_x, center_y), 'E': (max_x, center_y),
                    'N': (center_x, min_y), 'S': (center_x, max_y),
                }[side]
                candidates = sides[side]
                if not candidates:
                    return [(side, *fallback)]
                candidates = sorted(candidates, key=lambda point: point[1] if side in ('W', 'E') else point[0])
                if number == 1:
                    candidates = closest_to_center(candidates, 'y' if side in ('W', 'E') else 'x')
                    candidates = candidates[:1]
                elif len(candidates) >= number:
                    indexes = [round(index * (len(candidates) - 1) / (number - 1)) for index in range(number)]
                    candidates = [candidates[index] for index in indexes]
                else:
                    candidates = candidates + [fallback] * (number - len(candidates))
                return [(side, x, y) for x, y in candidates]

            explicit = [
                (x, y) for y, row in enumerate(rows)
                for x, char in enumerate(row) if char == 'O'
            ]

            def explicit_port(point):
                x, y = point
                distances = {
                    'W': abs(x - min_x), 'E': abs(max_x - x),
                    'N': abs(y - min_y), 'S': abs(max_y - y),
                }
                if multi_pin and orientation in ('N', 'S'):
                    side = 'W' if x <= center_x else 'E'
                elif multi_pin:
                    side = 'N' if y <= center_y else 'S'
                else:
                    side = min(distances, key=distances.get)
                return (side, x, y)

            def spaced(low, high, number):
                if number == 1:
                    return [(low + high) // 2]
                return [round(low + (high - low) * index / (number - 1))
                        for index in range(number)]

            ports = []
            if multi_pin:
                ports.extend(explicit_port(point) for point in explicit)
            elif count == 1:
                ports.extend(explicit_port(point) for point in explicit[:1])
                if not ports:
                    side = {'N': 'N', 'E': 'S', 'S': 'S', 'W': 'N'}[orientation]
                    ports.extend(side_ports(side))
            elif count == 4:
                if len(explicit) >= count:
                    ports.extend(explicit_port(point) for point in explicit[:count])
                else:
                    ports.extend(side_ports(side) for side in ('W', 'E', 'N', 'S'))
                    ports = [port for group in ports for port in group]
            elif gate and name != 'Inverter gate':
                if orientation in ('N', 'S'):
                    input_side, output_side = ('W', 'E') if orientation == 'N' else ('E', 'W')
                else:
                    input_side, output_side = ('N', 'S') if orientation == 'E' else ('S', 'N')
                ports.extend(side_ports(input_side, 2))
                output = next((point for point in explicit if explicit_port(point)[0] == output_side), None)
                ports.extend([explicit_port(output)] if output else side_ports(output_side))
                if name == 'Opamp':
                    supply_sides = ('N', 'S') if orientation in ('N', 'S') else ('W', 'E')
                    for side in supply_sides:
                        ports.extend(side_ports(side))
            elif count >= 3 and len(explicit) >= count:
                ports.extend(explicit_port(point) for point in explicit[:count])
            elif count == 2:
                pairs = [('W', 'E'), ('N', 'S')]
                horizontal = (max_x - min_x) >= (max_y - min_y)
                pairs.sort(key=lambda pair: (pair[0] == 'W') == horizontal, reverse=True)
                pair = max(pairs, key=lambda sides_pair:
                           len(sides[sides_pair[0]]) + len(sides[sides_pair[1]]))
                ports.extend(side_ports(side) for side in pair)
                ports = [port for group in ports for port in group]
            else:
                if count >= 6:
                    side_counts = (('W', 2), ('E', 2), ('N', 1), ('S', 1))
                    if count == 8:
                        side_counts = tuple((side, 2) for side in ('W', 'E', 'N', 'S'))
                    for side, number in side_counts:
                        ports.extend(side_ports(side, number))
                elif transistor or name in ('Potentiometer', 'SPDT switch', 'Voltage regulator 7-series'):
                    ports.extend(side_ports(side) for side in ('W', 'E', 'N'))
                    ports = [port for group in ports for port in group]
                else:
                    ports.extend(side_ports(side) for side in ('W', 'E'))
                    ports = [port for group in ports for port in group]

            layouts[orientation] = [
                {'name': 'P{}'.format(index + 1), 'direction': side, 'x': x, 'y': y}
                for index, (side, x, y) in enumerate(ports)
            ]
        return layouts

    @property
    def components(self):
        """Components indexed by the name shown in the current language."""
        return self._components

    def _canonical_name(self, key):
        return self._canonical_by_name.get(key, key)

    def get_grid(self, key):
        """Return the effective grid for an English or localized component name."""
        if len(key) == 1:
            self._key = key
            return [[key]]
        canonical_name = self._canonical_name(key)
        self._key = canonical_name
        return self._components[self._display_name(canonical_name)]['grid']

    def _display_name(self, canonical_name):
        for display_name, name in self._canonical_by_name.items():
            if name == canonical_name:
                return display_name
        return canonical_name

    def get_symbol(self, key):
        """Construct a symbol whose identity is its canonical English name."""
        if len(key) == 1:
            return Symbol(identity=ord(key), grid={'N': [key]})
        canonical_name = self._canonical_name(key)
        display_name = self._display_name(canonical_name)
        definition = self._components[display_name]
        self._key = canonical_name
        return Symbol(
            component_key=canonical_name,
            grid=definition['grid'],
            terminals=definition['terminals'],
        )

    def nr_components(self):
        return len(self._canonical_components)

    def nr_libraries(self):
        return len(self._libraries)


if __name__ == '__main__':
    library = ComponentLibrary()
    print(_("Number of libraries loaded: {0}").format(library.nr_libraries()))
