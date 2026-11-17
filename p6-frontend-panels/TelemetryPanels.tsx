"use client";

import React from "react";
import {
  Activity,
  AlertTriangle,
  Car,
  CheckCircle2,
  Cpu,
  Radio,
  SearchCheck,
  ShieldAlert,
  TrendingUp,
  XCircle,
} from "lucide-react";
import ActionPlaybook, { PlaybookData } from "./ActionPlaybook";

export interface MachineMetric {
  id: string;
  name: string;
  stage: string;
  cycle_time: number;
  target_cycle: number;
  temp: number;
  vibration: number;
  sensor_health: "OK" | "FAULTY";
  pass_fail: "PASS" | "FAIL";
  history?: number[]; // Recent cycle times for the mini graph
}

export interface AlertItem {
  alert_id: string;
  machine_id: string;
  severity: "WARNING" | "CRITICAL";
  type: string;
  message: string;
}

export interface CarLog {
  car_id: string;
  timestamp: string;
  status: "PASS" | "FAIL";
  failed_at: { machine_id: string; machine_name: string; reason: string }[];
}

export interface DetectiveRCA {
  primary_cause: string;
  confidence: "CONFIRMED" | "INFERRED";
  explanation: string;
  who_gets_hit_next: string;
  playbook?: PlaybookData | null;
}

interface TelemetryPanelsProps {
  machines: MachineMetric[];
  selectedMachine: MachineMetric | null;
  carsBuilt: number;
  factoryEfficiency: number;
  alerts: AlertItem[];
  recentCars: CarLog[];
  rca: DetectiveRCA | null;
  onExecuteFix?: () => void;
}

export default function TelemetryPanels({
  machines,
  selectedMachine,
  carsBuilt,
  factoryEfficiency,
  alerts,
  recentCars,
  rca,
  onExecuteFix,
}: TelemetryPanelsProps) {
  const runningCount = machines.filter((m) => m.sensor_health === "OK").length;
  const brokenCars = recentCars.filter((c) => c.status === "FAIL");
  const inspectedMachine = selectedMachine || machines[0] || null;

  // Fallback mini-graph history if backend hasn't supplied a history array yet
  const graphPoints = inspectedMachine?.history || [
    inspectedMachine?.target_cycle || 50,
    (inspectedMachine?.target_cycle || 50) + 1.2,
    (inspectedMachine?.target_cycle || 50) - 0.8,
    (inspectedMachine?.target_cycle || 50) + 2.5,
    inspectedMachine?.cycle_time || 50,
  ];
  const maxVal = Math.max(...graphPoints, 100);

  return (
    <div className="w-full bg-slate-950 text-slate-100 space-y-5 font-sans">
      {/* 1. Prominent Control Room "Simulated Data" Banner */}
      <div className="bg-amber-500/10 border border-amber-500/40 rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-amber-300 text-xs font-bold tracking-wider uppercase">
          <Radio className="w-4 h-4 text-amber-400 animate-pulse" />
          SIMULATED DATA — DIGITAL TWIN CONTROL ROOM (NOT LIVE FACTORY HARDWARE)
        </div>
        <span className="text-[11px] text-slate-400">
          Telemetry Refresh: 2.0s • Assembly Line T-021
        </span>
      </div>

      {/* 2. Top Summary Strip: Machines Running, Cars Made, Factory Efficiency */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-slate-400 block">
              Machines Running
            </span>
            <span className="text-2xl font-extrabold text-white mt-1 block">
              {runningCount}{" "}
              <span className="text-sm font-normal text-slate-500">/ {machines.length} active</span>
            </span>
          </div>
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
            <Cpu className="w-6 h-6 text-emerald-400" />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-slate-400 block">
              Total Cars Built
            </span>
            <span className="text-2xl font-extrabold text-white mt-1 block">
              {carsBuilt}{" "}
              <span className="text-xs font-medium text-rose-400 ml-1">
                ({brokenCars.length} defective)
              </span>
            </span>
          </div>
          <div className="p-3 rounded-xl bg-sky-500/10 border border-sky-500/30">
            <Car className="w-6 h-6 text-sky-400" />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-slate-400 block">
              Factory Efficiency (OEE)
            </span>
            <span
              className={`text-2xl font-extrabold mt-1 block ${
                factoryEfficiency < 75 ? "text-red-400" : "text-emerald-400"
              }`}
            >
              {factoryEfficiency}%
            </span>
          </div>
          <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/30">
            <TrendingUp className="w-6 h-6 text-indigo-400" />
          </div>
        </div>
      </div>

      {/* 3. Main Control Room Information Boards (4-Panel Grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Panel A: Single Machine Page with Mini Performance Graph */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Activity className="w-4 h-4 text-sky-400" /> Machine Detail & Cycle Trend
              </h3>
              {inspectedMachine && (
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-sky-300 font-semibold">
                  {inspectedMachine.stage}
                </span>
              )}
            </div>

            {inspectedMachine ? (
              <>
                <div className="flex justify-between items-baseline mb-4">
                  <div className="text-lg font-bold text-white">
                    {inspectedMachine.id} — {inspectedMachine.name}
                  </div>
                  <div className="text-xs text-slate-400">
                    Temp: <strong className="text-slate-200">{inspectedMachine.temp}°C</strong> • Vib:{" "}
                    <strong className="text-slate-200">{inspectedMachine.vibration} mm/s</strong>
                  </div>
                </div>

                {/* Little Bar Graph of Recent Cycle Times */}
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                  <div className="flex justify-between text-[11px] text-slate-400 mb-2">
                    <span>Recent Car Cycle Times (Seconds)</span>
                    <span>Target: {inspectedMachine.target_cycle}s</span>
                  </div>
                  <div className="h-28 flex items-end gap-2 pt-2">
                    {graphPoints.map((val, idx) => {
                      const heightPct = Math.min(100, Math.round((val / maxVal) * 100));
                      const isSlow = val > inspectedMachine.target_cycle * 1.15;
                      return (
                        <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                          <span className="text-[10px] text-slate-400">{val}s</span>
                          <div className="w-full bg-slate-900 rounded-t h-20 flex items-end">
                            <div
                              className={`w-full rounded-t transition-all duration-300 ${
                                isSlow ? "bg-red-500" : "bg-sky-500"
                              }`}
                              style={{ height: `${heightPct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <p className="text-xs text-slate-400">Click any machine in the flowchart to inspect.</p>
            )}
          </div>
        </div>

        {/* Panel B: Live Alerts List */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" /> Active Alerts & Sensor Warnings
            </h3>
            <span className="text-xs bg-slate-800 px-2 py-0.5 rounded-full text-slate-300">
              {alerts.length}
            </span>
          </div>

          {alerts.length === 0 ? (
            <div className="bg-emerald-950/30 border border-emerald-900/60 rounded-lg p-4 text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              No active warnings. All 17 machines and sensors reporting nominal telemetry.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-52 overflow-y-auto pr-1">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  className={`p-3 rounded-lg border text-xs ${
                    alert.severity === "CRITICAL"
                      ? "bg-red-950/40 border-red-800 text-red-200"
                      : "bg-amber-950/40 border-amber-800 text-amber-200"
                  }`}
                >
                  <div className="flex justify-between font-bold uppercase text-[11px] mb-1">
                    <span>
                      [{alert.severity}] {alert.machine_id}
                    </span>
                    <span>{alert.type}</span>
                  </div>
                  <p className="opacity-90">{alert.message}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Panel C: Broken Cars Quality Log */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <XCircle className="w-4 h-4 text-rose-400" /> Broken Cars & Defect Trace
            </h3>
            <span className="text-xs text-rose-400 font-semibold">
              {brokenCars.length} Flagged
            </span>
          </div>

          {brokenCars.length === 0 ? (
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 text-xs text-slate-400">
              100% Quality Pass Rate — zero defective vehicles detected in recent batch.
            </div>
          ) : (
            <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
              {brokenCars.map((car) => (
                <div
                  key={car.car_id}
                  className="bg-slate-950 border border-rose-900/50 rounded-lg p-3 text-xs flex justify-between items-start gap-2"
                >
                  <div>
                    <span className="font-bold text-rose-300">{car.car_id}</span>
                    <span className="text-slate-500 ml-2">{car.timestamp}</span>
                    <div className="text-slate-300 mt-1">
                      {car.failed_at.map((f) => `${f.machine_id} (${f.reason})`).join(", ")}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-bold text-[10px]">
                    BROKEN
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Panel D: The Detective's Answer (Root Cause Analysis + Action Playbook) */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <SearchCheck className="w-4 h-4 text-indigo-400" /> Detective&apos;s Root Cause Diagnosis
            </h3>
            {rca && (
              <span
                className={`text-[10px] font-extrabold px-2 py-0.5 rounded ${
                  rca.confidence === "CONFIRMED"
                    ? "bg-rose-500 text-white"
                    : "bg-amber-400 text-slate-950"
                }`}
              >
                {rca.confidence}
              </span>
            )}
          </div>

          {rca ? (
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3.5 text-xs space-y-2">
              <div>
                <span className="text-slate-400">True Origin: </span>
                <strong className="text-rose-400">{rca.primary_cause}</strong>
              </div>
              <p className="text-slate-300">{rca.explanation}</p>
              <div className="text-amber-300 flex items-center gap-1.5 pt-1">
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>Cascade Warning: {rca.who_gets_hit_next}</span>
              </div>
            </div>
          ) : (
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3.5 text-xs text-slate-400">
              Factory line is balanced. No hidden slowdowns or cascading bottlenecks detected.
            </div>
          )}

          {/* Embedded Prescriptive Action Playbook */}
          <ActionPlaybook playbook={rca?.playbook} onExecuteFix={onExecuteFix} />
        </div>
      </div>
    </div>
  );
}