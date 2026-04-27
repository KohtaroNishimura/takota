#!/usr/bin/env bash
set -euo pipefail

journalctl --user -u takota-people-flow.service -f
