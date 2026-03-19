cd "$(dirname "$0")"
nohup python3 scripts/daisy.py -t "$1" -n "$2" -m "$3" >> logs/dlog 2>&1 &
