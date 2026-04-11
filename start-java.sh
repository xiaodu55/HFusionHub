#!/bin/bash
export DB_USERNAME=hfusionhub
export DB_PASSWORD=hfusionhub123
export CALLBACK_SECRET=callback-dev-secret-123
export PYTHON_AI_INTERNAL_TOKEN=internal-dev-token-123
export ADMIN_PASSWORD=admin123
cd d:/college/development/HFusionHub1/java-backend
mvn spring-boot:run -q
