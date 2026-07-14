# Contribution guidelines

Thank you for your interest in contributing to kibad-crawler.

The following guidelines ensure consistency across the project, so please read them thoroughly.

## Setup

Install the project with development dependencies:

```bash
uv sync --group cicd
```

## Local checks and CI commands

To run code quality checks and static type checking, call:

```bash
uv run --group cicd prek run -a
```

This runs all configured [prek](https://prek.j178.dev/) hooks (see [pre-commit-config.yaml](/.pre-commit-config.yaml)) on all files. Some hooks may fix issues automatically, others will report issues that need to be fixed manually.

To run all Python tests with `pytest`:

```bash
uv run pytest
# if you have not run 'uv sync --group cicd' previously, use instead
uv run --group cicd pytest
```

The following commands run on GitHub CI (see [code_quality_and_tests.yml](../.github/workflows/code_quality_and_tests.yml)), but can also be run locally:

Use this exact command set before claiming local CI readiness or `CONTRIBUTING.md` test compliance. Running only the checks for the files you touched is often fine while iterating, but do not present that as a full CI-equivalent run.

```bash
uv run --group cicd prek run -a
# the '-m "not slow"' bit is residue, to be cleaned up by a future polishing pr
uv run --group cicd pytest -m "not slow"
```
