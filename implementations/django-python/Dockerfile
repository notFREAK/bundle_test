FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8001
CMD ["python3","manage.py","runserver","0.0.0.0:8001"]
