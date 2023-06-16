.. role:: scy(code)
	:language: scy

Reference for .scy file format
==============================

Configuration of ``scy`` execution is done primarily with a ``.scy`` file.  This file is used to declare
all the files and code needed to perform the coverage tests and describe the hierarchy of smaller
cover properties.  See also ``.sby`` file format.

Sequence section
----------------

The ``[sequence]`` section comprises a sequence of covers (and other keywords) formatted as a tree.

Supported keywords:

- :ref:`cover`
- :ref:`trace`
- :ref:`append`
- :ref:`enable<enable and disable>`
- :ref:`disable<enable and disable>`
- :ref:`add`

An example is shown below:

.. code:: scy

    cover cp_reset:
        disable ap_noreset
        cover cp_hpmevent2:
            cover cp_hpmcounter:
                    trace hpm_event2
        cover cp_hpmcounter:
            trace hpm_any

This example shows two sequences which need to be checked.  Both sequences begin with the
``cp_reset`` cover cell being checked with ``ap_noreset`` disabled.  After this, the sequences
diverge.  The first runs until `cp_hpmevent2` is reached and then covers ``cp_hpmcounter``, while
the second checks ``cp_hpmcounter`` immediately. The trace ``hpm_event2`` thus shows the sequence
``cp_reset > cp_hpmevent2 > cp_hpmcounter`` while ``hpm_any`` shows ``cp_reset > cp_hpmcounter``.

For a more complete example of how the ``[sequence]`` section is used, refer to the :ref:`hpm
example<example sequence>`.

cover
~~~~~

:scy:`usage: cover <cell_name>`

Provided the name of a cover cell, this statement will generate a SBY file to run a cover check for
the named cell and ignoring all other cover cells. Note that if the desired cover statement resides
inside of a submodule, the fully qualified name must be used; i.e. :scy:`cover
checker_inst.cp_reset_done` looks for a cover cell named ``cp_reset_done`` inside the
``checker_inst`` module.  A named cover cell must be declared in SVA as follows:

.. code:: verilog

    cp_reset_done: cover(!reset && reset_q);

trace
~~~~~

:scy:`usage: trace <trace_name>`

The :scy:`trace` keyword can be used to generate a single ``.vcd`` trace of all cover statements up
to that point.  Note that each cover statement will produce its own trace starting from when the
previous cover statement is reached.  The name provided is used when generating the output file
``<trace_name>.vcd``.

append
~~~~~~

:scy:`usage: append <num_cycles>`

A number of cycles can be appended after the previous cover statement is reached.  By using
:scy:`append` an integer number of extra cycles can be added between one cover statement and the
next.  A negative value can also be provided, which will cause subsequent children statements to
begin prior to the previous statement being reached.

enable and disable
~~~~~~~~~~~~~~~~~~

:scy:`usage: enable <cell_name>` or :scy:`disable <cell_name>`

The :scy:`enable` and :scy:`disable` keywords can be used to enable and disable a cell.  This will
affect all children of the statement until the other keyword is given.  If one of these keywords is
in the body of a statement, i.e. if the enable/disable does not have a body of its own, then it will
affect only that one statement and not the subsequent children.

If a cell is enabled but never disabled then it will be disabled initially until an ``enable`` is
reached.  Otherwise, the cell will be enabled until a ``disable`` is reached.  This keyword is
intended to be used for dynamically enabling/disabling assume cells but can be used with any named
cell provided it has a 1-bit input ``EN`` which is disabled on a value of ``1'b0``.

add
~~~

:scy:`usage: add <cell_type> <wire_name>`

This will add a new cell of the provided type connected to the named wire.  While any of the cell
types available with ``yosys add`` are possible, this is primarily for dynamically adding
``$assume`` cells.  The added cell will be enabled at the point in the sequence which declares it
and for all subsequent statements.

Design section
--------------

The ``[design]`` sectioin contains the Yosys script to prepare the design for coverage testing.  See
also SBY script section.

Options section
---------------

The ``[options]`` section contains lines with key-value pairs.

+------------------+-----------------+-------------------------------------------------------------+
| Option           | Default         | Description                                                 |
+==================+=================+=============================================================+
| ``replay_vcd``   | ``off``         | Use ``.vcd`` files instead of ``.yw`` files.                |
|                  |                 | Values: ``on``, ``off``.                                    |
+------------------+-----------------+-------------------------------------------------------------+
| ``design_scope`` | None            | The top module of the design.  Only used when ``replay_vcd``|
|                  |                 | set to ``on``.  If not provided, ``design.json`` output     |
|                  |                 | from ``sby`` parse will be used to attempt auto detection.  |
+------------------+-----------------+-------------------------------------------------------------+

Any option SCY doesn't recognise is passed to SBY.

SBY sections
------------

Engines, files, etc sections.  Any section SCY doesn't recognise is passed to SBY.  Tasks
section might do weird things.
