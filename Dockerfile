# Start with the official Python image (3.11 is a good, stable version)
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
# This is a key step: installing dependencies first allows Docker to cache this layer
# so rebuilds are faster if only the code changes.
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Expose the port your FastAPI application will listen on (Google Cloud Run requires 8080 by default)
ENV PORT 8080
EXPOSE 8080

# Define the command to run your application using Gunicorn and Uvicorn
# This is equivalent to your Procfile command, but uses the standard Docker ENTRYPOINT
# We use the environment variable $PORT for flexibility
CMD exec gunicorn --bind :$PORT --workers 4 --worker-class uvicorn.workers.UvicornWorker main:app
