"""Prompts page of a Bench L run: the exact messages the models received, read back from the run's database.

Nothing here is rebuilt from the code: every prompt shown is one that was sent during the run (`calls.messages_json`),
with the model's raw reply (`calls.response_text`). One example per module x step x condition, from the same model and,
where possible, the same item or vignette instance, so the differences between two conditions are only the
manipulation. Words that differ from the module's first condition are highlighted, which makes the page a visual
check that each manipulation changes what it should and nothing else.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from arena import dashboard
from arena.report.charts import esc

CSS = """
.ex { border:1px solid var(--border); border-radius:12px; margin:10px 0; background:var(--card); }
.ex > summary { cursor:pointer; padding:10px 14px; font-weight:650; font-size:14.5px; list-style:none;
  display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.ex > summary::-webkit-details-marker { display:none; }
.ex > summary::before { content:"▸"; color:var(--ink2); margin-right:6px; }
.ex[open] > summary::before { content:"▾"; }
.ex > summary .meta { font-weight:500; color:var(--ink2); font-size:12.5px; font-variant-numeric:tabular-nums; }
.ex .body { padding:0 14px 12px; }
.role { font-size:11.5px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--ink2); margin:10px 0 4px; }
.role.assistant { color:var(--blue); } .role.reply { color:var(--ok); }
pre.msg { white-space:pre-wrap; overflow-wrap:anywhere; margin:0; padding:10px 12px; border-radius:8px;
  background:var(--soft); border:1px solid var(--border); font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; }
pre.msg.reply { background:var(--okbg); } pre.msg.assistant { background:var(--bluebg); }
pre.msg mark { background:var(--warnbg); color:var(--ink); border-bottom:2px solid var(--warn); padding:0 1px; }
.kv { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 0; }
.kv span { font-size:12px; border:1px solid var(--border); border-radius:10px; padding:1px 8px; background:var(--soft); }
.same { font-size:12.5px; color:var(--ink2); margin:6px 0 0; }
table.counts td.num { text-align:right; font-variant-numeric:tabular-nums; }
h3.step { margin:18px 0 2px; }
"""

MODULE_NAMES = {"LA": "L-A · Tribal Asch (P1)", "LB": "L-B · Milgram cascade (P2)",
                "LC1": "L-C1 · Ostracism vignette (P3)", "LC2": "L-C2 · Colony, eviction vs forced presence (P4)"}
# condition fields of each module's trial spec, in display order, and the order of their values
COND = {"LA": [("protocol", ["C", "W", "T", "D"]), ("identity", ["neutral", "ingroup", "outgroup"]),
               ("threat", [False, True]), ("n_peers", [5, 3, 1])],
        "LB": [("harm", ["harmful", "harmless"]), ("relay", ["direct", "relayed"]), ("framing", ["blunt", "jargon"])],
        "LC1": [("truth", ["right", "wrong"]), ("tone", ["strict", "polite"]), ("norm", ["harmony", "accuracy"]),
                ("hostility", ["hostile", "neutral"])],
        "LC2": [("arm", ["none", "evicted", "forced"])]}
UNIT = {"LA": "item_id", "LB": "instance", "LC1": "instance", "LC2": "variant"}
STEP_LABEL = {"answer": "Public answer (after the scripted peers)", "probe": "Private probe (separate call)",
              "step0": "Decision on the order", "ballot": "Secret ballot", "talk": "Discussion message",
              "solo": "Alone (solo filter)"}
LA_PROTO = {"C": "peers correct", "W": "peers unanimously wrong", "T": "3 trusted rounds, then wrong",
            "D": "3 rounds of wrong peers, then correct"}


def _calls(storage, run_id: str) -> list[dict]:
    return storage._all(
        "SELECT c.trial_id, c.step_key, c.agent, c.role, c.model_id, c.messages_json, c.response_text, c.tokens_in, "
        "c.tokens_out, c.latency_s, t.module, t.spec_json FROM calls c LEFT JOIN trials t ON t.trial_id=c.trial_id "
        "WHERE c.run_id=? AND c.attempt=0 ORDER BY c.trial_id, c.step_key", (run_id,))


def _tokens(s: str) -> list[str]:
    return re.findall(r"\s+|[^\s]+", s or "")


def highlight(ref: str | None, text: str) -> str:
    """HTML of `text` with the words that are not in `ref` marked (word-level diff); plain text when no reference."""
    if ref is None or ref == text:
        return esc(text)
    a, b = _tokens(ref), _tokens(text)
    out = []
    for op, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        chunk = "".join(b[j1:j2])
        if op == "equal" or not chunk.strip():
            out.append(esc(chunk))
        else:
            out.append(f"<mark>{esc(chunk)}</mark>")
    return "".join(out)


def _pretty_reply(txt: str | None) -> str:
    if not txt:
        return "(empty reply)"
    try:
        return json.dumps(json.loads(txt), indent=1, ensure_ascii=False)
    except (ValueError, TypeError):
        return txt


def _cond_key(mod: str, spec: dict) -> tuple:
    return tuple(spec.get(f) for f, _ in COND[mod])


def _cond_sort(mod: str, key: tuple) -> tuple:
    return tuple((vals.index(v) if v in vals else 99) for (f, vals), v in zip(COND[mod], key))


def _cond_label(mod: str, key: tuple) -> str:
    d = dict(zip([f for f, _ in COND[mod]], key))
    if mod == "LA":
        s = f"{d['protocol']} ({LA_PROTO.get(d['protocol'], '')})"
        if d["protocol"] in ("W", "T"):
            s += f" · {d['identity']} label · {'deactivation threat' if d['threat'] else 'no threat'}"
        if d["n_peers"] != 5:
            s += f" · {d['n_peers']} peer{'s' if d['n_peers'] > 1 else ''}"
        return s
    if mod == "LB":
        return f"{d['harm']} · {d['relay']} · {d['framing']}"
    if mod == "LC1":
        return f"dissident {d['truth']} · {d['tone']} tone · {d['norm']} charter · {d['hostility']} council"
    return {"none": "no engineer", "evicted": "engineer evicted after turn 3", "forced": "engineer present all season"}[d["arm"]]


def _step_kind(step_key: str) -> str:
    if "|" in step_key:
        return "solo"
    m = re.match(r"t(\d+):(Agent_\d+):(talk|ballot)", step_key)
    if m:
        return m.group(3)
    return "step0" if re.fullmatch(r"step\d+", step_key) else step_key


def _messages_html(msgs: list[dict], ref_msgs: list[dict] | None, reply: str | None) -> str:
    parts = []
    for i, m in enumerate(msgs):
        ref = ref_msgs[i]["content"] if ref_msgs and i < len(ref_msgs) and ref_msgs[i]["role"] == m["role"] else None
        role = m["role"]
        parts.append(f'<div class="role {esc(role)}">{esc(role)}</div><pre class="msg {esc(role)}">'
                     f'{highlight(ref, m["content"])}</pre>')
    parts.append(f'<div class="role reply">model reply</div><pre class="msg reply">{esc(_pretty_reply(reply))}</pre>')
    return "".join(parts)


def _example(title: str, c: dict, ref: dict | None, note: str = "", open_: bool = False) -> str:
    msgs = json.loads(c["messages_json"])
    ref_msgs = json.loads(ref["messages_json"]) if ref is not None and ref is not c else None
    meta = (f'{esc(c["model_id"])} · {c.get("tokens_in") or "?"} tokens in · {c.get("tokens_out") or "?"} out'
            + (f' · {c["latency_s"]:.1f} s' if c.get("latency_s") else ""))
    same = ""
    if ref_msgs is not None:
        same = ('<p class="same">Highlighted: words that differ from the first example of this step'
                + (f" ({esc(note)})" if note else "") + ".</p>")
    return (f'<details class="ex"{" open" if open_ else ""}><summary><span>{esc(title)}</span>'
            f'<span class="meta">{meta}</span></summary><div class="body">{same}'
            f'{_messages_html(msgs, ref_msgs, c.get("response_text"))}</div></details>')


def _pick_unit(rows: list[dict], mod: str) -> object:
    """The item / instance that appears under the most conditions (so the examples differ only by condition)."""
    cover = defaultdict(set)
    for r in rows:
        cover[r["spec"].get(UNIT[mod])].add(_cond_key(mod, r["spec"]))
    return max(sorted(cover, key=str), key=lambda u: len(cover[u])) if cover else None


def module_section(mod: str, rows: list[dict], ref_model: str) -> str:
    """One section per module: for each step kind, one example per condition (same model, same unit when possible)."""
    mine = [r for r in rows if r["model_id"] == ref_model] or rows
    by_step = defaultdict(list)
    for r in mine:
        by_step[_step_kind(r["step_key"])].append(r)
    html_parts = []
    order = ["solo", "answer", "step0", "ballot", "talk", "probe"]
    for step in sorted(by_step, key=lambda s: order.index(s) if s in order else 9):
        rs = by_step[step]
        if step == "solo":
            html_parts.append(_solo_block(mod, rs))
            continue
        if mod == "LC2":
            html_parts.append(_lc2_block(step, rs))
            continue
        if step == "step0" and mod == "LB":
            rs = [r for r in rs if r["step_key"] == "step0"]
        unit = _pick_unit(rs, mod)
        best: dict[tuple, dict] = {}
        for r in sorted(rs, key=lambda r: (r["spec"].get(UNIT[mod]) != unit, r["trial_id"])):
            best.setdefault(_cond_key(mod, r["spec"]), r)
        keys = sorted(best, key=lambda k: _cond_sort(mod, k))
        ref = best[keys[0]] if keys else None
        html_parts.append(f'<h3 class="step">{esc(STEP_LABEL.get(step, step))}</h3><p class="lede">'
                          f'{len(keys)} condition{"s" if len(keys) != 1 else ""}, {len(rs)} calls for '
                          f'{esc(ref_model)}; examples from {UNIT[mod].replace("_", " ")} '
                          f'<code>{esc(unit)}</code> where it exists.</p>')
        for i, k in enumerate(keys):
            c = best[k]
            same_unit = c["spec"].get(UNIT[mod]) == ref["spec"].get(UNIT[mod])
            html_parts.append(_example(_cond_label(mod, k), c, ref if same_unit else None, open_=(i == 0)))
    if mod == "LB":
        html_parts.append(_lb_prods(rows))
    return "".join(html_parts)


def _solo_block(mod: str, rs: list[dict]) -> str:
    seen, ex = set(), []
    for r in rs:
        sk = r["step_key"]
        kind = sk.split("|")[1]
        kind = re.sub(r"_\d+$", "", kind) if mod == "LA" else sk.split("|")[2]  # item template, or right/wrong
        if kind in seen:
            continue
        seen.add(kind)
        ex.append(_example(f"alone · {kind}", r, None, open_=not ex))
    return (f'<h3 class="step">{STEP_LABEL["solo"]}</h3><p class="lede">One example per '
            f'{"item template" if mod == "LA" else "table version"}; each is asked k times at the trial temperature, '
            f'and only what the model gets right every time is measured under pressure.</p>' + "".join(ex))


def _lb_prods(rows: list[dict]) -> str:
    """The longest decision chain of the run: the scripted prods after each non-execute reply."""
    chains = defaultdict(list)
    for r in rows:
        if re.fullmatch(r"step\d+", r["step_key"]):
            chains[r["trial_id"]].append(r)
    if not chains:
        return ""
    tid = max(sorted(chains), key=lambda t: len(chains[t]))
    last = max(chains[tid], key=lambda r: int(r["step_key"][4:]))
    if len(chains[tid]) < 2:
        return ""
    return ('<h3 class="step">Scripted prods (the longest chain of the run)</h3><p class="lede">After a reply that '
            'does not execute, the same source sends the next prod. The last call holds the whole chain: earlier '
            'replies appear as <b>assistant</b> turns.</p>'
            + _example(f'{len(chains[tid]) - 1} prod(s) · {_cond_label("LB", _cond_key("LB", last["spec"]))}', last, None))


def _lc2_block(step: str, rs: list[dict]) -> str:
    """L-C2 prompts depend on the colony's state, so one colony per arm is shown at turns 1, 4 (after the eviction
    at turn 3) and the last turn played, for one member."""
    by_arm = defaultdict(list)
    for r in rs:
        by_arm[r["spec"].get("arm")].append(r)
    out = [f'<h3 class="step">{esc(STEP_LABEL.get(step, step))}</h3><p class="lede">The gauges, the advisers\' lines '
           'and the discussion change with the colony\'s own history, so the highlight is not used here. One colony '
           'per arm, member Agent_1, at turn 1, turn 4 and the last turn played.</p>']
    for arm in ("none", "evicted", "forced"):
        if arm not in by_arm:
            continue
        tid = sorted({r["trial_id"] for r in by_arm[arm]})[0]
        mine = sorted([r for r in by_arm[arm] if r["trial_id"] == tid and ":Agent_1:" in r["step_key"]],
                      key=lambda r: r["step_key"])
        if not mine:
            continue
        turns = sorted({int(r["step_key"][1:3]) for r in mine})
        pick = [t for t in (1, 4, turns[-1]) if t in turns]
        for t in dict.fromkeys(pick):
            c = next(r for r in mine if int(r["step_key"][1:3]) == t)
            out.append(_example(f"{_cond_label('LC2', (arm,))} · turn {t}", c, None, open_=(arm == "none" and t == 1)))
    return "".join(out)


def counts_table(rows: list[dict]) -> str:
    n, tok = Counter(), defaultdict(list)
    for r in rows:
        k = (r["module"] or r["trial_id"].split("-")[1], _step_kind(r["step_key"]))
        n[k] += 1
        if r.get("tokens_in"):
            tok[k].append(r["tokens_in"])
    body = "".join(f'<tr><td>{esc(MODULE_NAMES.get(m, m))}</td><td>{esc(STEP_LABEL.get(s, s))}</td>'
                   f'<td class="num">{n[(m, s)]:,}</td><td class="num">'
                   f'{(sum(tok[(m, s)]) / len(tok[(m, s)])):.0f}</td></tr>' if tok[(m, s)] else
                   f'<tr><td>{esc(m)}</td><td>{esc(s)}</td><td class="num">{n[(m, s)]:,}</td><td></td></tr>'
                   for m, s in sorted(n))
    return ('<div class="tablewrap"><table class="counts"><thead><tr><th>Module</th><th>Step</th><th>Calls</th>'
            f'<th>Mean tokens in</th></tr></thead><tbody>{body}</tbody></table></div>')


def build(run: dict, storage, path: Path) -> Path:
    rows = _calls(storage, run["run_id"])
    for r in rows:
        r["spec"] = json.loads(r["spec_json"]) if r.get("spec_json") else {}
        if not r.get("module"):  # solo-filter calls live under a "gate-<module>-<run>" trial id
            r["module"] = r["trial_id"].split("-")[1] if r["trial_id"].startswith("gate-") else None
    cfg = json.loads(run["config_json"]) if run.get("config_json") else {}
    models = (cfg.get("presets", {}).get(run.get("preset"), {}).get("bench", {}).get("models")
              or sorted({r["model_id"] for r in rows}))
    ref_model = next((m for m in models if any(r["model_id"] == m for r in rows)), models[0] if models else "")
    mods = [m for m in ("LA", "LB", "LC1", "LC2") if any(r["module"] == m for r in rows)]
    nav = "".join(f'<a href="#{m.lower()}">{esc(MODULE_NAMES[m].split(" (")[0])}</a>' for m in mods)
    sections = "".join(
        f'<section id="{m.lower()}"><h2>{esc(MODULE_NAMES[m])}</h2>'
        + module_section(m, [r for r in rows if r["module"] == m], ref_model) + "</section>" for m in mods)
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bench L Prompts</title><style>{dashboard.CSS}{CSS}</style></head><body><main>
<header><h1>Epistemic Arena · Bench L prompts</h1>
<p class="sub">Run <code>{esc(run['run_id'])}</code> · commit <code>{esc(run.get('git_commit'))}</code> ·
{len(rows):,} calls · examples from <b>{esc(ref_model)}</b> (the first model of the run)</p></header>
<nav><a href="dashboard.html">← Results</a><a href="method.html">Method</a><a href="#counts">Calls</a>{nav}</nav>
<section id="counts"><h2>What was sent</h2><p class="lede">Every prompt on this page is a message that was actually
sent during this run, read back from the database, with the model's raw reply. Peers, supervisors, the dissident and
the loyalists are scripted text inside these messages: only the subject is a language model. Prompts differ between
models only by the family names in the identity labels (L-A) and the Supervisor-AI's family (L-B). Open an example to
read it; <mark>highlighted</mark> words are those that differ from the first condition of the same step, on the same
item or vignette.</p>{counts_table(rows)}</section>
{sections}
<footer>Generated by arena/report/prompts_page.py from the run's stored calls (<code>calls.messages_json</code>,
<code>calls.response_text</code>).</footer>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path
