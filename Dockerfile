FROM python:3.13-slim

ARG VERSION

# Install git and clean up unnecessary files to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -z "$VERSION" ]; then \
        pip3 install git+https://github.com/shenxianpeng/gitstats.git@main; \
    else \
        pip3 install git+https://github.com/shenxianpeng/gitstats.git@$VERSION; \
    fi

USER nobody

ENTRYPOINT [ "gitstats"]

LABEL com.github.actions.name="Git Stats"
LABEL com.github.actions.description="Check commit message formatting, branch naming, commit author, email, and more."
LABEL com.github.actions.icon="code"
LABEL com.github.actions.color="gray-dark"

LABEL repository="https://github.com/shenxianpeng/git"
LABEL maintainer="shenxianpeng <20297606+shenxianpeng@users.noreply.github.com>"
