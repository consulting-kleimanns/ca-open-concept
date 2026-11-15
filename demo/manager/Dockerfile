FROM python:3.13-slim
RUN pip install --no-cache-dir aiohttp==3.12.15
WORKDIR /app
COPY demo/manager/my_van_manager.py demo/manager/my_van_mcp.py /app/
COPY demo/manager/static /app/static
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "/app/my_van_manager.py"]
