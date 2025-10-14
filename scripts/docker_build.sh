docker build -t arxiv-paper-digest .
docker run -d \
  --name arxiv-paper-digest \
  --env-file .env \
  -p 33333:8000 \
  -v "$(pwd)/papers.sqlite3:/app/papers.sqlite3" \
  arxiv-paper-digest