FROM node:20-slim

# Install Python and Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv chromium \
    && rm -rf /var/lib/apt/lists/*

# Create grader virtual environment
RUN python3 -m venv /opt/grader-venv

# Install grader Python packages
RUN /opt/grader-venv/bin/pip install --no-cache-dir \
    playwright anthropic openai Pillow numpy scikit-image

# Install Playwright browsers
RUN /opt/grader-venv/bin/python -m playwright install --with-deps chromium

WORKDIR /app

# Copy image assets into the working directory
COPY assets/ /app/assets/

# Copy reference screenshots so the agent can view them
COPY reference_screenshots/ /app/reference_screenshots/
