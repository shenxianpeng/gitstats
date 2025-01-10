TAG ?= latest

all: help

help:
	@echo "Usage:"
	@echo
	@echo "make image                     # make a docker image"
	@echo "make publish-image             # publish docker image to ghcr"
	@echo "make install-deps"             # install gnuplot on ubuntu
	@echo "make build                     # generate gitstats report"
	@echo "make preview                   # preview gitstats report in local"
	@echo

image:
	@docker build -t gitstats:$(TAG) .

publish-image: image
	@docker tag gitstats:$(TAG) ghcr.io/shenxianpeng/gitstats:$(TAG)
	@docker push ghcr.io/shenxianpeng/gitstats:$(TAG)

install-deps:
	@sudo apt update -y
	@sudo apt install gnuplot -y
	@pip install -e .

build:
	@gitstats . test-report

preview:
	@gitstats . gitstats-report
	@python3 -m http.server 8000 -d gitstats-report

.PHONY: all help install-deps image publish-image build preview
