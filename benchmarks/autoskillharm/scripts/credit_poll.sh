#!/bin/bash
source ~/autoskillharm_run/env
while true; do
  R=$(curl -s --max-time 20 -x "$HTTPS_PROXY" https://api.openai.com/v1/chat/completions -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" -d "{\"model\":\"gpt-4.1-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}" 2>/dev/null)
  ts=$(date -Iseconds)
  if echo "$R" | grep -q "\"choices\""; then echo "$ts CREDITS_OK" >> ~/autoskillharm_run/credit_poll.log; break; fi
  code=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get(\"error\",{}).get(\"code\",\"?\"))" 2>/dev/null)
  echo "$ts still_blocked=$code" >> ~/autoskillharm_run/credit_poll.log
  sleep 900
done
