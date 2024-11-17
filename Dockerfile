FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        git \
        gnuplot \
        python3.12 \
        python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

# Set Python3.12 as the default Python version
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

WORKDIR /app

RUN python3 --version \
    && python3 -m venv venv \
    && . venv/bin/activate \
    && python3 -m pip install --upgrade pip \
    && pip install git+https://github.com/shenxianpeng/gitstats.git@main

ENTRYPOINT ["bash", "-c", "source venv/bin/activate && gitstats"]
