
    _        _    ____ _                _ _     ____        
   / \      / \  / ___(_)_ __ ___ _   _(_) |_  |  _ \ _   _ 
  / _ \    / _ \| |   | | '__/ __| | | | | __| | |_) | | | |
 / ___ \  / ___ \ |___| | | | (__| |_| | | |_  |  __/| |_| |
/_/   \_\/_/   \_\____|_|_|  \___|\__,_|_|\__| |_|    \__, |
                                                      |___/ 
                                            

Draw electronic circuits with ASCII characters.
                                                                        
                                                                        
         .---------------------o--------------o---o +1.5V               
         |                     |              |                         
         |                     |              |                         
        .-.         ||100n     |             .-.                        
        | |    .----||----.    |             | |                        
       100k    |    ||    |    |             | |1k                      
        '-'    |    ___   |  |<              '-'                        
         |     o---|___|--o--|                |                         
         |     |    1k       |\               |                         
         |   |/                |              |                         
         o---|                 |              |                         
    L    |   |>                |              |                         
    E    |     |               |              |                         
    D    |     |    \]         |     \]       |                         
         '-----)----|]---------o-----|]-------o                         
    B          |    /]+        |     /]+      |                         
    l          |    10µ       .-.    100µ     |                         
    i          |              | |             |                         
    n          |              | |47Ω          V ->                      
    k          |              '-'             -                         
    e          |               |              |                         
    r          '---------------o--------------o---o GND                 
                                                                        

This is a pythonized version of (Borland Delphi) AACircuit (by Andreas Weber).
A kind of reverse engineered version, where the idea and GUI layout are taken from the original.

For the ASCII representation, use copy or "Save ASCII". Use a monospaced font in your document, news- or mailclient!

English component definitions and default grids live in `application/components/component_en.json`.
Component names are their canonical keys; no numeric IDs are required.

Per-language files `component_de.json`, `component_da.json`, and `component_nl.json` in
`application/components/translations/` can define a translated `name` and/or a complete alternate `grid`
for a component. Entries are keyed by the canonical English name. Components without an alternate grid use
the English grid.

Grid dictionaries list only supported compass orientations (`N`, `E`, `S`, `W`). Rotation cycles through
the orientations present in that component's grid, so opposite directions with identical artwork can be
omitted. A localized `grid` replaces the base grid and likewise lists only supported orientations.

Optional user components are read from `application/components/user_component_1.json` through
`user_component_5.json`. Define them with English canonical names and a grid containing the supported
orientations. Add an entry in a language file to translate the name or provide an alternate grid.


Usage
=====
Install uv, go to the AACircuit directory, and run:

    uv run aacircuit.py


Dependencies
============
Python 3.10 or newer
PySide6 (Qt 6)
platformdirs
pypubsub
bresenham
pycairo


Windows
============
PySide6 and pycairo provide Windows wheels, so no separate GTK/MSYS2 installation is needed.
Install uv, then run `uv run aacircuit.py` from the project directory.

Original: https://github.com/Andy1978/AACircuit
