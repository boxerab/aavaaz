#!/bin/bash
cd "$(dirname "$0")/../.."

name=$1
shift
out=loadtest/ab/$name
mkdir -p "$out"

uv run aavaaz serve --model small --batch-inference "$@" --max-clients 500 --max-connection-time 900 --metrics-port 9100 > "$out/server.log" 2>&1 &
srv=$!
for i in $(seq 1 90)
do
  ss -ltn | grep -q ':9090 ' && ss -ltn | grep -q ':9100 ' && break
  sleep 2
done

uv run loadtest/scrape_metrics.py --targets localhost:9100 --out "$out/metrics.csv" > /dev/null 2>&1 &
scr=$!
uv run loadtest/stream_clients.py --clients 30 --ramp-step 30 --ramp-interval 30 --hold 150 --stop-lag 0 --out "$out" > "$out/clients.log" 2>&1

kill $scr
pkill -P $srv
kill $srv
sleep 5
echo "$name done"
