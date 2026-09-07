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

To run all tests (including coverage), call:

```bash
uv run --group cicd pytest
```
