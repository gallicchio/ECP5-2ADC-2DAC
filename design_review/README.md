# Design reviews of rev A

Every review the design had before it was ordered, each in its reviewer's directory, as received.

| directory | reviewer | reviewed |
|---|---|---|
| [`Claude-ultrareview/`](Claude-ultrareview/) | Claude Code's cloud review of the pull request (2026-10-04) | build 25 |
| [`CopilotSDK/`](CopilotSDK/) | Copilot SDK | round 1, build 25 |
| [`Gemini_3.8_Flash/`](Gemini_3.8_Flash/) | Gemini 3.8 Flash | round 1, build 25 |
| [`Grok4.7/`](Grok4.7/) | Grok 4.7 | round 1, build 25 |
| [`CopilotSDK2/`](CopilotSDK2/) | Copilot SDK | round 2, build 31: the last look before the order |
| [`Gemini_3.8_Flash2/`](Gemini_3.8_Flash2/) | Gemini 3.8 Flash | round 2, build 31 |

The briefs are [`../DESIGN_REVIEW_PROMPT.md`](../DESIGN_REVIEW_PROMPT.md) (round 1) and
[`../DESIGN_REVIEW_PROMPT2.md`](../DESIGN_REVIEW_PROMPT2.md) (round 2); what was done about each finding is
[`../DESIGN_REVIEW_RESPONSE.md`](../DESIGN_REVIEW_RESPONSE.md).

Reading them:

- **None of them found the two faults that kept rev A's USB port from working.** The bench did
  ([`../bringup/REVB.md`](../bringup/REVB.md), rows 12 and 13).
- **Old paths.** Until the public release these directories were `design_review_<name>/` at the top of the
  project (round 2's Gemini review was `design_review2_Gemini_3.8_Flash/`). The reports, the chat log and the
  commit history use those names.
- **No datasheets.** The reviewers' copies of vendor datasheets (PDFs, their text, renders of their pages) are
  not published: they are the vendors' copyright. `tools/jlc_datasheet.py` and `tools/adi_datasheet.py` fetch
  them.
- **`<name>/repo/` and `<name>/kicad_copy/`** are a reviewer's private working copies. They are not in git.
