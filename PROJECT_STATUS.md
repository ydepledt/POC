# Project status

**Status:** Prototype / sandbox

**Summary:** Canonical playground for small experiments and proofs of concept including visualization, simulation, procedural generation and machine-learning demos.

**Reviewed:** 2026-08-28

## Prototypes imported on 2026-10-17

| Folder | Project | Local validation |
| --- | --- | --- |
| [agent-racing](agent-racing/README.md) | Evolution Lab: neural car training, replays and video exports | 59 tests passed |
| [x_signal_watch_v2](x_signal_watch_v2/README.md) | X news collection, event deduplication and Streamlit dashboard | Unit tests passed, with external services mocked |

Each prototype keeps its own installation instructions and dependencies. Python environments, local databases, simulations, videos, account cookies and `.env` credentials are excluded. `x_signal_watch_v2/.env.example` documents the expected configuration without credentials.

Eight accidentally tracked `:Zone.Identifier` metadata files were removed from the current tree so that the repository can be cloned on Windows. The original project files and earlier history are retained.
