#!/bin/bash
# amodp_both.sh TILE: both boards sweep TILE at once (each lock-in reloaded first), then one plot of both in compare/,
# and the data committed in each tutorial repo.  ONLY=ecp5 or ONLY=icepi sweeps one board.  The sweep itself is the
# tutorials' src/verilog/amodp.py.
D=$(cd "$(dirname "$0")" && pwd); S=$D/logs; mkdir -p $S $D/compare
export OSS_CAD_SUITE=~/mudd/133electronics/icepi-zero-dac-adc/tools/oss-cad-suite; export PATH=$OSS_CAD_SUITE/bin:$PATH
T=$1; shift
E=$$; I=$$; : > $S/amodp_ecp5_$T.log; : > $S/amodp_icepi_$T.log
if [ "$ONLY" != icepi ]; then cd ~/mudd/133electronics/ecp5-2adc-2dac-tutorial/src/verilog; python3 amodp.py $T --load "$@" > $S/amodp_ecp5_$T.log 2>&1 & E=$!; fi
if [ "$ONLY" != ecp5 ]; then cd ~/mudd/133electronics/icepi-zero-dac-adc/src/verilog; python3 amodp.py $T --load "$@" > $S/amodp_icepi_$T.log 2>&1 & I=$!; fi
[ $E != $$ ] && tail --pid=$E -f /dev/null; [ $I != $$ ] && tail --pid=$I -f /dev/null
tail -2 $S/amodp_ecp5_$T.log; tail -2 $S/amodp_icepi_$T.log
python3 $D/amodp_plot.py $T $D/compare
for R in ~/mudd/133electronics/ecp5-2adc-2dac-tutorial ~/mudd/133electronics/icepi-zero-dac-adc; do
  cd $R; git add dev/data/amodp > /dev/null 2>&1; git -c user.name="Jason Gallicchio" -c user.email="jason@gallicchio.org" commit -q -m "AMOD-P $T measured (amodp.py)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Uf588GeGuaJ8vb8pWfQfmA" > /dev/null 2>&1
done
