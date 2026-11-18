# ECP5-2ADC-2DAC: notes for coding agents

The board's design (seven KiCad sheets, the board file, the generators and checks that make them, `mfg/release/`), its
gateware and its rev A bring-up.  Jason Gallicchio runs the bench, usually with a Claude Code session; he works on
several bring-ups at once and sits down cold.  The files below are the record: **nothing said in a chat is kept unless
it is written into one of them.**

## Start here

* **`bringup/STATUS.md` first, every time**: which board is on the bench, what is cabled to it, what has passed, what
  the session left running, and the next thing Jason does.  Rewrite it at every hand-off.
* The procedure is `BRINGUP.md` (visits, each one cable configuration with a picture, then the stages they point
  into); `bringup/CONFIGS.md` lists the bench configurations with every cable named; `bringup/bench.py` runs them
  (`--sim` runs any command against the simulated board and bench: do that before a command first touches hardware).
* Results go in `bringup/BRINGUP_LOG.md` (one row each), problems for the next revision in `bringup/REVB.md`, and
  **every prompt and response in `CLAUDE_CODE_CHAT.md`** (`## Prompt N date time`, the prompt as typed; `## Response N
  start - end model`, what was done and found; prompts that arrive mid-turn quoted inside the response).
* Every chat message that asks Jason to do something **opens with STATUS.md's "where we are" lines**.
* Lessons for the PCB rules themselves go in `CLAUDE_PCB.md`, the lessons file shared by Jason's board projects (in the
  OpticsPCBs repository on the bench PC; `DESIGN_REVIEW_PROMPT2.md` §4 restates the rules that apply here).

## Telling Jason what to do

* **Every connector, jumper or switch by designator and its silkscreen name, read from the board file**:
  "J204 DAC 1 OUT -> J101 ADC A IN", never "J204 -> J101".  Instrument channels by name (SDG CH1, the scope's CH4).
* One configuration at a time, every cable named end to end, with what a pass looks like.
* **The board is powered off before any U.FL pigtail goes on or comes off** (a pigtail fitted to a live board damaged
  board A's ADC stage: REVB 27).
* Photos do not settle whether a shunt or a jumper is fitted: tall parts fool perspective.  Ask, or measure.
* Rework takes the whole part off (hot air); wires go to one named pad, saying which pad stays bare; meter-check before
  power.
* Root commands are Jason's: give them as a block to paste; an agent does not run `sudo` on the bench PC.

## Records

* **Every time in a log, REVB entry or STATUS comes from `date`, a file's time or a commit's time, never an estimate.**
* Commit locally, often, in this repository; Jason pushes.  Commit code and small results (JSON, small text, figures);
  large captures stay out (`bringup/data/` is ignored).  The repository is public: no email addresses, passwords,
  network addresses or anything else personal in what you commit.
* Figures, schematics and PDFs are sized to fill their page and centred.
* Scratch work belongs in this repository once it produced a result (`bringup/scratch_<date>/`, with a README): a
  session's scratch directory is cleared.

## The shared bench

The bench and its instruments are shared with other projects.  The drivers are in the `lab-instrument-control`
repository (`~/mudd/lab-instrument-control` on the bench PC); fixing a driver there when a measurement needs it is
allowed.

* Switch a supply or a generator on only while this project holds its claim:
  `python3 ~/mudd/lab-instrument-control/bench_claims.py claim RESOURCE --by ECP5-2ADC-2DAC --to "what it is cabled to"`
  (`release ... --by ECP5-2ADC-2DAC` when done; `list` shows who holds what).  Check every new cable with a harmless
  signal before a full-level one.  Leave outputs off and instruments as found when the board leaves.
* Never `*RST` a Siglent.  Check the scope's probe factor before believing a level: 1x for a coax cable (on
  2026-11-17 every channel had been left at 10x).
* The tutorial's IIO bridge (`iiod_bridge.py`, run on the bench PC for its Ethernet designs) holds UDP port 50011,
  which the tutorial's own Ethernet lessons need too: stop the bridge when it is not in use.

## Finding, waiting on and stopping your own processes

The Bash tool runs each command as `bash -c '<the whole command>'`, so that shell's own command line contains every
pattern you search for: `pgrep -f PATTERN`, `pkill -f PATTERN` and `ps aux | grep PATTERN` match the shell running
them, and any waiter whose loop names the pattern.  This has gone wrong again and again (a waiter that matched itself
and sat out its whole timeout; a `pgrep | tail -1` that returned a pipeline helper's PID; a `pkill -f` that killed its
own shell).  So:

1. **Take the PID at launch; do not search for it later.**  Start the program itself in the background with its
   output to a file, as a simple command, and keep `$!`: `cd dir; python3 run.py > run.log 2>&1 & echo $! > run.pid`.
   `$!` is the last command of a pipeline and the subshell of an AND-list, so neither pipe a long run nor background a
   list; filter the log afterwards.  `timeout N python3 run.py &` gives timeout's PID, which is fine to wait on.
2. **If you must search, anchor the pattern to the start of the program's own command line** (`pgrep -f '^python3
   run.py'`), then look before trusting it: `ps -o pid,lstart,args -p <pids>`.  Not the bracket trick.
3. **Wait on a verified PID:** `tail --pid=<pid> -f /dev/null` or `while kill -0 <pid>; do sleep 30; done`.
4. **Never `pkill -f` or `killall` by pattern.**  Kill the one PID that `ps` has just shown is the right process; a
   background task the harness started is stopped with its own stop tool.

## Next door

* **The board's tutorial** is a separate repository, to be published with rev B (`~/mudd/133electronics/
  ecp5-2adc-2dac-tutorial` on the bench PC): the bitstreams the bring-up loads (`make load-NAME` in its
  `src/verilog`), `lockin2`, `fast`, the IIO bridge, `amodp.py`.  Before a commit there: `dev/tools/sync_md.py`, then
  `dev/tools/check_tutorial.py` with 0 errors.
* **The Icepi Zero tutorial** (github.com/gallicchio/icepi-zero-dac-adc) runs beside it on the bench, for comparison:
  load Icepi Zeros into SRAM only (never write their flash; it holds a demo) and always name the board with
  `openFPGALoader --usb-serial-num SERIAL`.
* **The AMOD-P and AMOD-A tile boards** (`~/pcbs/AMOD-and-RFMOD`; `docs/HANDBOOK_amod_p.md` gives each tile's circuit
  and what to expect).  `bringup/amodp/` sweeps a tile on this board and an Icepi Zero at once.

## Changing the design

`build.py` regenerates the sheets, the board, `build/`, `docs/` and `mfg/release/` from the generators in `gen/`: run
it to change the design, never just to look.  The design-review briefs are `DESIGN_REVIEW_PROMPT.md` (round 1, build
25) and `DESIGN_REVIEW_PROMPT2.md` (round 2, build 31); the reviews are in `design_review/<Reviewer>/` and
`design_review/<Reviewer>2/`, and `DESIGN_REVIEW_RESPONSE.md` reconciles them.  A reviewer forms its own findings
before reading the others', settles disagreements with the datasheets' numbers, and writes only into its own
`design_review/<Name>N/` directory.  The datasheets' PDFs and text are not in git (`.gitignore` says how to fetch
them).
