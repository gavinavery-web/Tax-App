import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { ArrowLeft, FileText, FileBarChart2, AlertTriangle, MessageSquare, Building2 } from "lucide-react";

export default function TaxReturnWorkspace() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [missing, setMissing] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [sumResp, missingResp, qResp] = await Promise.all([
        api.get(`/tax-returns/${id}/summary`),
        api.get(`/missing-evidence`),
        api.get(`/tax-returns/${id}/unanswered-questions`),
      ]);
      setSummary(sumResp.data);
      setMissing((missingResp.data || []).filter((m) => m.tax_return_id === id));
      setQuestions(qResp.data?.documents_with_questions || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load workspace");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  if (loading) return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="workspace-loading">
      <Skeleton className="h-12 w-full mb-4" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
  if (error) return <div className="p-6 text-red-700 bg-red-50 border border-red-200 rounded m-6" data-testid="workspace-error">{error}</div>;
  if (!summary) return null;

  const tr = summary.tax_return;
  const completionPct = (() => {
    const open = summary.missing_evidence_open;
    const total = summary.missing_evidence_total || 0;
    if (total === 0) return 0;
    return Math.max(0, Math.round(((total - open) / total) * 100));
  })();

  const openItems = missing.filter((m) => ["Outstanding", "Possible Match", "Accountant Review"].includes(m.status));
  const receivedItems = missing.filter((m) => m.status === "Received");
  const openQuestionCount = questions.reduce((n, d) => n + d.unanswered.length, 0);

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto" data-testid="workspace-page">
      <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
        <Link to="/tax-returns" className="hover:text-zinc-900 inline-flex items-center gap-1" data-testid="workspace-back">
          <ArrowLeft className="w-3.5 h-3.5" /> All tax returns
        </Link>
      </div>
      <header className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }} data-testid="workspace-title">
            {tr.tax_year} · {tr.return_type.replace(/_/g, " ")} — {tr.entity_name}
          </h1>
          <div className="text-sm text-zinc-500 mt-1 flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="capitalize" data-testid="workspace-status">{tr.status.replace(/_/g, " ")}</Badge>
            <span className="text-zinc-400">·</span>
            <span data-testid="workspace-completion">{completionPct}% evidence received</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/register?return=${id}`}>
            <Button variant="outline" className="gap-1.5" data-testid="workspace-link-docs"><FileText className="w-4 h-4" /> Documents</Button>
          </Link>
          <Link to="/reports">
            <Button className="gap-1.5 bg-zinc-950 hover:bg-zinc-800" data-testid="workspace-link-reports"><FileBarChart2 className="w-4 h-4" /> Reports</Button>
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard testid="card-documents" label="Documents" value={summary.documents_count} icon={FileText} />
        <SummaryCard testid="card-inbox" label="Needs Review" value={summary.inbox_count} icon={AlertTriangle} tone={summary.inbox_count > 0 ? "amber" : ""} />
        <SummaryCard testid="card-missing" label="Outstanding" value={summary.missing_evidence_open} icon={Building2} tone={summary.missing_evidence_open > 0 ? "red" : "green"} />
        <SummaryCard testid="card-questions" label="Open Questions" value={openQuestionCount} icon={MessageSquare} tone={openQuestionCount > 0 ? "amber" : ""} />
      </div>

      {questions.length > 0 && (
        <section data-testid="section-questions">
          <h2 className="font-semibold mb-3 tracking-tight" style={{ fontFamily: "Chivo" }}>Questions needing your answer</h2>
          <div className="space-y-2">
            {questions.map((d) => (
              <DocQuestions key={d.document_id} doc={d} onAnswered={load} />
            ))}
          </div>
        </section>
      )}

      <section data-testid="section-missing">
        <div className="flex items-end justify-between mb-3">
          <h2 className="font-semibold tracking-tight" style={{ fontFamily: "Chivo" }}>Missing Evidence</h2>
          <div className="text-xs text-zinc-500 mono">
            {openItems.length} outstanding · {receivedItems.length} received · {missing.length} total
          </div>
        </div>
        <div className="bg-white border border-zinc-200 rounded-lg divide-y divide-zinc-100" data-testid="missing-list">
          {openItems.length === 0 ? (
            <p className="p-4 text-sm text-zinc-500 italic">All evidence collected — nice work.</p>
          ) : openItems.map((m) => (
            <div key={m.id} className="flex justify-between items-center px-4 py-2.5 text-sm" data-testid={`missing-row-${m.id}`}>
              <div className="flex items-center gap-2 min-w-0">
                <span className="truncate">{m.item_needed}</span>
                <Badge variant="outline" className="shrink-0">{m.priority}</Badge>
              </div>
              <span className="text-xs text-zinc-500 mono shrink-0">{m.status}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function SummaryCard({ label, value, icon: Icon, tone, testid }) {
  const toneCls = tone === "amber" ? "border-l-2 border-l-amber-500"
    : tone === "red" ? "border-l-2 border-l-red-600"
    : tone === "green" ? "border-l-2 border-l-emerald-600"
    : "border-l-2 border-l-zinc-900";
  return (
    <Card className={`rounded-sm ${toneCls}`} data-testid={testid}>
      <CardHeader className="pb-1 pt-3">
        <CardTitle className="text-xs uppercase tracking-wider text-zinc-500 mono flex items-center gap-1.5">
          {Icon && <Icon className="w-3.5 h-3.5" />} {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 pb-3">
        <p className="text-2xl font-bold mono">{value}</p>
      </CardContent>
    </Card>
  );
}

function DocQuestions({ doc, onAnswered }) {
  const [vals, setVals] = useState({});
  const [busy, setBusy] = useState({});

  const save = async (q) => {
    const v = vals[q.key];
    if (v === undefined || v === "" || v === null) {
      toast.error("Enter an answer first");
      return;
    }
    setBusy((b) => ({ ...b, [q.key]: true }));
    try {
      await api.patch(`/documents/${doc.document_id}/questions/${q.key}`, { key: q.key, answer: v });
      toast.success("Answer saved");
      onAnswered?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save answer");
    } finally {
      setBusy((b) => ({ ...b, [q.key]: false }));
    }
  };

  return (
    <div className="border-l-2 border-l-amber-500 border border-zinc-200 rounded bg-amber-50/40 p-3" data-testid={`doc-questions-${doc.document_id}`}>
      <div className="text-sm font-medium mb-2 flex items-center gap-2">
        <FileText className="w-3.5 h-3.5 text-zinc-500" />
        <Link to={`/register?open=${doc.document_id}`} className="hover:underline" data-testid={`doc-link-${doc.document_id}`}>
          {doc.document_name}
        </Link>
        <Badge variant="outline" className="text-[10px] uppercase">{doc.category}</Badge>
      </div>
      <div className="space-y-2">
        {doc.unanswered.map((q) => (
          <div key={q.key} className="flex items-center gap-2 text-sm" data-testid={`q-${doc.document_id}-${q.key}`}>
            <span className="flex-1 text-zinc-700">{q.prompt}</span>
            {q.answer_type === "yes_no" ? (
              <div className="inline-flex gap-1">
                {[true, false].map((v) => (
                  <button
                    key={String(v)}
                    type="button"
                    onClick={() => setVals((s) => ({ ...s, [q.key]: v }))}
                    className={`px-2.5 py-1 text-xs rounded border ${vals[q.key] === v ? "bg-zinc-900 text-white border-zinc-900" : "bg-white border-zinc-300"}`}
                    data-testid={`q-${doc.document_id}-${q.key}-${v ? "yes" : "no"}`}
                  >{v ? "Yes" : "No"}</button>
                ))}
              </div>
            ) : q.answer_type === "single_select" ? (
              <select
                className="border border-zinc-300 rounded px-2 py-1 text-sm bg-white"
                value={vals[q.key] || ""}
                onChange={(e) => setVals((s) => ({ ...s, [q.key]: e.target.value }))}
              >
                <option value="">—</option>
                {(q.options || []).map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
              </select>
            ) : q.answer_type === "percent" ? (
              <input
                type="number" min="0" max="100"
                className="border border-zinc-300 rounded px-2 py-1 w-20 text-sm"
                value={vals[q.key] ?? ""}
                onChange={(e) => setVals((s) => ({ ...s, [q.key]: Number(e.target.value) }))}
              />
            ) : (
              <input
                className="border border-zinc-300 rounded px-2 py-1 text-sm"
                value={vals[q.key] || ""}
                onChange={(e) => setVals((s) => ({ ...s, [q.key]: e.target.value }))}
              />
            )}
            <Button size="sm" onClick={() => save(q)} disabled={busy[q.key]} className="rounded-sm bg-zinc-950 hover:bg-zinc-800" data-testid={`q-save-${doc.document_id}-${q.key}`}>
              {busy[q.key] ? "…" : "Save"}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
