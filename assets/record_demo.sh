#!/bin/bash
# Record a ValuX demo using asciinema
# Usage: bash assets/record_demo.sh
#
# Prerequisites:
#   pip install asciinema
#   npm install -g svg-term-cli   (optional, for SVG output)
#
# After recording:
#   1. Upload to asciinema.org:  asciinema upload assets/demo.cast
#   2. Or convert to GIF:       pip install asciinema-agg && agg assets/demo.cast assets/demo.gif
#   3. Or convert to SVG:       svg-term --in assets/demo.cast --out assets/demo.svg --window

echo "Recording ValuX demo..."
echo "Tips:"
echo "  - Use 600519.SS (Moutai) for A-share demo (free, no API key)"
echo "  - Use 0700.HK (Tencent) for HK demo (free annual data)"
echo "  - Type slowly and pause briefly after each step for readability"
echo "  - Press Ctrl+D or type 'exit' to stop recording"
echo ""

asciinema rec assets/demo.cast \
  --title "ValuX - AI DCF Stock Valuation" \
  --idle-time-limit 3 \
  --cols 120 \
  --rows 35
