cd "$(dirname "$0")"
nohup python3 daisy.py -t "$1" -n "$2" -m "$3" >> dlog 2>&1 &
