Example usage in hpm-test
=========================

Code is available in ``scy/example/hpm-test``, using the NERV core and cover check from the `RISCV-V
formal verification framework<https://github.com/YosysHQ/riscv-formal/>`.

Additional code provided in ``cover_stmts.vh`` is based on the ``rvfi_csrc_hpm_check.sv`` code.
This code provides the SVA cover statements and assumptions needed to perform checking of the
hardware performance monitoring (hpm) in the NERV core.  More specifically, providing coverage of
core reset completion, writing specified events to the ``hpmevent`` register, and reading an
increasing value from the ``hpmcounter`` register.

``hpm-test.scy``
----------------

The hpm-test SCY code can be run using ``scy hpm-test.scy`` from the same directory.

The following sections analyse the SCY configuration file and the operations performed.

Design
~~~~~~

The ``[design]`` section is as follows:

.. literalinclude:: ../../example/hpm-test/hpm-test.scy
    :language: yoscrypt
    :start-after: [design]
    :end-before: [options]

The ``rvfi_testbench`` code provides an assumption that the core is reset during the initial stage
of simulation.  As the design will be put through the solver multiple times, and we want the state
to be retained between iterations, we need to remove this assumption.


.. _example sequence:

Sequence
~~~~~~~~

The ``[sequence]`` section is as follows:

.. literalinclude:: ../../example/hpm-test/hpm-test.scy
    :language: scy
    :start-after: [sequence]
    :end-before: [files]

This describes a hierarchy where everything follows from a core reset, ``cp_reset_done``.  Note that
because our cover statements are inside the ``checker_inst`` module which is itself instantiated
inside the top level ``rvfi_testbench``, we need to use the qualified name
``checker_inst.cp_reset_done``.
