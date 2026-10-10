FROM postgres:16.15

ARG HYPOPG_VERSION=1.4.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && git clone \
        --branch ${HYPOPG_VERSION} \
        --depth 1 \
        https://github.com/HypoPG/hypopg.git \
        /tmp/hypopg \
    && cd /tmp/hypopg \
    && make \
    && make install \
    && rm -rf /tmp/hypopg \
    && apt-get remove -y \
        build-essential \
        git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*