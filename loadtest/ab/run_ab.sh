#!/bin/bash
cd "$(dirname "$0")"

./run_one.sh beam5_fallback --batch-beam-size 5 --batch-temperature-fallback
./run_one.sh beam5_nofallback --batch-beam-size 5 --no-batch-temperature-fallback
./run_one.sh beam1_nofallback --batch-beam-size 1 --no-batch-temperature-fallback
echo ALL DONE
