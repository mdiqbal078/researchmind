.PHONY: run test eval clean

run:
	@echo "Starting ResearchMind services..."
	docker-compose up -d

stop:
	@echo "Stopping ResearchMind services..."
	docker-compose down

logs:
	docker-compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
