FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Use a venv for cleanliness
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install Python deps
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app
COPY app.py /app/app.py

# Render sets the PORT env var; our app will use it
EXPOSE 8000

CMD ["python", "app.py"]
