#!/bin/sh
set -eu
python -m pytest -q tests \
  --ignore=tests/selenium \
  --ignore=tests/appium \
  --cov=backend.fixtures \
  --cov=backend.scoring \
  --cov=backend.standings \
  --cov=backend.store \
  --cov=backend.roster \
  --cov=backend.rbac \
  --cov-report=term
