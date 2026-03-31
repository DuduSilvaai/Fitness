FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Railway injects PORT env var
EXPOSE ${PORT:-5000}

# Run with Waitress via app.py
CMD ["python", "app.py"]
