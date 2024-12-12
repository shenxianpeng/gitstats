TAG ?= latest

all: help

help:
	@echo "Usage:"
	@echo
	@echo "make image                     # make a docker image"
	@echo "make publish-image             # publish docker image to ghcr"
	@echo "make preview                   # preview gitstats report in local"
	@echo

image:
	@docker build -t gitstats:$(TAG) .

publish-image: image
	@docker tag gitstats:$(TAG) ghcr.io/shenxianpeng/gitstats:$(TAG)
	@docker push ghcr.io/shenxianpeng/gitstats:$(TAG)

preview:
	@mkdir -p gitstats-report
	@gitstats . gitstats-report
	@python3 -m http.server 8000 -d gitstats-report

.PHONY: all help install release image publish-image
