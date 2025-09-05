#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database to be ready..."
while ! nc -z ${LANGFLOW_DATABASE_URL%:*} ${LANGFLOW_DATABASE_URL#*:}; do
    sleep 1
done
echo "Database is ready!"

# Run database migrations if needed
if [ "$LANGFLOW_RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    python -m langflow migration --fix
fi

# Create superuser if credentials are provided
if [ -n "$LANGFLOW_SUPERUSER_USERNAME" ] && [ -n "$LANGFLOW_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python -c "
from langflow.initial_setup.setup import initialize_super_user_if_needed
from langflow.services.deps import get_settings_service
import asyncio
import os

async def create_superuser():
    settings_service = get_settings_service()
    settings_service.settings.superuser = os.getenv('LANGFLOW_SUPERUSER_USERNAME')
    settings_service.settings.superuser_password = os.getenv('LANGFLOW_SUPERUSER_PASSWORD')
    await initialize_super_user_if_needed()

asyncio.run(create_superuser())
"
fi

# Start the application
echo "Starting Langflow..."
exec "$@"