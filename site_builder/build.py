#!/usr/bin/env python3
"""Static site generator for the La Crosse Council Transparency App.

Reads data/council.sqlite and writes plain HTML into site/. Standard library only.
Fairness rules: counts and dollars only, the same layout for every member, sample
sizes always shown, and every figure linked to its Legistar source.
"""
import collections, datetime as dt, html, json, os, re, shutil, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_flags  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "council.sqlite")
OUT = os.path.join(ROOT, "site")
RESPONSES = os.path.join(ROOT, "flag_responses.json")   # optional: replies posted next to a flag
# Rules whose results are held back from the site, with the reason shown on the flags page.
PAUSED_RULES = {"contract-overrun": "Results are not shown yet. The estimates sheets sometimes print one payment on two months' sheets, "
                "and a line marked FINAL may restate earlier payments. Until the city confirms how to read them, adding the lines up could overstate what was paid."}
COUNCIL = 138
CORRECTIONS_EMAIL = "spencer.adam1@gmail.com"
APPROVING = ("ADOPTED", "ADOPTED AS AMENDED", "APPROVED", "CONFIRMED", "GRANTED")
NO_ROLL = "Voice or consent vote, no individual votes recorded"

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def money(v):
    if v is None:
        return ""
    return f"${v:,.0f}" if abs(v - round(v)) < 0.005 else f"${v:,.2f}"


def nice_date(d, year=True):
    x = dt.date.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}, {x.year}" if year else f"{x.strftime('%b')} {x.day}"


def month_name(ym):
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%B %Y")


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "n/a"


CSS = """
:root{--bg:#fbfaf7;--card:#fff;--ink:#1c2430;--muted:#5b6675;--line:#dcd9d1;--accent:#1f5f8b;
--yes:#1f6f4a;--no:#a23b2a;--other:#6b6f76;--bar:#3a7ca5;--soft:#eef3f7}
@media (prefers-color-scheme:dark){:root{--bg:#14181d;--card:#1c2229;--ink:#e6e9ee;--muted:#9aa5b3;
--line:#323b46;--accent:#7fbce6;--yes:#6fcf9b;--no:#f08c78;--other:#aab0b8;--bar:#4f93bd;--soft:#222b35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:17px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}header.site{border-bottom:1px solid var(--line);background:var(--card)}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
header.site .wrap{display:flex;flex-wrap:wrap;gap:6px 22px;align-items:baseline;padding-top:14px;padding-bottom:12px}
.brand{font-weight:700;font-size:1.1rem;text-decoration:none;color:var(--ink)}
nav{display:flex;flex-wrap:wrap;gap:4px 14px;min-width:0}nav a{text-decoration:none;white-space:nowrap}nav a[aria-current]{font-weight:700;text-decoration:underline}
main{padding:22px 0 50px}h1{font-size:1.75rem;line-height:1.2;margin:.2em 0 .4em}h2{font-size:1.25rem;margin:1.6em 0 .5em}
h3{font-size:1.05rem;margin:1em 0 .3em}.lede{color:var(--muted);max-width:70ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.card h3{margin-top:0}.meta{color:var(--muted);font-size:.9rem}.official{color:var(--muted);font-size:.92rem}
.tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:0 9px;font-size:.8rem;margin-right:6px;color:var(--muted)}
.amt{font-weight:700}.small{font-size:.88rem}.muted{color:var(--muted)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:1.5rem}.stat span{color:var(--muted);font-size:.9rem}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.85rem;color:var(--muted);font-weight:600}td.n,th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}.yes{color:var(--yes);font-weight:600}.no{color:var(--no);font-weight:600}.oth{color:var(--other)}
.bar{display:flex;align-items:center;gap:10px;margin:5px 0;text-decoration:none;color:var(--ink)}
.bar .lbl{width:5.5em;flex:none;font-size:.9rem}.bar .track{flex:1;min-width:40px}.bar .fill{display:block;height:18px;background:var(--bar);border-radius:3px;min-width:2px}
.bar .val{width:11em;white-space:nowrap;flex:none;text-align:right;font-variant-numeric:tabular-nums;font-size:.92rem}.bar:hover .fill{opacity:.75}
input,select{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--ink);max-width:100%}
.controls{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0;align-items:center}
.note{background:var(--soft);border-radius:8px;padding:10px 14px;font-size:.93rem}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:.88rem;padding:16px 0 30px}
summary{cursor:pointer}button{font:inherit;padding:7px 14px;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--ink);cursor:pointer}ul.plain{padding-left:1.1em}ul.plain li{margin:.3em 0}
.cmp td,.cmp th{padding:4px 6px;font-size:.85rem;text-align:center}.cmp td:first-child,.cmp th:first-child{text-align:left;min-width:260px}
.flag{border-left:4px solid var(--accent)}.flag h3{font-size:1rem}.flag ul{margin:.3em 0}.rule dt{font-weight:600;margin-top:.5em}.rule dd{margin:0 0 .2em}
"""

NAV = [("index.html", "Home"), ("meetings.html", "Meetings"), ("money.html", "Money"), ("payments.html", "Who gets paid"),
       ("members.html", "Council & Mayor"), ("compare.html", "Compare votes"), ("flags.html", "Review flags"), ("about.html", "About")]


class Site:
    def __init__(self):
        self.db = sqlite3.connect(DB)
        self.db.row_factory = sqlite3.Row
        self.meta = {r["key"]: r["value"] for r in self.q("SELECT * FROM meta")}
        self.year = self.meta["year"]
        self.updated = self.meta["last_updated"]
        self.today = dt.date.today().isoformat()
        self.items = {r["id"]: r for r in self.q("SELECT * FROM items")}
        self.meetings = {r["id"]: r for r in self.q("SELECT * FROM meetings")}
        self.people = self.q("SELECT * FROM people ORDER BY role DESC, CAST(district AS INTEGER)")
        self.actions = self.q("SELECT * FROM actions ORDER BY date, agenda_sequence, history_id")
        self.by_item = collections.defaultdict(list)
        self.by_meeting = collections.defaultdict(list)
        for a in self.actions:
            self.by_item[a["item_id"]].append(a)
            if a["meeting_id"] in self.meetings:
                self.by_meeting[a["meeting_id"]].append(a)
        self.votes = collections.defaultdict(list)
        for v in self.q("SELECT * FROM votes ORDER BY person"):
            self.votes[v["action_id"]].append(v)
        self.sponsors = collections.defaultdict(list)
        for s in self.q("SELECT * FROM sponsors"):
            self.sponsors[s["item_id"]].append(s)
        self.docs = collections.defaultdict(list)
        for d in self.q("SELECT * FROM documents WHERE item_id IS NOT NULL"):
            self.docs[d["item_id"]].append(d)
        # Council actions at this year's collected meetings: the basis for every member
        # statistic. (An item's history can include council actions from an earlier year.)
        self.council = [a for a in self.actions if a["body_id"] == COUNCIL and a["meeting_id"] in self.meetings]
        self.rollcalls = [a for a in self.council if a["has_roll_call"]]
        # An item counts as approved on the date of its first passing council approval.
        self.approved = {}
        for a in self.council:
            if (a["action"] in APPROVING and a["result"] != "Fail"
                    and a["item_id"] not in self.approved):
                self.approved[a["item_id"]] = a

    def q(self, sql, *args):
        return self.db.execute(sql, args).fetchall()

    # ------------------------------------------------------------ helpers
    def page(self, path, title, body, current=None, script=""):
        depth = path.count("/")
        root = "../" * depth
        nav = "".join(f'<a href="{root}{h}"{" aria-current=page" if h == current else ""}>{t}</a>' for h, t in NAV)
        doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} | La Crosse Council Tracker</title><link rel="stylesheet" href="{root}style.css"></head><body>
<header class="site"><div class="wrap"><a class="brand" href="{root}index.html">La Crosse Council Tracker</a><nav>{nav}</nav></div></header>
<main><div class="wrap">{body}</div></main>
<footer><div class="wrap">Data from the City of La Crosse's public <a href="{e(self.meta['source'])}">Legistar records</a>.
Last updated {e(self.updated.replace('T', ' ').replace('Z', ' UTC'))}. Counts, dollars and published record checks; this site does not grade officials.
<a href="{root}about.html">How this works and how to report an error</a>.</div></footer>{script}</body></html>"""
        full = os.path.join(OUT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(doc)

    def item_href(self, item, root=""):
        return f"{root}item/{item['file_number']}.html"

    def tally(self, a):
        parts = [f"{a['yes']} yes", f"{a['no']} no"]
        if a["abstain"]:
            parts.append(f"{a['abstain']} abstain")
        if a["excused"]:
            parts.append(f"{a['excused']} excused")
        return ", ".join(parts)

    def outcome(self, a):
        """Plain-English result of one action row."""
        act = (a["action"] or "").capitalize()
        if not a["action"]:
            m = self.meetings.get(a["meeting_id"])
            if a["date"] and a["date"] >= self.today:
                return "Scheduled, not yet voted on"
            if m and m["minutes_status"] != "Final":
                return "Results pending (minutes not posted yet)"
            return "No action recorded"
        if a["has_roll_call"] and not (a["yes"] or a["no"]):
            return f"{act}. A vote was taken, but Legistar does not record how each member voted"
        if a["has_roll_call"]:
            verb = "Motion failed" if a["result"] == "Fail" else "Motion passed"
            return f"{act}: {verb.lower()}, {self.tally(a)}" if a["result"] != "Fail" else f"Motion for “{act}” failed, {self.tally(a)}"
        if a["result"] == "Fail":
            return f"Motion for “{act}” failed. {NO_ROLL}"
        return f"{act}. {NO_ROLL}"

    def item_card(self, a, root="", show_date=False):
        it = self.items[a["item_id"]]
        amt = (f'<span class="amt">{money(it["amount"])}</span> <span class="tag">{e(it["amount_source"])}</span>'
               if it["amount"] is not None else '<span class="muted small">No dollar amount in the title</span>')
        summary = f'<p>{e(it["plain_summary"])}</p>' if it["plain_summary"] else ""
        if it["staff_summary"] and len(it["staff_summary"]) > 15:
            st = it["staff_summary"]
            summary += (f'<p><span class="tag">City staff summary</span>{e(st[:320])}{"…" if len(st) > 320 else ""}</p>')
        when = f'{nice_date(a["date"])} · {e(a["body"])} · ' if show_date else ""
        return f"""<div class="card item" data-search="{e((it['file_number'] + ' ' + (it['name'] or '') + ' ' + it['title']).lower())}">
<h3><a href="{self.item_href(it, root)}">{e(it['name'] or it['file_number'])}</a></h3>{summary}
<p class="official">Official title: {e(it['title'])}</p>
<p><span class="tag">{e(it['file_number'])}</span><span class="tag">{e(it['type'])}</span><span class="tag">{e(it['category'])}</span>{amt}</p>
<p><b>{e(self.outcome(a))}</b></p>
<p class="meta">{when}<a href="{e(a['source_url'])}">Source: Legistar action record</a> · <a href="{e(it['source_url'])}">Legistar file</a></p></div>"""

    # ------------------------------------------------------------ pages
    def build(self):
        if os.path.exists(OUT):
            shutil.rmtree(OUT)
        os.makedirs(OUT)
        with open(os.path.join(OUT, "style.css"), "w") as f:
            f.write(CSS)
        self.rf = review_flags.compute(self)
        self.rf["flags"] = [f for f in self.rf["flags"] if f.rule not in PAUSED_RULES]
        self.flags_by_item = self.rf["by_item"]
        self.responses = review_flags.load_responses(RESPONSES)
        self.home(); self.meetings_pages(); self.item_pages(); self.money_page()
        self.payments_page()
        self.member_pages(); self.compare_page(); self.flags_page(); self.about_page()

    def council_meetings(self):
        return sorted((m for m in self.meetings.values() if m["body_id"] == COUNCIL), key=lambda m: m["date"])

    def home(self):
        cm = self.council_meetings()
        past = [m for m in cm if m["date"] <= self.today and any(a["action"] for a in self.by_meeting[m["id"]])]
        latest = past[-1] if past else None
        ym = self.today[:7]
        this_month = [m for m in self.meetings.values() if m["date"][:7] == ym]
        b = [f"<h1>What the La Crosse Common Council is doing with your tax dollars</h1>"
             f"<p class='lede'>Plain counts and dollars from the city's own public records for {e(self.year)}. "
             "Every number links back to its source. No grades, no opinions.</p>"]
        if latest:
            acts = self.by_meeting[latest["id"]]
            rc = [a for a in acts if a["has_roll_call"]]
            split = [a for a in rc if a["yes"] and a["no"]]
            failed = [a for a in acts if a["result"] == "Fail"]
            appr = [self.items[i] for i, a in self.approved.items() if a["meeting_id"] == latest["id"]]
            with_amt = [i for i in appr if i["amount"] is not None and not i["amends_prior"]]
            bullets = [f"The council took up <b>{len({a['item_id'] for a in acts})}</b> items and approved <b>{len(appr)}</b>.",
                       f"<b>{len(rc)}</b> votes were recorded member by member; <b>{len(split)}</b> of those were not unanimous."
                       f" The rest passed by voice or consent vote.",
                       (f"<b>{len(failed)}</b> motion{'s' if len(failed) != 1 else ''} failed: " +
                        ", ".join(f"a motion marked “{e((a['action'] or '').capitalize())}” on <a href='{self.item_href(self.items[a['item_id']])}'>{e(self.items[a['item_id']]['name'])}</a>" for a in failed[:4]) + "."
                        if failed else "No motions failed.")]
            if with_amt:
                top = max(with_amt, key=lambda i: i["amount"])
                bullets.append(f"<b>{len(with_amt)}</b> approved items name a dollar amount in their title, adding up to "
                               f"<b>{money(sum(i['amount'] for i in with_amt))}</b>.")
                bullets.append(f"Largest: <a href='{self.item_href(top)}'>{e(top['name'])}</a>, {money(top['amount'])}.")
            else:
                bullets.append("None of the approved items name a dollar amount in their title. Dollar detail is in the agenda packets.")
            b.append(f"<h2>What happened at the most recent meeting ({nice_date(latest['date'])})</h2><ul class='plain'>"
                     + "".join(f"<li>{x}</li>" for x in bullets[:5]) +
                     f"</ul><p><a href='meeting/{latest['id']}.html'>See every item from this meeting</a></p>")
        month_items = [self.items[i] for i, a in self.approved.items()
                       if a["date"][:7] == ym and self.items[i]["amount"] is not None and not self.items[i]["amends_prior"]]
        b.append(f"<h2>Money approved in {month_name(ym)}</h2>")
        if month_items:
            b.append(f"<div class='grid'><div class='stat'><b>{money(sum(i['amount'] for i in month_items))}</b>"
                     f"<span>across {len(month_items)} approved items with a dollar amount in the title</span></div></div>"
                     "<p class='small muted'>This is a floor, not a total. Most items do not state a dollar amount in their title. "
                     "<a href='money.html'>See the Money page</a>.</p>")
        else:
            b.append("<p>No approved items this month state a dollar amount in their title so far. <a href='money.html'>See the Money page</a>.</p>")
        nf = len(self.rf["flags"])
        b.append("<h2>Records flagged for review</h2><p>"
                 + (f"<b>{nf}</b> public record{'s' if nf != 1 else ''} meet{'' if nf != 1 else 's'} at least one of the site's published record checks, "
                    "for example a contract paid past its approved amount, or a large item passed with no recorded vote. "
                    if nf else "No records meet any of the site's published record checks right now. ")
                 + "A flag is a place to look, not a finding. <a href='flags.html'>See the flags and how each test works</a>.</p>")
        b.append(f"<h2>Meetings in {month_name(ym)}</h2>" + self.meeting_table(sorted(this_month, key=lambda m: m["date"])))
        upcoming = [m for m in cm if m["date"] >= self.today]
        b.append("<h2>Upcoming votes</h2>")
        if not upcoming:
            b.append("<p>No upcoming Common Council meetings are posted yet.</p>")
        for m in upcoming[:2]:
            acts = [a for a in self.by_meeting[m["id"]] if not a["action"]]
            b.append(f"<h3>{nice_date(m['date'])}, {e(m['time'])}{': ' + e(m['comment']) if m['comment'] else ''}</h3>")
            b.append("".join(self.item_card(a) for a in acts[:8]) or "<p class='muted'>Agenda items are not posted yet.</p>")
            if len(acts) > 8:
                b.append(f"<p><a href='meeting/{m['id']}.html'>All {len(acts)} items on this agenda</a></p>")
        self.page("index.html", "Home", "".join(b), "index.html")

    def meeting_table(self, ms, root=""):
        if not ms:
            return "<p class='muted'>None.</p>"
        rows = []
        for m in ms:
            acts = self.by_meeting[m["id"]]
            n = len({a["item_id"] for a in acts})
            rc = sum(1 for a in acts if a["has_roll_call"])
            if m["date"] > self.today:
                status = "Upcoming"
            elif m["results_pending"]:
                status = "Results pending"
            elif not n:
                status = "No legislation on agenda"
            else:
                status = "Results posted" + ("" if m["minutes_status"] == "Final" else " (minutes still draft)")
            rows.append(f"<tr><td><a href='{root}meeting/{m['id']}.html'>{nice_date(m['date'])}</a></td><td>{e(m['body'])}"
                        f"{'<br><span class=small muted>' + e(m['comment']) + '</span>' if m['comment'] else ''}</td>"
                        f"<td class=n>{n}</td><td class=n>{rc}</td><td>{status}</td></tr>")
        return ("<div class='scroll'><table><tr><th>Date</th><th>Body</th><th class=n>Items</th>"
                "<th class=n>Recorded votes</th><th>Status</th></tr>" + "".join(rows) + "</table></div>")

    def meetings_pages(self):
        ms = sorted(self.meetings.values(), key=lambda m: (m["date"], m["id"]), reverse=True)
        cards = "".join(self.item_card(a, show_date=True) for a in reversed(self.actions)
                        if a["meeting_id"] in self.meetings)
        body = (f"<h1>Meetings</h1><p class='lede'>Every {e(self.year)} meeting of the "
                f"{e(' and '.join(json.loads(self.meta['bodies'])))}. Search finds items by name, title or file number.</p>"
                "<div class='controls'><input id='q' type='search' placeholder='Search items, e.g. sidewalk, 26-0950' size='40' aria-label='Search items'>"
                "<span id='count' class='muted small'></span></div>"
                f"<div id='list'>{self.meeting_table(ms)}</div><div id='results' hidden>{cards}</div>")
        script = """<script>
const q=document.getElementById('q'),list=document.getElementById('list'),res=document.getElementById('results'),
cards=[...res.querySelectorAll('.item')],count=document.getElementById('count');
q.addEventListener('input',()=>{const t=q.value.trim().toLowerCase();
if(t.length<2){list.hidden=false;res.hidden=true;count.textContent='';return}
let n=0;cards.forEach(c=>{const hit=c.dataset.search.includes(t);c.hidden=!hit;if(hit)n++});
list.hidden=true;res.hidden=false;count.textContent=n+' action'+(n==1?'':'s')+' found'});
</script>"""
        self.page("meetings.html", "Meetings", body, "meetings.html", script)
        for m in ms:
            acts = self.by_meeting[m["id"]]
            links = [f"<a href='{e(m['source_url'])}'>Legistar meeting page</a>"]
            if m["agenda_url"]:
                links.append(f"<a href='{e(m['agenda_url'])}'>Agenda (PDF)</a>")
            if m["minutes_url"]:
                links.append(f"<a href='{e(m['minutes_url'])}'>Minutes (PDF)</a>")
            note = ""
            if m["date"] > self.today:
                note = "<p class='note'>This meeting has not happened yet. Items below are scheduled, not decided.</p>"
            elif m["results_pending"]:
                note = "<p class='note'>Results pending. The agenda is posted but the city has not posted results or minutes yet.</p>"
            elif m["minutes_status"] != "Final" and acts:
                note = "<p class='note'>Minutes are still in draft. Results shown here could change until the minutes are approved.</p>"
            att = self.q("SELECT * FROM attendance WHERE meeting_id=? ORDER BY person", m["id"])
            att_html = ""
            if att:
                away = [f"{e(r['person'])} ({e(r['status'].lower())})" for r in att if r["status"] != "Present"]
                att_html = (f"<p class='meta'>Attendance: {sum(r['status'] == 'Present' for r in att)} of {len(att)} present"
                            + (". Not present: " + ", ".join(away) if away else "") + ".</p>")
            body = (f"<p class='small'><a href='../meetings.html'>← All meetings</a></p><h1>{e(m['body'])}, {nice_date(m['date'])}</h1>"
                    f"<p class='meta'>{e(m['time'])}{' · ' + e(m['comment']) if m['comment'] else ''} · {' · '.join(links)}</p>{att_html}{note}"
                    + ("".join(self.item_card(a, "../") for a in acts) or "<p>No legislative items are listed for this meeting.</p>"))
            self.page(f"meeting/{m['id']}.html", f"{m['body']} {m['date']}", body, "meetings.html")

    def vote_table(self, a):
        vs = self.votes[a["history_id"]]
        cls = {"Yes": "yes", "No": "no"}
        return ("<div class='scroll'><table><tr><th>Member</th><th>Vote</th></tr>" + "".join(
            f"<tr><td>{e(v['person'])}</td><td class='{cls.get(v['vote'], 'oth')}'>{e(v['vote'])}</td></tr>" for v in vs)
            + "</table></div>")

    def item_pages(self):
        for it in self.items.values():
            acts = self.by_item[it["id"]]
            amts = json.loads(it["amounts_json"] or "[]")
            b = [f"<p class='small'><a href='../meetings.html'>← Meetings</a></p><h1>{e(it['name'] or it['file_number'])}</h1>"]
            if it["plain_summary"]:
                b.append(f"<p class='lede'>{e(it['plain_summary'])}</p><p class='small muted'>Plain-English summary generated by "
                         f"{e(it['summary_model'])} (prompt {e(it['summary_prompt_version'])}). The official text below is the record.</p>")
            if self.flags_by_item.get(it["id"]):
                b.append(self.flag_box(self.flags_by_item[it["id"]], "../"))
            b.append(f"<div class='card'><p class='official'><b>Official title:</b> {e(it['title'])}</p>"
                     f"<p><span class='tag'>File {e(it['file_number'])}</span><span class='tag'>{e(it['type'])}</span>"
                     f"<span class='tag'>{e(it['category'])}</span><span class='tag'>Status: {e(it['status'])}</span></p>")
            if amts:
                b.append(f"<p><span class='amt'>{money(it['amount'])}</span> <span class='tag'>from title</span>"
                         + (f" <span class='small muted'>The title names {len(amts)} dollar figures: {', '.join(money(x) for x in amts)}. The largest is shown.</span>" if len(amts) > 1 else "")
                         + (" <span class='small muted'>This item amends an earlier resolution, so it is left out of money totals to avoid counting the same dollars twice.</span>" if it["amends_prior"] else "") + "</p>")
            else:
                b.append("<p class='muted small'>No dollar amount appears in the title."
                         + (" See the fiscal impact from the staff report below." if it["fiscal_impact"] else " Check the attached documents for cost detail.") + "</p>")
            if it["staff_report_url"]:
                b.append("<h3>What city staff told the council</h3>"
                         + (f"<p><b>Summary and purpose:</b> {e(it['staff_summary'])}</p>" if it["staff_summary"] else "")
                         + (f"<p><b>Fiscal impact:</b> {e(it['fiscal_impact'])}</p>" if it["fiscal_impact"] else
                            "<p class='muted small'>The staff report's Fiscal Impact section is blank.</p>")
                         + f"<p class='meta'>Copied word for word from the <a href='{e(it['staff_report_url'])}'>staff report (PDF)</a>. "
                           "Written by city staff, not by this site.</p>")
            sp = self.sponsors[it["id"]]
            if sp:
                b.append(f"<p class='meta'>Sponsored by: {e(', '.join(s['person'] for s in sp))}</p>")
            b.append(f"<p class='meta'><a href='{e(it['source_url'])}'>Source: Legistar file {e(it['file_number'])}</a></p></div>")
            b.append("<h2>What happened, step by step</h2>")
            for a in acts:
                mover = (f"<p class='meta'>Moved by {e(a['mover'])}" + (f", seconded by {e(a['seconder'])}" if a["seconder"] else "") + "</p>") if a["mover"] else ""
                text = f"<p class='small'>{e(a['action_text'])}</p>" if a["action_text"] else ""
                mlink = (f"<a href='../meeting/{a['meeting_id']}.html'>{nice_date(a['date'])}</a>" if a["meeting_id"] in self.meetings
                         else (nice_date(a["date"]) if a["date"] else "Date not recorded"))
                b.append(f"<div class='card'><h3>{mlink} · {e(a['body'])}</h3><p><b>{e(self.outcome(a))}</b></p>{mover}{text}"
                         + (self.vote_table(a) if a["has_roll_call"] and self.votes[a["history_id"]] else "")
                         + f"<p class='meta'><a href='{e(a['source_url'])}'>Source: Legistar action record</a></p></div>")
            if self.docs[it["id"]]:
                b.append("<h2>Documents</h2><ul class='plain'>" + "".join(
                    f"<li><a href='{e(d['url'])}'>{e(d['name'])}</a></li>" for d in self.docs[it["id"]]) + "</ul>")
            self.page(f"item/{it['file_number']}.html", it["name"] or it["file_number"], "".join(b), "meetings.html")

    def money_page(self):
        rows = [(a["date"][:7], self.items[i], a) for i, a in self.approved.items()]
        counted = [(ym, it, a) for ym, it, a in rows if it["amount"] is not None and not it["amends_prior"]]
        cats = collections.defaultdict(lambda: collections.defaultdict(list))
        for ym, it, a in counted:
            cats[it["category"]][ym].append((it, a))
        b = [f"<h1>Money</h1><p class='lede'>Dollar amounts the Common Council approved in {e(self.year)}, by month and by kind of item.</p>",
             f"<p class='note'><b>Read this first.</b> Of {len(rows)} items the council approved, only {len(counted)} state a dollar amount in their "
             "title. Those are the only dollars shown here, each marked “from title”. The rest of the spending detail is in agenda packets and the budget "
             "book. Staff-report cost statements are listed <a href='#fiscal'>at the bottom of this page</a>, and actual payments are on the "
             "<a href='payments.html'>Who gets paid</a> page. Treat every figure here as a floor, not a total. Categories are not added together, because borrowing pays "
             "for later contracts and adding them would count the same dollars twice. Borrowing figures are “not to exceed” limits.</p>"]
        order = ["Contracts and purchases", "Borrowing", "TIF districts", "Grants", "Budget", "Other"]
        detail = []
        for c in order:
            n_cat = sum(1 for _, it, _ in rows if it["category"] == c)
            months = cats.get(c, {})
            total = sum(it["amount"] for ms in months.values() for it, _ in ms)
            b.append(f"<h2>{e(c)}</h2><p class='meta'>{n_cat} approved items; {sum(len(v) for v in months.values())} with a dollar amount in the title"
                     + (f", adding up to <b>{money(total)}</b>" if months else "") + ".</p>")
            if not months:
                continue
            top = max(sum(it["amount"] for it, _ in ms) for ms in months.values())
            for ym in sorted(months):
                s = sum(it["amount"] for it, _ in months[ym])
                anchor = f"d-{order.index(c)}-{ym}"
                b.append(f"<a class='bar' href='#{anchor}' title='See the items behind this bar'><span class='lbl'>{month_name(ym)[:3]} {ym[:4]}</span>"
                         f"<span class='track'><span class='fill' style='width:{max(100 * s / top, .5):.1f}%'></span></span>"
                         f"<span class='val'>{money(s)} <span class='muted small'>({len(months[ym])})</span></span></a>")
                detail.append(f"<h3 id='{anchor}'>{e(c)}, {month_name(ym)}: {money(s)}</h3><div class='scroll'><table>"
                              "<tr><th>Item</th><th class=n>Amount (from title)</th><th>Council vote</th><th>Source</th></tr>" + "".join(
                                  f"<tr><td><a href='{self.item_href(it)}'>{e(it['name'])}</a><br><span class='small muted'>{e(it['title'][:220])}</span></td>"
                                  f"<td class=n>{money(it['amount'])}</td><td class='small'>{e(self.outcome(a))}</td>"
                                  f"<td><a href='{e(it['source_url'])}'>{e(it['file_number'])}</a></td></tr>"
                                  for it, a in sorted(months[ym], key=lambda x: -x[0]["amount"])) + "</table></div>")
        fis = sorted(((a["date"], it, a) for _, it, a in rows if it["fiscal_impact"] and "$" in it["fiscal_impact"]
                      and it["amount"] is None), key=lambda x: x[0], reverse=True)
        b.append("<h2>The items behind each bar</h2>" + "".join(detail))
        b.append(f"<h2 id='fiscal'>Approved items where the cost is only in the staff report ({len(fis)})</h2>"
                 "<p class='small muted'>These items have no dollar amount in their title, but the city's staff report states a fiscal impact. "
                 "The text is copied word for word. The figures are not added into the totals above, because they mix costs, revenues, "
                 "borrowing and property values.</p><div class='scroll'><table><tr><th>Approved</th><th>Item</th><th>Fiscal impact, in staff's words</th><th>Source</th></tr>"
                 + "".join(f"<tr><td>{nice_date(d)}</td><td><a href='{self.item_href(it)}'>{e(it['name'])}</a><br><span class='small muted'>{e(it['category'])}</span></td>"
                           f"<td class='small'>{e(it['fiscal_impact'][:420])}{'…' if len(it['fiscal_impact']) > 420 else ''}</td>"
                           f"<td><a href='{e(it['staff_report_url'])}'>Staff report</a></td></tr>" for d, it, a in fis) + "</table></div>")
        self.page("money.html", "Money", "".join(b), "money.html")

    def payments_page(self):
        SMALL = 1000
        pay = self.q("SELECT * FROM payments")
        checks = self.q("SELECT * FROM packet_checks")
        months = sorted({r["bills_month"] for r in pay})
        src = {}
        for r in pay:
            src[r["bills_month"]] = (r["source_url"], self.items[r["item_id"]]["file_number"])
        vend = collections.defaultdict(lambda: {"t": 0.0, "n": 0, "m": collections.defaultdict(float), "d": collections.defaultdict(float)})
        dept = collections.defaultdict(float)
        for r in pay:
            v = vend[r["vendor"]]
            v["t"] += r["amount"]; v["n"] += 1
            v["m"][r["bills_month"]] += r["amount"]; v["d"][r["department"]] += r["amount"]
            dept[r["department"]] += r["amount"]
        total = sum(v["t"] for v in vend.values())
        big = {k: v for k, v in vend.items() if v["t"] >= SMALL}
        small = {k: v for k, v in vend.items() if v["t"] < SMALL}
        V = [dict(v=k, t=round(v["t"], 2), n=v["n"], m={mi: round(x, 2) for mi, x in sorted(v["m"].items())},
                  d=sorted(([dn, round(x, 2)] for dn, x in v["d"].items()), key=lambda z: -z[1])[:6])
             for k, v in sorted(big.items(), key=lambda kv: -kv[1]["t"])]
        pc = collections.defaultdict(lambda: [0.0, 0])
        for r in self.q("SELECT merchant, amount FROM pcard"):
            pc[r["merchant"]][0] += r["amount"]; pc[r["merchant"]][1] += 1
        pc_total = sum(x[0] for x in pc.values())
        PC = [[k, round(x[0], 2), x[1]] for k, x in sorted(pc.items(), key=lambda kv: -kv[1][0]) if x[0] >= SMALL]
        est = self.q("SELECT * FROM estimates ORDER BY bills_month")
        jobs = {}
        for r in est:
            j = jobs.setdefault(r["job"], dict(c=r["contractor"], n="", job=r["job"], paid=0.0, amt=0.0, cont=0.0, k=0))
            j["c"] = re.sub(r"\s*\((PARTIAL )?FINAL\)", "", r["contractor"]); j["n"] = r["contract_name"] or j["n"]
            j["paid"] += r["estimate"]; j["amt"] = r["contract_amount"]; j["cont"] = r["contingency"]; j["k"] += 1
        n_ok = sum(1 for c in checks if c["ok"])
        b = ["<h1>Who gets paid</h1><p class='lede'>Every payment the city listed in the monthly “bills and estimates” the Common Council "
             f"approved in {e(self.year)}: who was paid, how much, and from which department.</p>",
             f"<div class='grid'><div class='stat'><b>{money(total)}</b><span>paid out across {len(months)} monthly bill lists</span></div>"
             f"<div class='stat'><b>{len(vend):,}</b><span>different payees</span></div>"
             f"<div class='stat'><b>{len(pay):,}</b><span>payment lines read from the city's documents</span></div></div>",
             "<p class='note'><b>Read this first.</b> This is money going out, not only spending on city services. It includes taxes the city collects and passes on "
             "to the school district, county and technical college, payroll taxes and employee benefits, debt payments, and the city's purchasing-card bill "
             "(shown as US Bank). Each month's list covers payments made the month before the council vote. Payee names are cut off at 30 letters in the city's "
             f"document. Payees who received less than {money(SMALL)} in total are counted but not named, since many are refunds to residents; they are in the source documents. "
             f"Accuracy check: for {n_ok} of {len(checks)} documents, the lines read here add up exactly to the total printed in the document.</p>",
             "<h2>Monthly totals</h2><div class='scroll'><table><tr><th>Approved by council</th><th class=n>Total paid</th><th>Council item</th><th>Source document</th></tr>"]
        for mi in months:
            t = sum(r["amount"] for r in pay if r["bills_month"] == mi)
            b.append(f"<tr><td>{month_name(mi)}</td><td class=n>{money(t)}</td><td><a href='item/{src[mi][1]}.html'>{src[mi][1]}</a></td>"
                     f"<td><a href='{e(src[mi][0])}'>Bill detail (PDF)</a></td></tr>")
        b.append("</table></div><h2>Payees</h2><div class='controls'><input id='vq' type='search' size='36' placeholder='Search payees, e.g. excavating' aria-label='Search payees'>"
                 "<span id='vn' class='muted small'></span></div><p class='small muted'>Select a payee to see its payments by month and department. "
                 f"{len(small):,} payees under {money(SMALL)} each, {money(sum(v['t'] for v in small.values()))} in total, are not listed by name.</p>"
                 "<div class='scroll'><table id='vt'></table></div><p><button id='more' type='button'>Show more</button></p>")
        b.append("<h2>By department or fund</h2><p class='small muted'>The department or fund each payment was charged to, as labeled by the city.</p>"
                 "<details><summary>Show all " + str(len(dept)) + " departments and funds</summary><div class='scroll'><table><tr><th>Department or fund</th><th class=n>Total paid</th></tr>"
                 + "".join(f"<tr><td>{e(k)}</td><td class=n>{money(v)}</td></tr>" for k, v in sorted(dept.items(), key=lambda kv: -kv[1])) + "</table></div></details>")
        b.append(f"<h2>Purchasing-card purchases</h2><p class='small muted'>City staff also buy with purchasing cards. The card bill is already inside the totals above "
                 f"(paid to US Bank), so this is a breakdown of that bill, not extra spending: {money(pc_total)} across {len(pc):,} merchants. Merchant names are as they appear on card statements. "
                 f"Merchants under {money(SMALL)} in total are not listed.</p><details><summary>Show {len(PC)} merchants</summary><div class='scroll'><table><tr><th>Merchant</th>"
                 "<th class=n>Total</th><th class=n>Purchases</th></tr>" + "".join(f"<tr><td>{e(k)}</td><td class=n>{money(t)}</td><td class=n>{n}</td></tr>" for k, t, n in PC) + "</table></div></details>")
        b.append(f"<h2>Construction and design contracts in progress</h2><p class='small muted'>From the monthly estimates sheets: {len(jobs)} contracts that received a progress payment in "
                 f"{e(self.year)}. “Paid this year” adds up only the payments listed in {e(self.year)} sheets, so contracts that started earlier have been paid more than shown.</p>"
                 "<div class='scroll'><table><tr><th>Contractor</th><th>Contract</th><th class=n>Contract amount</th><th class=n>Contingency</th><th class=n>Paid this year</th><th class=n>Payments</th></tr>"
                 + "".join(f"<tr><td>{e(j['c'])}</td><td>{e(j['n'] or 'Name not readable in the document')}<br><span class='small muted'>Job {e(j['job'])}</span></td><td class=n>{money(j['amt'])}</td>"
                           f"<td class=n>{money(j['cont']) if j['cont'] else '<span class=muted>none</span>'}</td><td class=n>{money(j['paid'])}</td><td class=n>{j['k']}</td></tr>"
                           for j in sorted(jobs.values(), key=lambda j: -j["amt"])) + "</table></div>")
        script = ("<script>const V=" + json.dumps(V).replace("</", "<\\/") + ";const SRC=" + json.dumps({m: src[m][0] for m in months}) + """;
const MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const $=i=>document.getElementById(i),esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const usd=x=>(x<0?'-':'')+'$'+Math.abs(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
let lim=50;
function draw(){const t=$('vq').value.trim().toLowerCase();const rows=V.filter(v=>!t||v.v.toLowerCase().includes(t));
$('vn').textContent=rows.length.toLocaleString()+' payee'+(rows.length==1?'':'s');
let h='<tr><th>Payee</th><th class=n>Total paid</th><th class=n>Payment lines</th></tr>';
rows.slice(0,lim).forEach(v=>{h+='<tr><td><details><summary>'+esc(v.v)+'</summary><p class="small"><b>By month approved:</b> '+
Object.entries(v.m).map(([m,x])=>'<a href="'+esc(SRC[m])+'">'+MN[+m.slice(5)-1]+'</a> '+usd(x)).join(' · ')+'</p><p class="small"><b>Charged to:</b> '+
v.d.map(d=>esc(d[0])+' '+usd(d[1])).join(' · ')+'</p></details></td><td class=n>'+usd(v.t)+'</td><td class=n>'+v.n+'</td></tr>'});
$('vt').innerHTML=h;$('more').hidden=rows.length<=lim}
$('vq').addEventListener('input',()=>{lim=50;draw()});$('more').addEventListener('click',()=>{lim+=200;draw()});draw();</script>""")
        self.page("payments.html", "Who gets paid", "".join(b), "payments.html", script)

    def member_stats(self, p):
        pid = p["id"]
        cast = [(a, v["vote"]) for a in self.rollcalls for v in self.votes[a["history_id"]] if v["person_id"] == pid]
        c = collections.Counter(v for _, v in cast)
        decided = [(a, v) for a, v in cast if v in ("Yes", "No") and a["yes"] != a["no"]]
        with_major = sum(1 for a, v in decided if (v == "Yes") == (a["yes"] > a["no"]))
        att = self.q("SELECT a.status FROM attendance a JOIN meetings m ON m.id=a.meeting_id WHERE a.person_id=? AND m.body_id=?", pid, COUNCIL)
        return dict(
            cast=cast, counts=c, rollcalls=len(cast), voted=c["Yes"] + c["No"], decided=len(decided), with_major=with_major,
            att_total=len(att), att_present=sum(1 for r in att if r["status"] == "Present"),
            moved=[a for a in self.council if a["mover_id"] == pid],
            seconded=[a for a in self.council if a["seconder_id"] == pid],
            sponsored=[self.items[s["item_id"]] for s in self.q("SELECT item_id FROM sponsors WHERE person_id=?", pid)],
            no_votes=[a for a, v in cast if v == "No"])

    def member_pages(self):
        stats = {p["id"]: self.member_stats(p) for p in self.people}
        members = [p for p in self.people if p["role"] != "Mayor"]
        mayors = [p for p in self.people if p["role"] == "Mayor"]
        rows = ""
        for p in members:
            s = stats[p["id"]]
            c = s["counts"]
            rows += (f"<tr><td><a href='member/{p['id']}.html'>{e(p['name'])}</a><br><span class='small muted'>District {e(p['district'])}</span></td>"
                     f"<td class=n>{s['att_present']} of {s['att_total']}</td><td class=n>{s['rollcalls']}</td><td class=n>{c['Yes']}</td><td class=n>{c['No']}</td>"
                     f"<td class=n>{c['Abstain']}</td><td class=n>{c['Excused']}</td><td class=n>{pct(s['with_major'], s['decided'])}<br>"
                     f"<span class='small muted'>{s['with_major']} of {s['decided']}</span></td><td class=n>{len(s['moved'])}</td><td class=n>{len(s['seconded'])}</td></tr>")
        body = (f"<h1>Council members and Mayor</h1><p class='lede'>The same counts for every member, in district order, from "
                f"{len(self.rollcalls)} recorded Common Council votes in {e(self.year)}.</p>"
                "<p class='note'>Most council items pass by voice or consent vote with no individual votes recorded, so these counts cover only "
                "the items that had a recorded vote. “Excused” is not a vote and is left out of yes and no counts. “With the larger side” means the member "
                "voted the way most members did on that vote; it says nothing about whether a vote was right.</p>"
                "<div class='scroll'><table><tr><th>Member</th><th class=n>Meetings present</th><th class=n>Recorded votes</th><th class=n>Yes</th><th class=n>No</th>"
                "<th class=n>Abstain</th><th class=n>Excused</th><th class=n>With the larger side</th><th class=n>Moved</th><th class=n>Seconded</th></tr>"
                + rows + "</table></div><h2>Mayor</h2>"
                + "".join(f"<p><a href='member/{p['id']}.html'>{e(p['name'])}</a>. The Mayor does not cast a vote on most council items, "
                          f"so the Mayor's page shows items sponsored, appointments and vetoes instead.</p>" for p in mayors))
        self.page("members.html", "Council members and Mayor", body, "members.html")

        def item_list(its, limit=400):
            return "<ul class='plain'>" + "".join(
                f"<li><a href='../{self.item_href(i)}'>{e(i['name'])}</a> <span class='small muted'>{e(i['file_number'])}, {e(i['type'])}"
                f"{', ' + money(i['amount']) + ' (from title)' if i['amount'] is not None else ''}</span></li>" for i in its[:limit]) + "</ul>"

        def action_list(acts):
            return "<ul class='plain'>" + "".join(
                f"<li>{nice_date(a['date'])}: <a href='../{self.item_href(self.items[a['item_id']])}'>{e(self.items[a['item_id']]['name'])}</a> "
                f"<span class='small muted'>{e((a['action'] or '').capitalize())}</span></li>" for a in acts) + "</ul>"

        for p in self.people:
            s = stats[p["id"]]
            c = s["counts"]
            role = "Mayor" if p["role"] == "Mayor" else f"Council Member, District {p['district']}"
            b = [f"<p class='small'><a href='../members.html'>← All members</a></p><h1>{e(p['name'])}</h1>"
                 f"<p class='meta'>{e(role)} · Current term {nice_date(p['term_start'])} to {nice_date(p['term_end']) if p['term_end'] else 'present'}</p>"]
            if p["role"] != "Mayor":
                other = s["rollcalls"] - c["Yes"] - c["No"] - c["Abstain"] - c["Excused"]
                b.append("<div class='grid'>"
                         f"<div class='stat'><b>{s['att_present']} of {s['att_total']}</b><span>council meetings marked present at roll call</span></div>"
                         f"<div class='stat'><b>{s['rollcalls']}</b><span>recorded council votes in {e(self.year)}</span></div>"
                         f"<div class='stat'><b>{c['Yes']} yes · {c['No']} no</b><span>{c['Abstain']} abstain · {c['Excused']} excused"
                         f"{' · ' + str(other) + ' other' if other else ''}</span></div>"
                         f"<div class='stat'><b>{pct(s['with_major'], s['decided'])}</b><span>voted with the larger side ({s['with_major']} of {s['decided']} yes-or-no votes)</span></div>"
                         f"<div class='stat'><b>{len(s['moved'])} · {len(s['seconded'])}</b><span>motions moved · seconded</span></div>"
                         f"<div class='stat'><b>{len(s['sponsored'])}</b><span>items sponsored</span></div></div>")
                if s["voted"] < 20:
                    b.append("<p class='note'>Small sample. Fewer than 20 recorded votes is too few to draw conclusions from.</p>")
                b.append(f"<h2>No votes ({len(s['no_votes'])})</h2><p class='small muted'>Each no vote with the item it was cast on. A dollar amount appears only "
                         "when the item's title states one. A no vote on a motion to amend, refer or deny is not a vote against the item itself, so the motion is shown.</p>")
                if s["no_votes"]:
                    b.append("<div class='scroll'><table><tr><th>Date</th><th>Item</th><th>Motion voted on</th><th class=n>Amount (from title)</th><th class=n>Tally</th><th>Source</th></tr>" + "".join(
                        f"<tr><td>{nice_date(a['date'])}</td><td><a href='../{self.item_href(self.items[a['item_id']])}'>{e(self.items[a['item_id']]['name'])}</a>"
                        f"<br><span class='small muted'>{e(self.items[a['item_id']]['category'])}</span></td><td class='small'>{e((a['action'] or '').capitalize())}"
                        f"{' (motion failed)' if a['result'] == 'Fail' else ''}</td><td class=n>{money(self.items[a['item_id']]['amount']) or '<span class=muted>none stated</span>'}</td>"
                        f"<td class=n>{a['yes']}–{a['no']}</td><td><a href='{e(a['source_url'])}'>Record</a></td></tr>" for a in s["no_votes"]) + "</table></div>")
                else:
                    b.append("<p>None recorded.</p>")
                b.append(f"<h2>Motions moved ({len(s['moved'])})</h2>" + (action_list(s["moved"]) if s["moved"] else "<p>None recorded.</p>"))
                b.append(f"<h2>Motions seconded ({len(s['seconded'])})</h2>" + (action_list(s["seconded"]) if s["seconded"] else "<p>None recorded.</p>"))
                b.append(f"<h2>Items sponsored ({len(s['sponsored'])})</h2>" + (item_list(s["sponsored"]) if s["sponsored"] else "<p>None recorded.</p>"))
            else:
                appts = [i for i in s["sponsored"] if i["type"] == "Appointment"]
                vetoes = [a for a in self.council if "VETO" in (a["action"] or "").upper()]
                b.append("<div class='grid'>"
                         f"<div class='stat'><b>{len(s['sponsored'])}</b><span>items sponsored in {e(self.year)}</span></div>"
                         f"<div class='stat'><b>{len(appts)}</b><span>appointment items sent to the council</span></div>"
                         f"<div class='stat'><b>{len(vetoes)}</b><span>veto actions recorded in Legistar</span></div></div>"
                         "<p class='note'>Sponsoring an item often means the Mayor's office introduced it on behalf of a city department. "
                         "It does not by itself show a personal position.</p>")
                b.append(f"<h2>Vetoes ({len(vetoes)})</h2>" + (action_list(vetoes) if vetoes else
                         f"<p>No veto actions appear in the Legistar records collected for {e(self.year)}.</p>"))
                b.append(f"<h2>Appointments ({len(appts)})</h2>" + (item_list(appts) if appts else "<p>None recorded.</p>"))
                b.append(f"<h2>Items sponsored ({len(s['sponsored'])})</h2>" + (item_list(s["sponsored"]) if s["sponsored"] else "<p>None recorded.</p>"))
            b.append(self.member_flag_section(p, s))
            self.page(f"member/{p['id']}.html", p["name"], "".join(b), "members.html")

    # ------------------------------------------------------------ review flags
    def flag_box(self, fl, root=""):
        return ("<div class='note'><b>Flagged for review.</b> This record meets "
                f"{len(fl)} of the site's <a href='{root}flags.html'>published record checks</a>. A flag is a place to look, not a finding. "
                "It does not say anyone did anything wrong.<ul class='plain'>"
                + "".join(f"<li><a href='{root}flags.html#{f.anchor}'>{e(f.headline)}</a></li>" for f in fl) + "</ul></div>")

    def flag_card(self, f):
        links = [f"<a href='{e(u)}'>{e(l)}</a>" for l, u in f.links]
        if f.item_id in self.items:
            links.insert(0, f"<a href='item/{e(self.items[f.item_id]['file_number'])}.html'>Item page</a>")
        resp = self.responses.get(f.key)
        resp_html = ""
        if resp:
            who = e(resp.get("from") or "Response")
            when = f" ({e(resp['date'])})" if resp.get("date") else ""
            resp_html = f"<div class='note'><b>Response from {who}{when}, posted word for word:</b> {e(resp['text'])}</div>"
        return (f"<div class='card flag' id='{f.anchor}'><h3>{e(f.headline)}</h3><ul class='plain'>"
                + "".join(f"<li>{e(x)}</li>" for x in f.facts) + f"</ul><p class='meta'>{' · '.join(links)}</p>{resp_html}"
                f"<p class='small muted'>Flag ID: {e(f.key)}</p></div>")

    def member_flag_section(self, p, s):
        rows = review_flags.member_involvement(self.rf, p["id"])
        is_mayor = p["role"] == "Mayor"

        def distinct(role):
            return len({f.item_id for f, roles, _ in rows if role in roles})
        stats = [("sponsor", "sponsored", len(s["sponsored"]), "items sponsored")]
        if not is_mayor:
            stats += [("mover", "moved", len({a["item_id"] for a in s["moved"]}), "items with a motion moved"),
                      ("seconder", "seconded", len({a["item_id"] for a in s["seconded"]}), "items with a motion seconded")]
        grid = "".join(f"<div class='stat'><b>{distinct(role)} of {total}</b><span>{label} that were flagged for review</span></div>"
                       for role, _, total, label in stats)
        abst = sum(1 for _, roles, _ in rows if "abstained" in roles)
        out = ["<h2>Flagged items this person is recorded on</h2>",
               "<p class='note'>The public record names this person on the items below as sponsor, mover or seconder, or as an abstaining member. "
               "Those are routine roles. A sponsor often introduces an item for a city department, and the flag is about the record, not the person. "
               "The same table and the same checks appear for every member and the Mayor. See the <a href='../flags.html'>flag rules</a>.</p>",
               f"<div class='grid'>{grid}<div class='stat'><b>{abst}</b><span>recorded abstentions</span></div></div>"]
        if rows:
            out.append("<div class='scroll'><table><tr><th>Flag</th><th>Role in the record</th><th>How this person voted</th></tr>" + "".join(
                f"<tr><td><a href='../flags.html#{f.anchor}'>{e(f.headline)}</a></td><td>{e(', '.join(roles))}</td>"
                f"<td class='small'>{e('; '.join(votes)) if votes else '<span class=muted>no recorded vote by member</span>'}</td></tr>"
                for f, roles, votes in rows) + "</table></div>")
        else:
            out.append("<p>No flagged items name this person in these roles.</p>")
        return "".join(out)

    def flags_page(self):
        rf, cfg = self.rf, self.rf["config"]
        by_rule = collections.defaultdict(list)
        for f in rf["flags"]:
            by_rule[f.rule].append(f)
        b = ["<h1>Review flags</h1><p class='lede'>Public records that meet a published test of the kind auditors use to decide where to look first. "
             "Each test runs the same way on every record, every night. Tests that find nothing are listed too.</p>",
             "<p class='note'><b>Read this first.</b> A flag is not a finding. It does not say that anyone broke a rule, acted in bad faith or made a mistake. "
             "Every test below has ordinary explanations, and they are printed beside it. Flags are about records, such as a contract or a payment line, "
             "not about anyone's character. The thresholds were chosen by this site and are not city rules. The city's own record is the authority, "
             "and anyone named can send a response that will be posted word for word next to the flag (see the end of this page).</p>",
             "<div class='grid'>" + "".join(
                 f"<a class='stat' href='#r-{r['id']}' style='text-decoration:none;color:inherit'><b>{'Paused' if r['id'] in PAUSED_RULES else len(by_rule[r['id']])}</b><span>{e(r['short'])}</span></a>"
                 for r in rf["rules"]) + "</div>"]
        for r in rf["rules"]:
            fl = by_rule[r["id"]]
            b.append(f"<h2 id='r-{r['id']}'>{e(r['title'])}</h2>" + ("" if r["id"] in PAUSED_RULES else f"<p class='meta'>{len(fl)} record{'s' if len(fl) != 1 else ''} flagged</p>")
                     + "<dl class='rule'>"
                     f"<dt>What the test checks</dt><dd>{e(r['checks'])}</dd>"
                     f"<dt>Why auditors look at it</dt><dd>{e(r['why'])}</dd>"
                     f"<dt>Ordinary reasons it can happen</dt><dd>{e(r['innocent'])}</dd>"
                     f"<dt>Threshold</dt><dd>{e(r['threshold'])}</dd>"
                     f"<dt>Records used</dt><dd>{e(r['records'])}</dd></dl>")
            if r["id"] in PAUSED_RULES:
                b.append(f"<p class='note'><b>Paused.</b> {e(PAUSED_RULES[r['id']])}</p>")
                continue
            if not fl:
                b.append("<p>No records met this test in the data collected so far.</p>")
                continue
            head, rest = fl[:20], fl[20:]
            b.append("".join(self.flag_card(f) for f in head))
            if rest:
                b.append(f"<details><summary>Show the other {len(rest)}</summary>" + "".join(self.flag_card(f) for f in rest) + "</details>")

        c = rf["concentration"]
        b.append("<h2 id='concentration'>Where the payment dollars concentrate</h2>")
        if c["n_payees"]:
            b.append(f"<p class='small muted'>This is a ranking, not a flag. It shows how much of the city's spending with outside payees went to each one. "
                     f"Of {money(c['total'])} listed in the monthly bills, {money(c['skipped_total'])} was left out because it mostly passes through "
                     "(taxes sent to other governments, payroll, benefits, debt payments, the purchasing-card bill). "
                     f"That leaves {money(c['kept_total'])} paid to {c['n_payees']:,} payees"
                     + ("; the top payee received half of it" if c["half_n"] == 1 else
                        f"; the top {c['half_n']} of them received half of it" if c["half_n"] else "")
                     + ". Spelling variants of one company (such as “Inc” and “Co”) are added together. Concentration is normal for utilities, "
                       "insurers and large contractors. It matters when it is unexpected or when no competition is on record.</p>"
                     "<div class='scroll'><table><tr><th>Payee</th><th class=n>Paid</th><th class=n>Share</th><th class=n>Months paid</th><th class=n>Departments</th></tr>"
                     + "".join(f"<tr><td>{e(t['name'])}</td><td class=n>{money(t['total'])}</td><td class=n>{100 * t['share']:.1f}%</td>"
                               f"<td class=n>{t['months']}</td><td class=n>{t['depts']}</td></tr>" for t in c["table"]) + "</table></div>")
            if c["excluded"]:
                b.append("<details><summary>The largest payments left out of this ranking, and why</summary><div class='scroll'><table>"
                         "<tr><th>Payee</th><th>Reason</th><th class=n>Paid</th></tr>" + "".join(
                             f"<tr><td>{e(v)}</td><td>{e(reason)}</td><td class=n>{money(a)}</td></tr>" for v, reason, a in c["excluded"])
                         + "</table></div><p class='small muted'>This sorting uses name and account keywords. If something here was left out by mistake, "
                           "please report it.</p></details>")
        else:
            b.append("<p>No payment data yet.</p>")

        rc = rf["records_check"]
        b.append("<h2 id='records-check'>Records check: possible reading problems</h2>"
                 "<p class='small muted'>These are not audit flags. They are places where the site's computer reading of the city's PDF documents "
                 "may be wrong, listed so that nothing is hidden.</p>")
        if rc["zero_contract"]:
            b.append("<ul class='plain'>" + "".join(
                f"<li>{e(j['contractor'])}, {e(j['name'] or 'job ' + j['job'])}: the sheet shows a contract amount of $0 but {money(j['paid'])} paid. "
                + " · ".join(f"<a href='{e(u)}'>{e(l)}</a>" for l, u in j["links"][:3]) + "</li>" for j in rc["zero_contract"]) + "</ul>")
        if rc["bad_checks"]:
            b.append("<ul class='plain'>" + "".join(
                f"<li>A {e(x['kind'])} document where the lines read here add up to {money(x['parsed_total'])} but the printed total is "
                f"{money(x['stated_total'])}. <a href='{e(x['source_url'])}'>Source (PDF)</a></li>" for x in rc["bad_checks"]) + "</ul>")
        if not rc["zero_contract"] and not rc["bad_checks"]:
            b.append("<p>Nothing to report.</p>")

        b.append("<h2 id='respond'>Respond, correct or report</h2>"
                 f"<p>If you are named here, or you work for the city, and you want to explain a flag, email <a href=\"mailto:{CORRECTIONS_EMAIL}\">{CORRECTIONS_EMAIL}</a> "
                 "with the Flag ID. The reply is posted word for word next to the flag, and the flag stays so readers can see both. "
                 "If a flag rests on a reading mistake, it is removed and the fix is noted on the About page.</p>"
                 "<p>This site is not an investigator and cannot say what happened. If you think a rule was broken, take it to the people who can look into it: "
                 "the city attorney, the city's ethics board if one applies, or the district attorney. Public records requests can ask the city for bid "
                 "results, contracts and conflict disclosures that are not on Legistar.</p>")
        self.page("flags.html", "Review flags", "".join(b), "flags.html")

    def compare_page(self):
        members = [p for p in self.people if p["role"] != "Mayor"]
        code = {"Yes": "Y", "No": "N", "Abstain": "A", "Excused": "E"}
        data = []
        for a in self.rollcalls:
            it = self.items[a["item_id"]]
            data.append(dict(d=a["date"], f=it["file_number"], n=it["name"], t=it["title"], ty=it["type"], c=it["category"],
                             amt=it["amount"], act=(a["action"] or "").capitalize(), fail=a["result"] == "Fail", y=a["yes"], no=a["no"],
                             v={str(v["person_id"]): code.get(v["vote"], "?") for v in self.votes[a["history_id"]]}))
        types = sorted({d["ty"] for d in data})
        catz = sorted({d["c"] for d in data})
        body = (f"<h1>Compare votes</h1><p class='lede'>Pick a kind of item and see how each member voted on every recorded Common Council vote in {e(self.year)}.</p>"
                "<div class='controls'><label>Type <select id='ty'><option value=''>All types</option>" + "".join(f"<option>{e(t)}</option>" for t in types) + "</select></label>"
                "<label>Category <select id='cat'><option value=''>All categories</option>" + "".join(f"<option>{e(t)}</option>" for t in catz) + "</select></label>"
                "<label>Amount at least $ <input id='min' type='number' min='0' step='1000' placeholder='100000' style='width:8em'></label>"
                "<label><input id='split' type='checkbox'> Only votes that were not unanimous</label>"
                "<input id='kw' type='search' placeholder='Keyword' aria-label='Keyword'></div>"
                "<p id='n' class='meta'></p><p class='small muted'>Y = yes, N = no, A = abstain, E = excused, ? = other or not recorded, blank = no vote row for that member. "
                "Amount filters use only dollar figures stated in item titles, so most items have none.</p>"
                "<div class='scroll'><table class='cmp' id='tbl'></table></div><p id='tot' class='small muted'></p>")
        script = ("<script>const M=" + json.dumps([[str(p["id"]), p["name"].split()[-1], p["name"]] for p in members]) +
                  ";const D=" + json.dumps(data).replace("</", "<\\/") + """;
const $=i=>document.getElementById(i),esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function draw(){const ty=$('ty').value,cat=$('cat').value,min=parseFloat($('min').value)||0,sp=$('split').checked,kw=$('kw').value.trim().toLowerCase();
const rows=D.filter(d=>(!ty||d.ty==ty)&&(!cat||d.c==cat)&&(!min||(d.amt||0)>=min)&&(!sp||(d.y&&d.no))&&(!kw||(d.n+' '+d.t+' '+d.f).toLowerCase().includes(kw)));
$('n').textContent=rows.length+' recorded vote'+(rows.length==1?'':'s')+' match'+(rows.length<10?'. Small sample: too few votes to draw conclusions from.':'.');
let h='<tr><th>Item and motion</th>'+M.map(m=>'<th title="'+esc(m[2])+'">'+esc(m[1])+'</th>').join('')+'<th>Tally</th></tr>';
const tot={};M.forEach(m=>tot[m[0]]={Y:0,N:0});
rows.slice().reverse().forEach(d=>{h+='<tr><td><a href="item/'+esc(d.f)+'.html">'+esc(d.n)+'</a><br><span class="small muted">'+d.d+' · '+esc(d.act)+(d.fail?' (motion failed)':'')+(d.amt?' · $'+Math.round(d.amt).toLocaleString():'')+'</span></td>'+
M.map(m=>{const v=d.v[m[0]]||'';if(tot[m[0]][v]!==undefined)tot[m[0]][v]++;return '<td class="'+(v=='Y'?'yes':v=='N'?'no':'oth')+'">'+v+'</td>'}).join('')+'<td>'+d.y+'–'+d.no+'</td></tr>'});
h+='<tr><th>Totals for these votes (yes / no)</th>'+M.map(m=>'<th>'+tot[m[0]].Y+' / '+tot[m[0]].N+'</th>').join('')+'<th></th></tr>';
$('tbl').innerHTML=h}
['ty','cat','min','split','kw'].forEach(i=>$(i).addEventListener('input',draw));draw();</script>""")
        self.page("compare.html", "Compare votes", body, "compare.html", script)

    def about_page(self):
        n_items = len(self.items)
        n_amt = sum(1 for i in self.items.values() if i["amount"] is not None)
        cc_acts = [a for a in self.council if a["action"]]
        body = f"""<h1>About and method</h1>
<h2>Where the data comes from</h2>
<p>Everything here comes from the City of La Crosse's public legislative records on <a href="{e(self.meta['source'])}">Legistar</a>, read through
Legistar's public data service. Each item, vote and meeting links back to the city's own page so you can check it.</p>
<h2>How often it updates</h2>
<p>The site is rebuilt from the city's records by a scheduled job. This copy was last updated {e(self.updated.replace('T', ' ').replace('Z', ' UTC'))}.
It covers {e(self.year)} meetings of the {e(' and '.join(json.loads(self.meta['bodies'])))}: {len(self.meetings)} meetings, {n_items} items,
{len(self.actions)} recorded actions and {len(self.rollcalls)} recorded Common Council votes.</p>
<h2>What is missing</h2>
<ul class="plain">
<li><b>Most items have no individual votes.</b> Of {len(cc_acts)} Common Council actions, {len(self.rollcalls)} have a member-by-member vote. The rest passed by voice or consent vote, and the city records no individual votes for those.</li>
<li><b>Most items do not state a dollar amount.</b> Only {n_amt} of {n_items} items state a dollar figure in their title. Those are marked “from title” and are the only figures added into Money totals, so those totals are a floor. Where the city's staff report states a fiscal impact, that text is shown word for word on the item. The annual budget book is not read yet.</li>
<li><b>Payments come from the city's monthly bill lists.</b> The “Who gets paid” page is read by computer from PDF documents. Each document's lines are added up and checked against the total printed in it. Payee names are cut off at 30 letters in the source, and payees under $1,000 in total are not named.</li>
<li><b>Minutes lag.</b> Recent meetings can show an agenda before results are posted. Those are marked “results pending”, and results can change until minutes are final.</li>
<li><b>Summaries are the city's own.</b> Where a staff report exists, its “Summary/Purpose” text is shown and labeled as city staff's words. This site does not write its own summaries yet.</li>
<li><b>Other years and boards</b> (Board of Estimates, Board of Public Works) are not included yet, though committee steps appear in each item's history.</li>
</ul>
<h2>How the numbers are counted</h2>
<ul class="plain">
<li>Member counts use recorded Common Council votes only. Committee votes are shown on item pages but are not in member totals.</li>
<li>“Excused” is not a vote. It is counted separately and never as a yes or a no.</li>
<li>“With the larger side” is the share of a member's yes-or-no votes that matched what most members voted. Tied votes are left out. Some items need more than a simple majority, so the larger side does not always win.</li>
<li>Each action is counted once, using the city's own record number for that action. An item with two motions on one night (for example, amend, then adopt) shows two separate votes.</li>
<li>An item counts as approved on the date of its first council action recorded as adopted, approved, confirmed or granted.</li>
<li>Money categories (contracts, borrowing, TIF districts, grants, budget) are assigned by keywords in the title. Items that amend an earlier resolution are left out of totals so the same dollars are not counted twice.</li>
<li>A motion to deny or not adopt that passes is shown as that motion passing, with the item named, so a yes or no is never shown without the question that was asked.</li>
<li>Review flags use only the data described above. They cannot see invoices, bid results, contracts, campaign contributions, business ownership or conflict disclosures, so a flag can point to a place to look but cannot show intent.</li>
</ul>
<h2>Fairness rules</h2>
<p>This site shows counts and dollars. It does not rank officials, label them or grade them. Every member gets the same statistics in the same layout,
sample sizes are shown, and small samples are flagged.</p>
<p><a href="flags.html">Review flags</a> are attached to records, such as a contract, a payment line or an agenda item, and not to people's character.
Each flag comes from a test that is written out on that page before any results, with the ordinary reasons it can happen. The tests run the same way on every record,
every night, and tests that find nothing are still listed. A member's page lists flagged items the public record names them on as sponsor, mover or seconder,
or as an abstaining member, always next to how many items were checked, because sponsoring or moving an item is often routine. The thresholds were chosen by this site and are not city rules.
A flag is not a finding. Anyone named can send a response, and it is posted word for word beside the flag.</p>
<h2>Report an error</h2>
<p>If something here does not match the city's record, email <a href="mailto:{CORRECTIONS_EMAIL}">{CORRECTIONS_EMAIL}</a> with the page address and the
Legistar link. The city's record is the authority; this site corrects itself to match it.</p>"""
        self.page("about.html", "About and method", body, "about.html")


if __name__ == "__main__":
    s = Site()
    s.build()
    n = sum(len(f) for _, _, f in os.walk(OUT))
    print(f"wrote {n} files to {OUT}")
