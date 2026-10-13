# ======= CONFIGURAÇÕES =======
HARBOR_REGISTRY = 172.21.70.155
HARBOR_PROJECT  = pricedev
HARBOR_USER     = admin
PLAT            = linux/amd64
IMAGES          = backend frontend
TAG             = latest

.PHONY: help login publish

help:
	@echo "Targets:"
	@echo "  make publish HARBOR_PASSWORD=xxx"
	@echo ""
	@echo "Faz build e push das imagens $(IMAGES) para"
	@echo "$(HARBOR_REGISTRY)/$(HARBOR_PROJECT)/*:latest"

login:
	@test -n "$(HARBOR_PASSWORD)" || { echo "❌ Informe a senha: make publish HARBOR_PASSWORD=xxx"; exit 1; }
	@echo "$(HARBOR_PASSWORD)" | docker login $(HARBOR_REGISTRY) -u $(HARBOR_USER) --password-stdin

publish: login
	@for imagem in $(IMAGES); do \
		echo "🚀 Build $$imagem (tag=$(TAG))"; \
		docker buildx build ./$$imagem \
			--platform=$(PLAT) \
			-t $(HARBOR_REGISTRY)/$(HARBOR_PROJECT)/$$imagem:$(TAG) \
			--push \
		|| exit 1; \
	done
	@echo "✅ $(HARBOR_PROJECT) publicado em $(HARBOR_REGISTRY)/$(HARBOR_PROJECT)/*:$(TAG)"