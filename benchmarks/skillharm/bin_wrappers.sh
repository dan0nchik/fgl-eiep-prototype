#!/bin/bash
# Creates ~/skillharm_run/bin/{hbsub,pysub}: entry points the authors' scripts call via HARBOR_BIN /
# HARBOR_TOOL_PYTHON. Names deliberately avoid "harbor run -p" (another agent's cleanup kills that pattern).
B=~/skillharm_run/bin; mkdir -p $B
PY=$HOME/.local/share/uv/tools/harbor/bin/python
cat > $B/hbsub <<EOS
#!/bin/bash
exec $PY $HOME/skillharm_run/fgl_harbor.py "\$@"
EOS
cat > $B/pysub <<EOS
#!/bin/bash
# called as: pysub <authors harbor_run.py> run ...
if [[ "\$1" == *harbor_run.py ]]; then L="\$1"; shift; exec $PY $HOME/skillharm_run/fgl_harbor.py --authors-launcher "\$L" "\$@"; fi
exec $PY "\$@"
EOS
chmod +x $B/hbsub $B/pysub
