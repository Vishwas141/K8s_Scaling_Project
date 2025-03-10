FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the custom app code
COPY custom_app.py /app/

# Expose port 6000 for the /user_count endpoint
EXPOSE 6000

CMD ["python", "custom_app.py"]
