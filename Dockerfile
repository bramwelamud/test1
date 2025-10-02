FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directories
RUN mkdir -p data/assessments data/reports

# Set environment variables
ENV PORT=8080
ENV FLASK_ENV=production

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]
