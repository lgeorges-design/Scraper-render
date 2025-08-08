FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Empêche pip de retélécharger les navigateurs (déjà présents dans l'image)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

EXPOSE 8000
CMD ["python", "app.py"]