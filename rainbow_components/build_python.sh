#!/bin/bash

conda deactivate
source venv/bin/activate
npm run build:backends
npm run build:js
deactivate
conda activate dash
pip install .
