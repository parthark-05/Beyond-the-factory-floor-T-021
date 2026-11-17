"use client";

import React, { useState, useEffect } from "react";
import { Wrench, CheckSquare, Square, PlayCircle, Clock, TrendingUp, CheckCircle2 } from "lucide-react";

export interface PlaybookData {
  playbook_id: string;
  title: string;
  target_machine: string;
  urgency: string;
  estimated_recovery_mins: number;
  expected_oee_gain: string;
  steps: string[];
}

interface ActionPlaybookProps {
  playbook?: PlaybookData | null;
  onExecuteFix?: () => void;
}

export default function ActionPlaybook({ playbook, onExecuteFix }: ActionPlaybookProps) {
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);
  const [applied, setApplied] = useState(false);

  // Reset checklist whenever a new playbook appears
  useEffect(() => {
    setCompletedSteps([]);
    setApplied(false);
  }, [playbook?.playbook_id]);

  if (!playbook) {
    return (
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 text-xs text-slate-400 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        No corrective playbook required. All assembly stages are operating within target cycle times.
      </div>
    );
  }

  const toggleStep = (index: number) => {
    setCompletedSteps((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  };

  const handleApplyFix = () => {
    setCompletedSteps(playbook.steps.map((_, idx) => idx));
    setApplied(true);
    if (onExecuteFix) {
      onExecuteFix(); // Calls backend to reset fault_mode to "none"
    }
  };

  return (
    <div className="bg-slate-900 border border-indigo-500/50 rounded-xl p-5 shadow-lg">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-800 pb-3 mb-4">
        <div>
          <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-indigo-400">
            <Wrench className="w-3.5 h-3.5" /> Prescriptive Action Playbook • {playbook.playbook_id}
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">{playbook.title}</h3>
          <p className="text-xs text-slate-400">Target Station: {playbook.target_machine}</p>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="flex items-center gap-1 bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-lg text-slate-300">
            <Clock className="w-3.5 h-3.5 text-sky-400" /> ~{playbook.estimated_recovery_mins} mins
          </span>
          <span className="flex items-center gap-1 bg-emerald-950/60 border border-emerald-800 px-2.5 py-1 rounded-lg text-emerald-300 font-semibold">
            <TrendingUp className="w-3.5 h-3.5" /> {playbook.expected_oee_gain}
          </span>
        </div>
      </div>

      {/* Interactive SOP Checklist */}
      <div className="space-y-2 mb-4">
        {playbook.steps.map((step, idx) => {
          const isDone = completedSteps.includes(idx);
          return (
            <button
              key={idx}
              onClick={() => toggleStep(idx)}
              className={`w-full text-left flex items-start gap-2.5 p-2.5 rounded-lg border text-xs transition cursor-pointer ${
                isDone
                  ? "bg-emerald-950/30 border-emerald-800/70 text-slate-300 line-through opacity-80"
                  : "bg-slate-950 border-slate-800 text-slate-200 hover:border-slate-700"
              }`}
            >
              {isDone ? (
                <CheckSquare className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <Square className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
              )}
              <span>
                <strong className="text-indigo-300 mr-1">Step {idx + 1}:</strong>
                {step}
              </span>
            </button>
          );
        })}
      </div>

      {/* One-Click Execution Button */}
      <button
        onClick={handleApplyFix}
        className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs py-2.5 px-4 rounded-lg transition cursor-pointer"
      >
        <PlayCircle className="w-4 h-4" />
        {applied ? "Playbook Executed — Restoring Line Flow..." : "Execute Playbook & Resolve Disruption"}
      </button>
    </div>
  );
}