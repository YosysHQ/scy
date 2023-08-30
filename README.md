# Sequence of Covers with Yosys (SCY)

SCY is a tool for creating deep formal traces, by splitting the property to
cover into smaller cover properties, which the solver will cover eagerly
in sequence.

The cover points themselves are SVA cover properties. Additional data-flow
analysis properties and SVA restrict/assume properties can be used to further
narrow the search space to certain traces.

## Note on installation

Requires Yosys with PR #3903.

