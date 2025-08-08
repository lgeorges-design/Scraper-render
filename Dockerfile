FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Dossier de travail
WORKDIR /app

# Dépendances Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Code
COPY app.py /app/app.py

# Port exposé (Render fournit $PORT, lu par app.py)
EXPOSE 8000

CMD ["python", "app.py"]
