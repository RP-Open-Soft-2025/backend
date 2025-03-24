FROM python:3.11.4

WORKDIR /app

# Copy only requirements file to leverage Docker cache
ADD requirements.txt /app/requirements.txt

# Upgrade pip and install dependencies first
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the rest of the application files
COPY ./ /app

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

