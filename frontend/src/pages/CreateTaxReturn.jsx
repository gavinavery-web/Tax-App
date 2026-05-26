import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import useTaxYears from "../lib/useTaxYears";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";

const RETURN_TYPES = [
  { value: "personal", label: "Personal" },
  { value: "company", label: "Company (Pty Ltd)" },
  { value: "trust", label: "Trust" },
  { value: "sole_trader", label: "Sole Trader" },
];

export default function CreateTaxReturn() {
  const nav = useNavigate();
  const { active: activeYears } = useTaxYears();
  const [step, setStep] = useState(1);
  const [taxYear, setTaxYear] = useState("");
  const [returnType, setReturnType] = useState("");
  const [entityName, setEntityName] = useState("");
  const [questions, setQuestions] = useState(null);
  const [answers, setAnswers] = useState({});
  const [creating, setCreating] = useState(false);
  const [createdReturnId, setCreatedReturnId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!taxYear && activeYears.length > 0) setTaxYear(activeYears[0].name);
  }, [activeYears]);

  const goToStep2 = () => {
    if (!taxYear || !returnType || !entityName.trim()) {
      setError("Year, type and entity name are all required");
      return;
    }
    setError("");
    setStep(2);
  };

  const createReturnAndLoadQuestions = async () => {
    setCreating(true);
    setError("");
    try {
      const { data: created } = await api.post("/tax-returns", {
        tax_year: taxYear,
        return_type: returnType,
        entity_name: entityName.trim(),
      });
      setCreatedReturnId(created.id);
      const { data: qs } = await api.get(`/tax-returns/${created.id}/profile-questions`);
      setQuestions(qs);
      setStep(3);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to create return");
    } finally {
      setCreating(false);
    }
  };

  const handleAnswer = (key, value) => {
    setAnswers((a) => ({ ...a, [key]: value }));
  };

  const finish = async () => {
    setCreating(true);
    setError("");
    try {
      await api.patch(`/tax-returns/${createdReturnId}`, {
        profile_answers: answers,
        status: "collecting_evidence",
      });
      const { data: gen } = await api.post(`/tax-returns/${createdReturnId}/generate-evidence-checklist`, {});
      toast.success(`Tax return created. ${gen.created} evidence items generated.`);
      nav(`/missing-evidence?return=${createdReturnId}`);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to finalise");
    } finally {
      setCreating(false);
    }
  };

  // Walk through groups → filter visible questions, including conditional follow-ups
  const visibleQuestions = (group) => {
    const out = [];
    for (const q of group.questions) {
      out.push(q);
      if (q.follow_up && answers[q.key] === true && q.follow_up.yes) {
        for (const f of q.follow_up.yes) out.push(f);
      }
      // For "claim_wfh" → if yes, follow-up is wfh_method. Already covered above.
    }
    return out;
  };

  return (
    <div className="p-6 max-w-3xl mx-auto" data-testid="create-tax-return-page">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ fontFamily: "Chivo" }} data-testid="create-tr-title">Create New Tax Return</h1>
        <StepBadge active={step >= 1} done={step > 1} n={1} label="Basics" />
        <StepBadge active={step >= 2} done={step > 2} n={2} label="Confirm" />
        <StepBadge active={step >= 3} done={false} n={3} label="Profile" />
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded text-sm mb-4" data-testid="create-tr-error">{error}</div>}

      {step === 1 && (
        <div className="space-y-4 bg-white border border-zinc-200 rounded-lg p-5" data-testid="create-tr-step-1">
          <div>
            <label className="block text-xs uppercase tracking-wider text-zinc-500 mono mb-1">Tax year</label>
            <select
              className="w-full border border-zinc-300 rounded px-3 py-2 text-sm bg-white"
              value={taxYear}
              onChange={(e) => setTaxYear(e.target.value)}
              data-testid="create-tr-year"
            >
              <option value="">— select —</option>
              {activeYears.map((y) => <option key={y.name} value={y.name}>{y.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wider text-zinc-500 mono mb-1">Return type</label>
            <select
              className="w-full border border-zinc-300 rounded px-3 py-2 text-sm bg-white"
              value={returnType}
              onChange={(e) => setReturnType(e.target.value)}
              data-testid="create-tr-type"
            >
              <option value="">— select —</option>
              {RETURN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wider text-zinc-500 mono mb-1">Entity / name</label>
            <Input value={entityName} onChange={(e) => setEntityName(e.target.value)} placeholder="e.g. Gavin Christie — Personal" data-testid="create-tr-entity" />
          </div>
          <div className="flex justify-end">
            <Button onClick={goToStep2} className="rounded-sm gap-1 bg-zinc-950 hover:bg-zinc-800" data-testid="create-tr-next">
              Next <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4 bg-white border border-zinc-200 rounded-lg p-5" data-testid="create-tr-step-2">
          <div className="text-sm text-zinc-600">Review the return details before creating it:</div>
          <ul className="bg-zinc-50 p-4 rounded text-sm border border-zinc-200 space-y-1.5">
            <li><span className="text-zinc-500 mono mr-2">Year:</span><b>{taxYear}</b></li>
            <li><span className="text-zinc-500 mono mr-2">Type:</span><b>{RETURN_TYPES.find(t => t.value === returnType)?.label || returnType}</b></li>
            <li><span className="text-zinc-500 mono mr-2">Entity:</span><b>{entityName}</b></li>
          </ul>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(1)} className="gap-1" data-testid="create-tr-back-to-1">
              <ArrowLeft className="w-4 h-4" /> Back
            </Button>
            <Button onClick={createReturnAndLoadQuestions} disabled={creating} className="rounded-sm gap-1 bg-zinc-950 hover:bg-zinc-800" data-testid="create-tr-create">
              {creating ? "Creating…" : <>Create &amp; continue <ArrowRight className="w-4 h-4" /></>}
            </Button>
          </div>
        </div>
      )}

      {step === 3 && questions && (
        <div className="space-y-6" data-testid="create-tr-step-3">
          <p className="text-sm text-zinc-600">
            Answer only what applies. We'll use these to build a tailored evidence checklist.
            Skipping a question is the same as "No".
          </p>
          {(questions.groups || []).map((g) => (
            <div key={g.id} className="bg-white border border-zinc-200 rounded-lg p-5" data-testid={`profile-group-${g.id}`}>
              <h2 className="font-semibold mb-3 tracking-tight" style={{ fontFamily: "Chivo" }}>{g.title}</h2>
              <div className="divide-y divide-zinc-100">
                {visibleQuestions(g).map((q) => (
                  <div key={q.key} className="py-2.5">
                    <Question q={q} answer={answers[q.key]} onChange={(v) => handleAnswer(q.key, v)} />
                  </div>
                ))}
              </div>
            </div>
          ))}
          <div className="sticky bottom-4 flex justify-end bg-white/80 backdrop-blur border border-zinc-200 rounded-lg p-3">
            <Button onClick={finish} disabled={creating} className="rounded-sm gap-1 bg-zinc-950 hover:bg-zinc-800" data-testid="create-tr-finish">
              <CheckCircle2 className="w-4 h-4" />
              {creating ? "Generating checklist…" : "Generate evidence checklist & finish"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function StepBadge({ active, done, n, label }) {
  const tone = done ? "bg-emerald-600 text-white border-emerald-600"
    : active ? "bg-zinc-900 text-white border-zinc-900"
    : "bg-white text-zinc-400 border-zinc-300";
  return (
    <div className={`hidden sm:inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border ${tone}`}>
      <span className="font-semibold mono">{n}</span>
      <span>{label}</span>
    </div>
  );
}

function Question({ q, answer, onChange }) {
  if (q.type === "info") return <p className="text-sm text-zinc-500 italic">{q.text}</p>;
  if (q.type === "yes_no") {
    return (
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-zinc-800">{q.text}</span>
        <div className="inline-flex gap-1 shrink-0">
          {[true, false].map((v) => (
            <button
              key={String(v)}
              type="button"
              onClick={() => onChange(v)}
              className={`px-3 py-1 text-sm rounded border min-w-[48px] ${answer === v ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-700 border-zinc-300 hover:border-zinc-500"}`}
              data-testid={`q-${q.key}-${v ? "yes" : "no"}`}
            >
              {v ? "Yes" : "No"}
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (q.type === "single_select") {
    return (
      <div className="flex items-center justify-between gap-3">
        <label className="text-sm text-zinc-800">{q.text}</label>
        <select
          className="border border-zinc-300 rounded px-2 py-1 text-sm bg-white"
          value={answer || ""}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`q-${q.key}`}
        >
          <option value="">—</option>
          {(q.options || []).map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
        </select>
      </div>
    );
  }
  if (q.type === "short_text" || q.type === "list_text") {
    return (
      <div>
        <label className="block text-sm text-zinc-800 mb-1">{q.text}</label>
        <Input value={answer || ""} onChange={(e) => onChange(e.target.value)} data-testid={`q-${q.key}`} />
      </div>
    );
  }
  return null;
}
