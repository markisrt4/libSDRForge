# Contributing to libSDRForge

Thanks for helping build libSDRForge. You can start with a documentation fix,
a repeatable test, or an improvement to an adapter you already use.

## Finding something to work on

Search the existing interfaces, implementations, examples and tests before
adding a new abstraction. Open an issue to discuss substantial design
changes. Explain the use case, affected services or hardware, and how
someone else could reproduce the result.

## Setting up a development environment

From a checkout of your feature branch, use Python 3.11 or later:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,quality]'
python -m pytest -q
```

The pull-request workflow runs pytest, Ruff, mypy and packaging on Python 3.11–3.13, plus a separate docstring and Doxygen job.

## A quick architecture tour

Start with the [architecture guide](docs/architecture.md) to see where
contracts, adapters and application responsibilities belong. Reuse an
existing contract when it fits the capability being added. Keep device
and service dependencies at the adapter boundary.

## Where tests belong

- `tests/` holds unattended pytest tests. Use focused unit tests for isolated
  behavior and integration tests for boundaries between real library
  components. Existing coverage includes IQ sources, demodulation, protocols, receiver lifecycle and replay.
- `component_test/` holds manual checks. See the
  [component test guide](component_test/README.md) for the command,
  prerequisites and expected result.
- `examples/` holds usage examples. Link existing scripts from the
  component test guide when the same command also verifies a real setup.

Prefer synthetic IQ or a small redistributable recording. Document source format, sample rate and frequency units. Public Python interfaces use Doxygen docstrings with @brief, @param and @return where applicable.

## Public interfaces and documentation

Annotate public Python APIs. Document inputs, units, outputs, failure
behavior and optional dependencies alongside the interface. Use Mermaid
for architecture, data flow and sequences. Update the README, relevant
design guide and affected example commands with behavior changes.

## Preparing a pull request

Work on a feature branch. Explain what changed, how to reproduce it,
which checks passed and which ones need hardware or a live service.
Remove private data and credentials from logs, preserve existing license
notices, and follow [AGENTS.md](AGENTS.md) for repository-specific checks.
