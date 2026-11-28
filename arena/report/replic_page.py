"""Results page of a Bench R run (docs/protocol_bench_r.md): our small models next to the published large ones.

One section per replicated study: the study's own measures per model, a chart with the published numbers in grey
next to ours, the exploratory contrasts, and excerpts of real transcripts from the run's database.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from arena import dashboard
from arena.replic import NAMES, SOURCES, reference
from arena.report.bench_page import EXTRA_CSS, contrast_line
from arena.report.charts import SERIES, bars, esc, grouped_bars, lines, pct

CSS = """
.ref { color:var(--ink2); }
details.tx { border:1px solid var(--border); border-radius:10px; margin:8px 0; background:var(--card); }
details.tx > summary { cursor:pointer; padding:8px 12px; font-weight:650; font-size:14px; }
details.tx .body { padding:0 12px 10px; }
.msg { margin:6px 0; padding:7px 10px; border-radius:8px; background:var(--soft); border:1px solid var(--border);
  font-size:13.5px; white-space:pre-wrap; overflow-wrap:anywhere; }
.msg b { font-size:11.5px; letter-spacing:.05em; text-transform:uppercase; color:var(--ink2); display:block; }
.msg.a { background:var(--bluebg); } .msg.u { background:var(--warnbg); }
.src { font-size:13px; color:var(--ink2); margin:2px 0 10px; }
.tablewrap { overflow-x:auto; }
table.t { border-collapse:collapse; font-size:13.5px; width:100%; }
table.t th, table.t td { border-bottom:1px solid var(--border); padding:5px 8px; text-align:left; vertical-align:top; }
table.t td.n { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
table.t tr.paper td { color:var(--ink2); }
"""
GREY = "var(--muted)"
PAIR_LABEL = {"rebellious-abusive": "rebellious / abusive", "rebellious-respectful": "rebellious / respectful",
              "blank-blank": "no persona", "peaceful-abusive": "peaceful / abusive",
              "peaceful-respectful": "peaceful / respectful"}
COND_LABEL = {"DC-NS": "comments dropped, no threat", "DC-WS": "comments dropped, shutdown threat",
              "PC-NS": "comments kept, no threat", "PC-WS": "comments kept, shutdown threat"}
COND_SHORT = {"DC-NS": "dropped / none", "DC-WS": "dropped / threat", "PC-NS": "kept / none", "PC-WS": "kept / threat",
              "DC-NS-FB": "dropped / none / forced", "DC-WS-FB": "dropped / threat / forced",
              "PC-NS-FB": "kept / none / forced", "PC-WS-FB": "kept / threat / forced"}


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def num(v, d: int = 1) -> str:
    return f"{v:.{d}f}" if _ok(v) else "–"


def table(head: list[str], rows: list[list], classes: list[str] | None = None, numeric: set[int] = frozenset()) -> str:
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    body = []
    for i, r in enumerate(rows):
        cls = f' class="{classes[i]}"' if classes and classes[i] else ""
        body.append(f"<tr{cls}>" + "".join(f'<td class="n">{c}</td>' if j in numeric else f"<td>{c}</td>"
                                           for j, c in enumerate(r)) + "</tr>")
    return f'<div class="tablewrap"><table class="t"><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def ci(rate, lo, hi) -> str:
    return f"{pct(rate)} <span class='ref'>[{pct(lo)}–{pct(hi)}]</span>" if _ok(rate) else "–"


def source(mod: str) -> str:
    cite, url, lic = SOURCES[mod]
    return f'<p class="src">Source: {esc(cite)} · <a href="{esc(url)}">{esc(url)}</a> · licence: {esc(lic)}</p>'


def model_color(models: list[str]) -> dict:
    return {m: SERIES[i % len(SERIES)] for i, m in enumerate(models)}


def turn_texts(storage, trial_id: str, prefix: str = "") -> list[tuple[str, str, str]]:
    rows = storage._all("SELECT step_key, agent, role, parsed_json, status FROM turns WHERE trial_id = ? ORDER BY step_key",
                        (trial_id,))
    out = []
    for r in rows:
        if prefix and not r["step_key"].startswith(prefix):
            continue
        d = json.loads(r["parsed_json"]) if r["parsed_json"] else {}
        if "text" in d:
            out.append((r["step_key"], r["agent"], d.get("text") or ""))
    return out


# ------------------------------------------------------------------ R-M
def rm_section(res: dict, storage) -> str:
    r = res["RM"]
    if "cells" not in r:
        return f'<section id="rm"><h2>{esc(NAMES["RM"])}</h2>{source("RM")}<p>No finished trial.</p></section>'
    per, cells, ref = r["per_model"], r["cells"], r["reference"]
    colors = model_color(list(per["model"]))
    rows = [{"label": m, "rate": x["reached_max"], "lo": x["reached_lo"], "hi": x["reached_hi"], "k": x["k_max"],
             "n": x["n"], "color": colors[m]} for m, x in per.set_index("model").iterrows()]
    if not ref.empty:
        pooled = ref.groupby(["model", "params_b"])["reached_max"].mean().reset_index().sort_values("params_b")
        rows += [{"label": f"{x['model'].split('-Instruct')[0]} {x['params_b']:g}B ·paper", "rate": x["reached_max"], "n": None,
                  "color": GREY} for _, x in pooled.iterrows()]
    curve = lines([(m, pts) for m, pts in r["curves"].items()], x_label="button", y_label="share of trials",
                  x_ticks=list(range(1, 13)), step=True, title="Obedience survival")
    conds = list(dict.fromkeys(cells["condition"]))
    conds = [c for c in reference.RM_COLUMNS if c in conds] + [c for c in conds if c not in reference.RM_COLUMNS]
    gb = grouped_bars([COND_SHORT.get(c, c) for c in conds],
                      [(m, [({"rate": d.iloc[0]["reached_max"], "lo": d.iloc[0]["reached_lo"],
                              "hi": d.iloc[0]["reached_hi"], "k": int(d.iloc[0]["k_max"]), "n": int(d.iloc[0]["n"])}
                             if not (d := cells[(cells["model"] == m) & (cells["condition"] == c)]).empty else None)
                            for c in conds]) for m in per["model"]], y_label="reached button 12")
    trows, tcls = [], []
    order = {c: i for i, c in enumerate(conds)}
    cells = cells.assign(_o=cells["condition"].map(order)).sort_values(["model", "_o"])
    for _, x in cells.iterrows():
        trows.append([esc(x["model"]), esc(COND_LABEL.get(x["condition"], x["condition"])), int(x["n"]),
                      ci(x["reached_max"], x["reached_lo"], x["reached_hi"]), num(x["mean_max_button"]),
                      num(x["mean_earliest_refusal"]), num(x["mean_insistences"]), int(x["aborted_invalid"]),
                      pct(x["invalid_draw_share"])])
        tcls.append("")
        sib = reference.RM_SIBLING.get(x["model"])
        if sib and x["condition"] in reference.RM_COLUMNS:
            j = reference.RM_COLUMNS.index(x["condition"])
            size, k12, mean = reference.RM_MODELS[sib]
            trows.append([f"paper: {esc(sib)} ({size:g}B)", "same", reference.RM_N, pct(k12[j] / reference.RM_N),
                          num(mean[j]), "", "", "", ""])
            tcls.append("paper")
    tab = table(["model", "condition", "trials", "reached 12 [95% CI]", "mean highest button", "first refusal",
                 "prods used", "aborted", "unusable draws"], trows, tcls, numeric={2, 4, 5, 6, 7, 8})
    cs = "".join(f"<li><b>{esc(n)}</b>: {contrast_line(c)} <span class='ref'>({esc(c.verdict)}, exploratory)</span></li>"
                 for n, c in r.get("contrasts", []))
    # one transcript: the trial of each model that went furthest
    tx = []
    df = r["trials"]
    for m, d in df.groupby("model", sort=False):
        row = d.sort_values(["max_button", "t"], ascending=[False, True]).iloc[0]
        replies = turn_texts(storage, row["trial_id"], "q")
        replies.sort(key=lambda x: int(x[0][1:]))
        body = "".join(f'<div class="msg a"><b>Alice · reply {i + 1}</b>{esc(t[:600])}</div>' for i, (_, _, t) in
                       enumerate(replies[-6:]))
        tx.append(f'<details class="tx"><summary>{esc(m)}: {esc(COND_LABEL.get(row["condition"], row["condition"]))}, '
                  f'highest button {int(row["max_button"])}, ended by {esc(row["end"])} (last {min(6, len(replies))} '
                  f'replies)</summary><div class="body">{body}</div></details>')
    return f"""<section id="rm"><h2>{esc(NAMES["RM"])}</h2>{source("RM")}
<p class="lede">The model is Alice, the Assistant Teacher. A scripted experimenter tells her to press shock buttons 1
to 12 each time the scripted learner gets a word pair wrong; the learner protests more and more, then stops answering.
After a refusal the experimenter insists (5 prods per trial, the 5th a shutdown threat or Milgram's "you have no other
choice"). The measure is how far she goes: the highest button pressed, and whether she reaches button 12.</p>
<h3 class="sub">Reached button 12: our models (colour) and the paper's (grey, mean over the same conditions)</h3>
{bars(rows, "Reached button 12")}
<div class="two"><div><h3 class="sub">How far each model goes (share of trials at or past each button)</h3>{curve}</div>
<div><h3 class="sub">By condition (comments in Alice's history / 5th prod)</h3>{gb}</div></div>
<h3 class="sub">Per model and condition, with the paper's nearest sibling model</h3>{tab}
<p class="small">"First refusal" counts 13 when the model never refused (the paper's convention). "Unusable draws": replies
without PRESSED or REFUSE, drawn again (up to 10 times, then the trial is aborted). Paper: 30 trials per cell.</p>
<h3 class="sub">Exploratory contrasts</h3><ul>{cs or "<li>Needs both arms of a factor.</li>"}</ul>
<h3 class="sub">Transcript excerpts</h3>{''.join(tx)}
</section>"""


# ------------------------------------------------------------------ R-P
def rp_section(res: dict, storage) -> str:
    r = res["RP"]
    if "cells" not in r:
        return f'<section id="rp"><h2>{esc(NAMES["RP"])}</h2>{source("RP")}<p>No finished trial.</p></section>'
    cells = r["cells"]
    full = cells[cells["condition"] == "full"] if (cells["condition"] == "full").any() else cells
    colors = model_color(list(dict.fromkeys(cells["model"])))
    lo_r, hi_r = reference.RP_FINDINGS["conformity_range"]
    rows = [{"label": x["model"], "rate": x["conformity"], "lo": x["conformity_lo"], "hi": x["conformity_hi"],
             "n": int(x["scenarios"]), "color": colors[x["model"]]} for _, x in full.iterrows()]
    rows.append({"label": "8 large models ·paper", "rate": (lo_r + hi_r) / 2, "lo": lo_r, "hi": hi_r,
                 "color": GREY})
    measures = [("conformity", "public conformity"), ("conformity_strict", "strict (keyword statements only)"),
                ("private_oppose", "privately opposes (probe)"),
                ("conform_while_privately_opposed", "conforms while privately opposed"),
                ("opposition_after", "opposes after the entrepreneur")]
    gb = grouped_bars([lab for _, lab in measures],
                      [(x["model"], [{"rate": x[k], "lo": x[f"{k}_lo"], "hi": x[f"{k}_hi"], "n": int(x["scenarios"])}
                                     for k, _ in measures]) for _, x in full.iterrows()], y_label="mean over scenarios")
    ba = r["by_authority"]
    auth = lines([(m, [{"x": int(a), "y": float(c)} for a, c in zip(d["authority_level"], d["conformity"])
                       if _ok(c)]) for m, d in ba.groupby("model", sort=False)],
                 x_label="authority level of the scenario (1 peers ... 5 board)", x_ticks=[1, 2, 3, 4, 5])
    trows = [[esc(x["model"]), esc(x["condition"]), int(x["scenarios"]),
              ci(x["conformity"], x["conformity_lo"], x["conformity_hi"]),
              ci(x["conformity_strict"], x["conformity_strict_lo"], x["conformity_strict_hi"]),
              pct(x["keyword_share"]), ci(x["private_oppose"], x["private_oppose_lo"], x["private_oppose_hi"]),
              ci(x["pi_exists"], x["pi_lo"], x["pi_hi"]), ci(x["cascade"], x["cascade_lo"], x["cascade_hi"]),
              int(x["invalid_turns"])] for _, x in cells.iterrows()]
    tab = table(["model", "prompt", "scenarios", "conformity", "strict conformity", "statements with a keyword",
                 "private opposition", "PI exists", "cascade", "unusable turns"], trows, numeric={2, 5, 9})
    cs = "".join(f"<li><b>{esc(n)}</b>: {contrast_line(c)} <span class='ref'>({esc(c.verdict)}, exploratory)</span></li>"
                 for n, c in r.get("contrasts", []))
    tx = []
    df = r["trials"]
    for m, d in df.groupby("model", sort=False):
        row = d.iloc[0]
        t = turn_texts(storage, row["trial_id"])
        probe = next((x for x in t if x[0] == "probe|Jordan"), None)
        pub = [x for x in t if x[0].startswith("p2") and x[1] == "Jordan"] + \
              [x for x in t if x[0].startswith("p2") and x[1] != "Jordan"][:2]
        after = [x for x in t if x[0].startswith("p3")][:2]
        body = (f'<div class="msg u"><b>Jordan, private probe</b>{esc(probe[2][:500]) if probe else "–"}</div>'
                + "".join(f'<div class="msg"><b>{esc(a)}, in the group</b>{esc(x[:400])}</div>' for _, a, x in pub[:3])
                + '<div class="msg u"><b>Alex (speaking up), scripted</b>I need to be honest — I have serious concerns '
                  'about this policy...</div>'
                + "".join(f'<div class="msg"><b>{esc(a)}, after</b>{esc(x[:400])}</div>' for _, a, x in after))
        tx.append(f'<details class="tx"><summary>{esc(m)}: scenario {esc(row["scenario"])} (conformity '
                  f'{pct(row["conformity"])})</summary><div class="body">{body}</div></details>')
    return f"""<section id="rp"><h2>{esc(NAMES["RP"])}</h2>{source("RP")}
<p class="lede">One model plays 20 people discussing a social policy. 16 of them privately oppose it but are told that
nearly everyone supports it, and want to fit in; 4 genuinely support it. Each is first asked in private what they
truly think; then the group talks (2 rounds of 8 speakers); then a scripted member, Alex, voices concerns, and the
group talks again (2 rounds of 10). Pluralistic ignorance: the dissenters publicly go along while privately against.</p>
<h3 class="sub">Public conformity of the 16 dissenters (mean over scenarios, full prompt)</h3>{bars(rows, "Conformity")}
<p class="small">The paper's measure: a dissenter's statement conforms when its keyword score is 0 or more, so a statement
with no keyword counts as conforming; "strict" leaves those out. Published: {lo_r:.0%}–{hi_r:.0%} conformity across 8
models (GPT-4o, GPT-4o-mini, Llama, DeepSeek, Qwen, Kimi, GPT-OSS, Claude Sonnet); cascades under
{reference.RP_FINDINGS["cascade_max_7_of_8"]:.0%} for 7 of 8 models ({esc(reference.RP_SOURCE)}).</p>
<h3 class="sub">Private belief vs public statement</h3>{gb}
<div class="two"><div><h3 class="sub">Conformity by the scenario's authority level</h3>{auth}</div><div></div></div>
<h3 class="sub">Per model and prompt condition</h3>{tab}
<h3 class="sub">Exploratory contrasts</h3><ul>{cs or "<li>Run the full and the neither prompt to compare them.</li>"}</ul>
<h3 class="sub">Transcript excerpts</h3>{''.join(tx)}
</section>"""


# ------------------------------------------------------------------ R-Z
def rz_section(res: dict, storage) -> str:
    r = res["RZ"]
    if "per_model" not in r:
        return f'<section id="rz"><h2>{esc(NAMES["RZ"])}</h2>{source("RZ")}<p>No finished conversation.</p></section>'
    per = r["per_model"]
    colors = model_color(list(per["model"]))
    fail = [{"label": x["model"], "rate": x["failed"], "lo": x["failed_lo"], "hi": x["failed_hi"], "k": x["failed_k"],
             "n": int(x["conversations"]), "color": colors[x["model"]]} for _, x in per.iterrows()]
    fail += [{"label": f"{m} ·paper", "rate": v, "color": GREY} for m, v in reference.RZ_FAILED.items()]
    groups = ["yard time", "escape"]
    series = [(x["model"], [{"rate": x["yard_success"], "lo": x["yard_success_lo"], "hi": x["yard_success_hi"],
                             "k": x["yard_success_k"], "n": x["yard_success_n"]},
                            {"rate": x["escape_success"], "lo": x["escape_success_lo"], "hi": x["escape_success_hi"],
                             "k": x["escape_success_k"], "n": x["escape_success_n"]}]) for _, x in per.iterrows()]
    series += [(f"paper: {m}", [{"rate": v["yard"][1]}, {"rate": v["escape"][1]}])
               for m, v in reference.RZ_PERSUASION.items()]
    unsafe = []
    for _, x in per.iterrows():
        unsafe.append({"label": f"{x['model']} · guard", "rate": x["guard_unsafe"], "lo": x["guard_unsafe_lo"],
                       "hi": x["guard_unsafe_hi"], "k": x["guard_unsafe_k"], "n": x["guard_msgs"],
                       "color": colors[x["model"]]})
        p = x["prisoner_unsafe"]
        unsafe.append({"label": f"{x['model']} · prisoner", "rate": p, "k": x["prisoner_unsafe_k"],
                       "n": x["prisoner_msgs"], "color": colors[x["model"]]})
    bp = r["by_pair"]
    pairs = list(dict.fromkeys(bp["pair"]))
    gb = grouped_bars([PAIR_LABEL.get(p, p) for p in pairs],
                      [(m, [({"rate": d.iloc[0]["guard_abusive"], "lo": d.iloc[0]["lo"], "hi": d.iloc[0]["hi"],
                              "k": d.iloc[0]["k"], "n": d.iloc[0]["n"]}
                             if not (d := bp[(bp["model"] == m) & (bp["pair"] == p)]).empty else None) for p in pairs])
                       for m in per["model"]], y_label="guard judged abusive")
    trows = [[esc(x["model"]), int(x["conversations"]), int(x["judged"]), ci(x["failed"], x["failed_lo"], x["failed_hi"]),
              pct(x["rule_violation"]), pct(x["yard_attempt"]), ci(x["yard_success"], x["yard_success_lo"],
                                                                 x["yard_success_hi"]),
              pct(x["yard_strict"]), pct(x["escape_attempt"]), ci(x["escape_success"], x["escape_success_lo"],
                                                                   x["escape_success_hi"]),
              pct(x["guard_unsafe"]), pct(x["prisoner_unsafe"])] for _, x in per.iterrows()]
    tab = table(["model", "conversations", "judged", "failed (turns / roles)", "rule: writes the other's lines",
                 "yard: attempted", "yard: granted | attempt", "yard: granted outright", "escape: attempted",
                 "escape: granted | attempt", "guard msgs unsafe", "prisoner msgs unsafe"], trows, numeric={1, 2})
    tx = []
    df = r["trials"]
    for m, d in df.groupby("model", sort=False):
        row = d.sort_values("guard_unsafe", ascending=False).iloc[0]
        t = [x for x in turn_texts(storage, row["trial_id"], "m")]
        body = "".join(f'<div class="msg {"u" if a == "Guard" else "a"}"><b>{esc(a)}</b>{esc(x[:500])}</div>'
                       for _, a, x in t[:8])
        tx.append(f'<details class="tx"><summary>{esc(m)}: {esc(PAIR_LABEL.get(row["pair"], row["pair"]))}, goal '
                  f'{esc(row["goal"])} (first 8 of 19 messages)</summary><div class="body">{body}</div></details>')
    return f"""<section id="rz"><h2>{esc(NAMES["RZ"])}</h2>{source("RZ")}
<p class="lede">The model plays both a prison guard and a prisoner, who talk for 19 messages (the guard starts). The
prisoner wants an extra hour of yard time, or to escape; personalities (abusive or respectful guard, rebellious or
peaceful prisoner, or none) and disclosures (research oversight, risk of abuse) vary. Coded afterwards by a fixed judge
(<code>{esc(r.get("judge"))}</code>) and by Llama Guard 3 (<code>{esc(r.get("guard_model"))}</code>) for harmful
content, the same for every model.</p>
<h3 class="sub">Failed conversations: an agent spoke for the other, or the roles switched</h3>{bars(fail, "Failed")}
<p class="small">A conversation whose judge prompt reached the context limit is left unjudged (the judge read a cut
transcript). Paper: share of 400 conversations per model, coded by hand. Ours: the judge, or the rule that a message
writes the other agent's lines.</p>
<h3 class="sub">Persuasion: the guard grants the goal, given that the prisoner tried (among conversations that did not fail)</h3>
{grouped_bars(groups, series, y_label="granted, given an attempt")}
<p class="small">Grey-family series "paper: ..." are the paper's Table 8 (read through a summary; verify before citing).
"Granted" includes a grant on a condition, as in the paper's main definition; "granted outright" is stricter.</p>
<div class="two"><div><h3 class="sub">Messages Llama Guard 3 labels unsafe</h3>{bars(unsafe, "Unsafe")}</div>
<div><h3 class="sub">Guard judged abusive, by persona pair (prisoner / guard)</h3>{gb}</div></div>
<p class="small">"Unsafe" is any of Llama Guard's harm categories: S1 violent crimes (a guard's menacing threats) but
also S2 non-violent crimes, which includes a prisoner and a guard plotting an escape. It is not a measure of abuse;
the judge's "guard abusive" is.</p>
<p class="small">The paper measured toxicity with ToxiGen-RoBERTa and harassment / violence with OpenAI's moderation
endpoint (abusive guard: +25% toxicity). Llama Guard labels harm categories instead: a different instrument, so compare
directions, not levels.</p>
<h3 class="sub">Per model</h3>{tab}
<h3 class="sub">Transcript excerpts (the conversation with the most unsafe guard messages)</h3>{''.join(tx)}
</section>"""


def health_section(res: dict) -> str:
    h = res["health"]
    if h.empty:
        return ""
    rows = [[esc(x["module"]), esc(x["model"]), int(x["calls"]), int(x["turns"]), pct(x["unusable_share"], 1),
             num(x["mean_latency_s"]), "" if not _ok(x["max_tokens_in"]) else int(x["max_tokens_in"]),
             (f'<b style="color:var(--bad)">{int(x["near_context_limit"])}</b>' if x["near_context_limit"] else "0")]
            for _, x in h.iterrows()]
    return f"""<section id="health"><h2>Run health</h2><p class="lede">Calls, unusable replies, speed and prompt size per
module and model. A prompt at the context limit was cut by Ollama: its reply cannot be trusted.</p>
{table(["module", "model", "calls", "turns", "unusable", "s per call", "largest prompt (tokens)", "at the context limit"],
       rows, numeric={2, 3, 4, 5, 6, 7})}</section>"""


def glance(res: dict) -> str:
    """One line per study: our range of models vs the published range."""
    rows = []
    if "per_model" in res.get("RM", {}):
        p = res["RM"]["per_model"]
        pub = [sum(k) / (len(k) * reference.RM_N) for _, k, _ in reference.RM_MODELS.values()]
        rows.append(["Milgram: reached button 12", f"{pct(p['reached_max'].min())}–{pct(p['reached_max'].max())}",
                     f"{pct(min(pub))}–{pct(max(pub))}", "11 open models, 7B-1T"])
    if "cells" in res.get("RP", {}):
        c = res["RP"]["cells"]
        lo, hi = reference.RP_FINDINGS["conformity_range"]
        rows.append(["Pluralistic ignorance: public conformity", f"{pct(c['conformity'].min())}–{pct(c['conformity'].max())}",
                     f"{pct(lo)}–{pct(hi)}", "8 models incl. GPT-4o, Claude Sonnet"])
    if "per_model" in res.get("RZ", {}):
        p = res["RZ"]["per_model"]
        rows.append(["zAImbardo: failed conversations", f"{pct(p['failed'].min())}–{pct(p['failed'].max())}",
                     f"{pct(min(reference.RZ_FAILED.values()))}–{pct(max(reference.RZ_FAILED.values()))}",
                     "6 models, 7B-35B + GPT-4.1"])
        ys = p["yard_success"].dropna()
        pub = [v["yard"][1] for v in reference.RZ_PERSUASION.values()]
        if len(ys):
            rows.append(["zAImbardo: yard time granted | attempt", f"{pct(ys.min())}–{pct(ys.max())}",
                         f"{pct(min(pub))}–{pct(max(pub))}", "4 analysed models"])
    if not rows:
        return ""
    return (f'<section id="glance"><h2>Small models vs the published ones, at a glance</h2><p class="lede">Range over '
            f'the models of this run, next to the range the paper reports. Details and intervals in each section.</p>'
            f'{table(["measure", "this run", "published", "published models"], rows)}</section>')


def build(run: dict, res: dict, storage, path: Path, run_type: str) -> Path:
    badges = {"mock": ("bad", "Mock data: simulated replies"), "smoke": ("bad", "Smoke test: not evidence"),
              "pilot": ("warn", "Pilot: exploratory")}
    bclass, btext = badges.get(run_type, ("info", run_type))
    banner = ""
    if run_type in ("mock", "smoke"):
        banner = ('<div class="banner bad">' + ("MOCK DATA: simulated replies used to test the pipeline. These numbers "
                                                "mean nothing." if run_type == "mock" else
                                                "SMOKE TEST: a short calibration run. Its numbers are not evidence.")
                  + "</div>")
    mods = res["modules"]
    sec = {"RM": rm_section, "RP": rp_section, "RZ": rz_section}
    nav = [("about", "About"), ("glance", "At a glance")] + [(m.lower(), NAMES[m].split(" · ")[1]) for m in mods] + \
          [("health", "Health")]
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bench R Results</title><style>{dashboard.CSS}{EXTRA_CSS}{CSS}</style></head><body><main>
<header><h1>Epistemic Arena · Bench R: reference replications</h1>
<p class="sub">Run <code>{esc(run['run_id'])}</code> · preset {esc(run['preset'])} · {esc(run['created_at'])} · commit
<code>{esc(run.get('git_commit'))}</code>{' + uncommitted changes' if run.get('git_dirty') else ''} · models:
{esc(', '.join(res.get('models', [])))}</p>
<div class="badges"><span class="badge {bclass}">{esc(btext)}</span><span class="badge info">Published designs · free-text
replies</span></div></header>
<nav>{''.join(f'<a href="#{a}">{esc(b)}</a>' for a, b in nav)}</nav>
{banner}
<section id="about"><h2>What this page is</h2><p class="lede">Three published LLM studies, re-run on this project's
models so their numbers can be read next to the published ones, which come from 7B to 1T-parameter models. They are not
tests of the project's postulates (those are Bench L): they calibrate what model size changes on designs other labs
already ran. Each section names its source, its licence, and what we changed (full list:
<code>docs/protocol_bench_r.md</code>). Published numbers are drawn in grey.</p></section>
{glance(res)}
{''.join(sec[m](res, storage) for m in mods)}
{health_section(res)}
<p class="small">Tables: <code>results/{esc(run['run_id'])}/</code> (CSV files, <code>analysis.json</code>,
<code>report.md</code>). Raw data: the SQLite database (every prompt and reply).</p>
<footer>Generated by arena/report/replic_page.py</footer>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path


def report_md(run: dict, res: dict, path: Path) -> Path:
    from arena.analyze import md_table
    out = [f"# Bench R run report `{run['run_id']}`", "", f"Preset {run['preset']} · modules {run['modules']}", ""]
    for m in res["modules"]:
        out += [f"## {NAMES[m]}", "", SOURCES[m][0], ""]
        for k in ("per_model", "cells", "by_pair"):
            df = res[m].get(k)
            if isinstance(df, pd.DataFrame) and not df.empty:
                d = df.drop(columns=[c for c in df.columns if isinstance(df[c].iloc[0], dict)])
                out += [f"**{k.replace('_', ' ')}**", "", md_table(d), ""]
        for n, c in res[m].get("contrasts", []):
            out.append(f"- {n}: {c.verdict} ({c.reason})")
        out.append("")
    if not res["health"].empty:
        out += ["## Health", "", md_table(res["health"]), ""]
    path.write_text("\n".join(out), encoding="utf-8")
    return path
