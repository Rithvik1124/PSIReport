#!/bin/bash
set -e

URL="${URL:-https://example.com}"
STRATEGY="${STRATEGY:-desktop}"
MODEL="${MODEL:-gpt-4o}"
OUT_DIR="${OUT_DIR:-out}"
PREFIX="${PREFIX:-report}"

echo "========================================="
echo "Running Lighthouse for: $URL"
echo "Strategy: $STRATEGY"
echo "Model: $MODEL"
echo "Output Dir: $OUT_DIR"
echo "========================================="

# Ensure output directory exists
mkdir -p "$OUT_DIR"

# 1) Run Lighthouse
lighthouse "$URL" \
    --output=json \
    --output=html \
    --output-path="$OUT_DIR/$PREFIX" \
    --chrome-flags="--headless --no-sandbox --disable-gpu" \
    --preset="$STRATEGY"

# 2) Convert HTML to PDF
echo "Converting HTML to PDF..."
CHROME_BIN=$(which chromium || which chromium-browser || which google-chrome || which google-chrome-stable)
$CHROME_BIN \
    --headless \
    --disable-gpu \
    --no-sandbox \
    --print-to-pdf="$OUT_DIR/$PREFIX.report.pdf" \
    "$(realpath "$OUT_DIR/$PREFIX.report.html")"

# 3) Generate AI advice DOCX
if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "OPENAI_API_KEY is not set. Skipping OpenAI advice generation."
else
  echo "Generating OpenAI advice..."
  python run.py \
    --url "$URL" \
    --model "$MODEL" \
    --strategy "$STRATEGY" \
    --out-dir "$OUT_DIR" \
    --prefix "$PREFIX"
fi

# 4) Launch Streamlit
echo "Starting Streamlit app..."
streamlit run streamlit_app.py -- --url "$URL" --strategy "$STRATEGY"
