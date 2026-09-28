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

    def __init__(self, language=None):
        language = language or locale.getlocale()[0] or 'en'
        self.language = language[:2].lower()

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

        self._components = OrderedDict()
        self._canonical_by_name = {}
        for canonical_name, base_definition in self._canonical_components.items():
            localized = translations.get(canonical_name, {})
            definition = copy.deepcopy(base_definition)
            # A locale grid is a complete replacement for this component; its keys
            # are exactly the directions supported in that locale.
            if 'grid' in localized:
                definition['grid'] = copy.deepcopy(localized['grid'])
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
            if not isinstance(variant, dict) or set(variant) - {'name', 'grid'}:
                raise ValueError("Translation for {!r} may contain only name and grid".format(name))
            display_name = variant.get('name', name)
            if not isinstance(display_name, str) or not display_name:
                raise ValueError("Translation for {!r} must be a non-empty string".format(name))
            if 'grid' in variant:
                cls._validate_grid(name, variant['grid'])

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
        return Symbol(component_key=canonical_name, grid=definition['grid'])

    def nr_components(self):
        return len(self._canonical_components)

    def nr_libraries(self):
        return len(self._libraries)


if __name__ == '__main__':
    library = ComponentLibrary()
    print(_("Number of libraries loaded: {0}").format(library.nr_libraries()))
