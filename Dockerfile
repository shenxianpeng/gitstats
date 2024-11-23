FROM python:3.13-slim

ARG VERSION

# Install git and clean up unnecessary files to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gnuplot \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -z "$VERSION" ]; then \
        pip3 install git+https://github.com/shenxianpeng/gitstats.git@main; \
    else \
        pip3 install git+https://github.com/shenxianpeng/gitstats.git@$VERSION; \
    fi

USER nobody

ENTRYPOINT [ "gitstats"]

LABEL org.opencontainers.image.source="https://github.com/shenxianpeng/gitstats"
LABEL org.opencontainers.image.description="Git History Statistics Generator"
LABEL org.opencontainers.image.licenses="GPLv3"
