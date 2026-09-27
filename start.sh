#!/bin/bash

mkdir -p .streamlit

echo "$STREAMLIT_SECRETS" > .streamlit/secrets.toml

streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT