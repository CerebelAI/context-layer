# Imports flow one way: server → knowledge → connectors

**Status: accepted.**

Three top-level modules mirror the pipeline, and imports run in one direction only. Cross-
module imports go through a module's `__init__.py`; nothing reaches into a submodule. The rule
applies recursively.

Complexity goes down into submodules, never out into new top-level modules. Adding a
top-level module is a decision to discuss, never done unprompted.

## Consequences

- `connectors` imports from neither of the others, which is what makes it testable against
  captured API responses with nothing else in the picture.
- `knowledge` imports `connectors` only for the `Envelope` type — see ADR-0006.
- A connector's public interface is re-exported from `connectors/__init__.py`. The submodule
  import sits at the bottom of that file, after `Envelope` is defined, because a connector
  imports `Envelope` from its own package.
