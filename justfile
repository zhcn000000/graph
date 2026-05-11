web:
  cd backend && uv run knowgraph start

initdb:
  cd backend && uv run knowgraph initdb

ui:
  cd frontend && pnpm dev

build-ui:
  cd frontend && pnpm build
  rm -rf ../static
  cp -r dist ../static
  

database:
  cd docker && podman-compose up database

web-docker:
  cd docker && podman-compose up web

docker:
  cd docker && podman-compose up
