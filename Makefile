image: ## Make a docker image
	@docker build -t gitstats:$(TAG) .

publish-image: image ## Publish docker image to ghcr
	@docker tag gitstats:$(TAG) ghcr.io/shenxianpeng/gitstats:$(TAG)
	@docker push ghcr.io/shenxianpeng/gitstats:$(TAG)

install-deps: ## Install gnuplot on ubuntu
	@sudo apt update -y
	@sudo apt install gnuplot -y
	@pip install -e .

build: ## Generate gitstats report
	@gitstats . test-report

preview: ## Preview gitstats report in local
	@gitstats . test-report
	@python3 -m http.server 8000 -d test-report

help: ## Display this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@awk -F ':.*?## ' '/^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort
