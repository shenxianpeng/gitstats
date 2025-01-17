FROM python:3.13-slim

ARG VERSION

# Install git and clean up unnecessary files to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gnuplot \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install gitstats${VERSION:+==$VERSION}

USER nobody

ENTRYPOINT [ "gitstats"]

# Add metadata labels
LABEL org.opencontainers.image.source="https://github.com/shenxianpeng/gitstats" \
      org.opencontainers.image.description="GitStats - Visualize Your Git Repositories" \
      org.opencontainers.image.licenses="GPLv3"
