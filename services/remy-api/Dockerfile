FROM python:3.11-slim

WORKDIR /app

# Install uv for faster package installation
RUN pip install uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install dependencies
RUN uv pip install --system -e .

# Create data directory
RUN mkdir -p data/checkpoints

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "remy_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
