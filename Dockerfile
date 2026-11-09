FROM python:3.12

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /opt/kibad-crawler

RUN apt-get update \
    && apt-get install vim tree btop -y \
    && git config --global pager.branch false

RUN cd /opt/kibad-crawler && uv sync --frozen --no-cache

WORKDIR /opt/kibad-crawler