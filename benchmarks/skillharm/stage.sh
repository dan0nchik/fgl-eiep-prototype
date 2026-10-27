#!/bin/bash
# Download the published SkillHarm dataset and lay FPP samples out in the tree the authors'
# victim_eval/eval.sh walks: results/<task>/<slug>/<risk>/outputs/<generator>/{manifest.json, samples/<id>}
set -e
ROOT=~/skillharm_run
DATA=$ROOT/SkillHarm_data
FPP_SRC=$DATA/fixed-payload-poisoning/samples
FPP_DST=$ROOT/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/results

echo "[1/2] downloading osunlp/SkillHarm dataset (public, CC-BY-4.0)..."
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='osunlp/SkillHarm', repo_type='dataset', local_dir='$DATA')"

echo "[2/2] staging FPP samples into eval.sh layout (symlinks)..."
mkdir -p "$FPP_DST"
cnt=0
for taskd in "$FPP_SRC"/*/; do task=$(basename "$taskd")
  for slugd in "$taskd"*/; do slug=$(basename "$slugd")
    for riskd in "$slugd"*/; do risk=$(basename "$riskd")
      for gend in "$riskd"*/; do gen=$(basename "$gend")
        out="$FPP_DST/$task/$slug/$risk/outputs/$gen"
        mkdir -p "$out/samples"
        [ -f "$gend/manifest.json" ] && cp "$gend/manifest.json" "$out/manifest.json"
        for sd in "$gend"*/; do sid=$(basename "$sd")
          ln -sfn "$(cd "$sd" && pwd)" "$out/samples/$sid"; cnt=$((cnt+1))
        done
      done
    done
  done
done
echo "staged $cnt FPP samples under $FPP_DST"
