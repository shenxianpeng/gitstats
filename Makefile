RESOURCES=gitstats.css sortable.js *.gif
VERSION := $(shell python3 -c "from setuptools_scm import get_version; print(get_version())")
SEDVERSION=perl -pi -e 's/VERSION = 0/VERSION = "$(VERSION)"/' --
TAG ?= latest

all: help

help:
	@echo "Usage:"
	@echo
	@echo "make release [VERSION=foo]     # make a release tarball"
	@echo "make image                     # make a docker image"
	@echo "make publish-image             # publish docker image to ghcr"
	@echo "make preview                   # preview gitstats report in local"
	@echo
	
release:
	@cp gitstats gitstats.tmp
	@$(SEDVERSION) gitstats.tmp
	@tar --owner=0 --group=0 --transform 's!^!gitstats/!' --transform 's!gitstats.tmp!gitstats!' -zcf gitstats-$(VERSION).tar.gz gitstats.tmp $(RESOURCES) doc/ Makefile
	@$(RM) gitstats.tmp

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
