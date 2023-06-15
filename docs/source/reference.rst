Reference for .scy file format
==============================

Configuration of `scy` execution is done primarily with a `.scy` file.  This file is used to declare
all the files and code needed to perform the coverage tests and describe the hierarchy of smaller
cover properties.  See also `.sby` file format.

Sequence section
----------------

Sequence of covers formatted as a tree.

Keywords:

- cover
- trace
- append
- add
- enable
- disable

Design section
--------------

Yosys script to prepare the design for coverage testing.  See also `sby` script section.

Options section
---------------

`replay_vcd on|off`

Any option `scy` doesn't recognise is passed to `sby`.

SBY sections
------------

Engines, files, etc sections.  Any section `scy` doesn't recognise is passed to `sby`.  Tasks
section might do weird things.
