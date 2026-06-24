docker compose up -d postgres
docker compose run --rm init
docker compose run --rm ingest 
docker compose up -d api streamlit
