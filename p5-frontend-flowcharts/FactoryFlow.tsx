"use client";

import React, { useState, useMemo } from "react";
import {
  AlertOctagon,
  Zap,
  RotateCcw,
  Activity,
  Thermometer,
  Clock,
  Layers,
  X,
  ArrowRight,
  AlertTriangle,
} from "lucide-react";

export interface MachineNode {
  id: string;
  name: string;
  stage: string;
  cycle_time: number;
  target_cycle: number;
  temp: number;
  vibration: number;
  sensor_health: "OK" | "FAULTY";
  pass_fail: "PASS" | "FAIL";
}

export interface BufferBar {
  id: string;
  name: string;
  from_stage: string;
  to_stage: string;
  level: number;
  capacity: number;
  fill_percent: number;
}

interface FactoryFlowProps {
  machines?: MachineNode[];
  buffers?: BufferBar[];
  faultMode?: string;
  onInjectFault?: (mode: "none" | "welding_fault" | "bad_sensor") => void;
  onSelectMachine?: (machine: MachineNode) => void;
}

// Built-in standalone simulator data so P5 renders & works interactively even before backend connects
const DEFAULT_MACHINES: MachineNode[] = [
  { id: "M01", name: "Blanking Press", stage: "Stamping", cycle_time: 42.1, target_cycle: 42.0, temp: 58.0, vibration: 2.1, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M02", name: "Deep Draw Press", stage: "Stamping", cycle_time: 45.2, target_cycle: 45.0, temp: 64.0, vibration: 2.6, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M03", name: "Trim & Pierce", stage: "Stamping", cycle_time: 43.0, target_cycle: 43.0, temp: 60.0, vibration: 2.3, sensor_health: "OK", pass_fail: "PASS" },

  { id: "M04", name: "Underbody Welder", stage: "Body Welding", cycle_time: 48.3, target_cycle: 48.0, temp: 74.0, vibration: 3.0, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M05", name: "Left Framing Robot", stage: "Body Welding", cycle_time: 50.1, target_cycle: 50.0, temp: 76.0, vibration: 3.2, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M06", name: "Right Framing Robot", stage: "Body Welding", cycle_time: 49.8, target_cycle: 50.0, temp: 75.0, vibration: 3.1, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M07", name: "Roof Laser Welder", stage: "Body Welding", cycle_time: 49.0, target_cycle: 49.0, temp: 79.0, vibration: 2.9, sensor_health: "OK", pass_fail: "PASS" },

  { id: "M08", name: "E-Coat Dip Tank", stage: "Paint Shop", cycle_time: 52.0, target_cycle: 52.0, temp: 42.0, vibration: 1.1, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M09", name: "Primer Spray Booth", stage: "Paint Shop", cycle_time: 54.1, target_cycle: 54.0, temp: 36.0, vibration: 1.4, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M10", name: "Clear Coat Robot", stage: "Paint Shop", cycle_time: 55.0, target_cycle: 55.0, temp: 38.0, vibration: 1.5, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M11", name: "Curing Oven", stage: "Paint Shop", cycle_time: 53.2, target_cycle: 53.0, temp: 145.0, vibration: 1.2, sensor_health: "OK", pass_fail: "PASS" },

  { id: "M12", name: "Engine Decking", stage: "Powertrain Assembly", cycle_time: 56.1, target_cycle: 56.0, temp: 52.0, vibration: 2.4, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M13", name: "Transmission Mate", stage: "Powertrain Assembly", cycle_time: 55.0, target_cycle: 55.0, temp: 50.0, vibration: 2.2, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M14", name: "Axle & Suspension", stage: "Powertrain Assembly", cycle_time: 54.2, target_cycle: 54.0, temp: 48.0, vibration: 2.7, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M15", name: "Battery & Fluid Fill", stage: "Powertrain Assembly", cycle_time: 52.0, target_cycle: 52.0, temp: 44.0, vibration: 1.8, sensor_health: "OK", pass_fail: "PASS" },

  { id: "M16", name: "Alignment & Dyno", stage: "Final QA", cycle_time: 48.0, target_cycle: 48.0, temp: 46.0, vibration: 2.5, sensor_health: "OK", pass_fail: "PASS" },
  { id: "M17", name: "3D Vision & Leak QA", stage: "Final QA", cycle_time: 46.1, target_cycle: 46.0, temp: 32.0, vibration: 1.0, sensor_health: "OK", pass_fail: "PASS" },
];

const DEFAULT_BUFFERS: BufferBar[] = [
  { id: "BUF-1", name: "Stamping → Welding", from_stage: "Stamping", to_stage: "Body Welding", level: 4, capacity: 20, fill_percent: 20 },
  { id: "BUF-2", name: "Welding → Paint", from_stage: "Body Welding", to_stage: "Paint Shop", level: 5, capacity: 20, fill_percent: 25 },
  { id: "BUF-3", name: "Paint → Powertrain", from_stage: "Paint Shop", to_stage: "Powertrain Assembly", level: 4, capacity: 20, fill_percent: 20 },
  { id: "BUF-4", name: "Powertrain → QA", from_stage: "Powertrain Assembly", to_stage: "Final QA", level: 3, capacity: 20, fill_percent: 15 },
  { id: "BUF-5", name: "QA → Dispatch", from_stage: "Final QA", to_stage: "Dispatch", level: 2, capacity: 20, fill_percent: 10 },
];

const STAGES = [
  "Stamping",
  "Body Welding",
  "Paint Shop",
  "Powertrain Assembly",
  "Final QA",
];

export default function FactoryFlow({
  machines: propMachines,
  buffers: propBuffers,
  faultMode: propFaultMode,
  onInjectFault,
  onSelectMachine,
}: FactoryFlowProps) {
  // Local fallback state so "Inject Fault" buttons work immediately during standalone testing
  const [localFault, setLocalFault] = useState<"none" | "welding_fault" | "bad_sensor">("none");
  const [selectedMachine, setSelectedMachine] = useState<MachineNode | null>(null);

  const activeFault = propFaultMode ?? localFault;

  const handleFaultClick = (mode: "none" | "welding_fault" | "bad_sensor") => {
    setLocalFault(mode);
    if (onInjectFault) onInjectFault(mode);
  };

  // Apply local simulated fault effects if parent hasn't passed live backend props yet
  const machines = useMemo(() => {
    if (propMachines && propMachines.length > 0) return propMachines;

    return DEFAULT_MACHINES.map((m) => {
      if (localFault === "welding_fault" && m.id === "M05") {
        return {
          ...m,
          cycle_time: 84.5,
          temp: 102.5,
          vibration: 6.3,
          pass_fail: "FAIL" as const,
        };
      }
      if (localFault === "welding_fault" && m.stage === "Stamping") {
        // Upstream stage gets worried/blocked due to buffer buildup
        return { ...m, cycle_time: m.target_cycle + 6.5 };
      }
      if (localFault === "bad_sensor" && m.id === "M10") {
        return {
          ...m,
          temp: 412.5,
          vibration: 29.8,
          sensor_health: "FAULTY" as const,
        };
      }
      return m;
    });
  }, [propMachines, localFault]);

  const buffers = useMemo(() => {
    if (propBuffers && propBuffers.length > 0) return propBuffers;
    if (localFault === "welding_fault") {
      return DEFAULT_BUFFERS.map((b) =>
        b.id === "BUF-1"
          ? { ...b, level: 18, fill_percent: 90 }
          : b.id === "BUF-2"
          ? { ...b, level: 1, fill_percent: 5 }
          : b
      );
    }
    return DEFAULT_BUFFERS;
  }, [propBuffers, localFault]);

  // Identify the slowest machine (highest cycle_time / target_cycle ratio > 1.15)
  const bottleneckId = useMemo(() => {
    let slowestId: string | null = null;
    let highestRatio = 1.15;
    for (const m of machines) {
      const ratio = m.cycle_time / m.target_cycle;
      if (ratio > highestRatio) {
        highestRatio = ratio;
        slowestId = m.id;
      }
    }
    return slowestId;
  }, [machines]);

  // Determine Green (Healthy), Orange (Worried), or Red (Broken)
  const getMachineHealth = (m: MachineNode) => {
    const ratio = m.cycle_time / m.target_cycle;
    if (m.id === bottleneckId || ratio >= 1.35 || m.pass_fail === "FAIL") {
      return {
        label: "BROKEN",
        border: "border-red-500",
        bg: "bg-red-950/50",
        badge: "bg-red-500 text-white",
        dot: "bg-red-500",
      };
    }
    if (m.sensor_health === "FAULTY" || ratio >= 1.12) {
      return {
        label: "WORRIED",
        border: "border-amber-500",
        bg: "bg-amber-950/40",
        badge: "bg-amber-500 text-slate-950",
        dot: "bg-amber-400",
      };
    }
    return {
      label: "HEALTHY",
      border: "border-emerald-500/80",
      bg: "bg-emerald-950/30",
      badge: "bg-emerald-500/20 text-emerald-300",
      dot: "bg-emerald-400",
    };
  };

  const handleCardClick = (machine: MachineNode) => {
    setSelectedMachine(machine);
    if (onSelectMachine) onSelectMachine(machine);
  };

  return (
    <div className="w-full bg-slate-950 text-slate-100 rounded-2xl border border-slate-800 p-5 shadow-xl">
      {/* Top Bar with High-Visibility "Inject Fault" Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-5 mb-6 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-sky-400" />
            Live Automobile Assembly Line Map (17 Machines • 5 Buffers)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Tap any machine box to inspect live telemetry • Bars between stages show waiting parts
          </p>
        </div>

        {/* Prominent Inject Fault Controls */}
        <div className="flex flex-wrap items-center gap-2 bg-slate-900 p-2 rounded-xl border border-slate-700">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-2">
            Test Controls:
          </span>
          <button
            onClick={() => handleFaultClick("welding_fault")}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
              activeFault === "welding_fault"
                ? "bg-red-600 text-white ring-2 ring-red-400"
                : "bg-red-600/20 text-red-300 border border-red-500/50 hover:bg-red-600 hover:text-white"
            }`}
          >
            <Zap className="w-4 h-4" />
            Inject Welding Fault
          </button>

          <button
            onClick={() => handleFaultClick("bad_sensor")}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
              activeFault === "bad_sensor"
                ? "bg-amber-500 text-slate-950 ring-2 ring-amber-300"
                : "bg-amber-500/20 text-amber-300 border border-amber-500/50 hover:bg-amber-500 hover:text-slate-950"
            }`}
          >
            <AlertTriangle className="w-4 h-4" />
            Inject Bad Sensor
          </button>

          <button
            onClick={() => handleFaultClick("none")}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeFault === "none"
                ? "bg-emerald-600 text-white"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset Healthy
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-5 text-xs text-slate-300 mb-5">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block" /> Healthy Machine
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-amber-500 inline-block" /> Worried / Blocked / Bad Sensor
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-red-500 inline-block" /> Broken / Faulty
        </span>
        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-rose-600/30 border border-rose-500 text-rose-200 font-semibold">
          <AlertOctagon className="w-3.5 h-3.5 text-rose-400" /> SLOWEST / BOTTLENECK
        </span>
      </div>

      {/* Horizontal Flowchart: 5 Stages + Arrows + Waiting Parts Buffer Bars */}
      <div className="overflow-x-auto pb-4">
        <div className="flex items-stretch gap-3 min-w-[1150px]">
          {STAGES.map((stageName, stageIdx) => {
            const stageMachines = machines.filter((m) => m.stage === stageName);
            const bufferAfter = buffers[stageIdx]; // Buffer connecting this stage to the next

            return (
              <React.Fragment key={stageName}>
                {/* Stage Column of Machine Boxes */}
                <div className="flex-1 bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 pb-2 border-b border-slate-800 flex justify-between">
                    <span>
                      {stageIdx + 1}. {stageName}
                    </span>
                    <span className="text-slate-500">{stageMachines.length} units</span>
                  </div>

                  <div className="space-y-2.5 flex-1">
                    {stageMachines.map((machine) => {
                      const health = getMachineHealth(machine);
                      const isSlowest = machine.id === bottleneckId;
                      const isSelected = selectedMachine?.id === machine.id;

                      return (
                        <button
                          key={machine.id}
                          onClick={() => handleCardClick(machine)}
                          className={`w-full text-left p-3 rounded-xl border-2 transition-all cursor-pointer relative ${
                            health.border
                          } ${health.bg} ${
                            isSelected ? "ring-2 ring-sky-400 scale-[1.02]" : "hover:brightness-110"
                          }`}
                        >
                          {/* Special Mark for the Slowest Machine */}
                          {isSlowest && (
                            <div className="mb-1.5 inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-600 text-white text-[10px] font-extrabold tracking-wide animate-pulse">
                              <AlertOctagon className="w-3 h-3" />
                              SLOWEST MACHINE (BOTTLENECK)
                            </div>
                          )}

                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold text-white truncate">
                              {machine.id} • {machine.name}
                            </span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${health.badge}`}>
                              {health.label}
                            </span>
                          </div>

                          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-300">
                            <span>
                              Speed: <strong>{machine.cycle_time}s</strong>{" "}
                              <span className="text-slate-500">/ {machine.target_cycle}s</span>
                            </span>
                            <span>{machine.temp}°C</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Arrow + Little Buffer Bar Between Stages Showing Waiting Parts */}
                {bufferAfter && (
                  <div className="w-24 flex flex-col items-center justify-center shrink-0 px-1">
                    <div className="text-[10px] font-semibold text-slate-400 text-center mb-1">
                      Waiting Parts
                    </div>

                    {/* Little Vertical/Horizontal Buffer Bar */}
                    <div className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 flex flex-col items-center">
                      <div className="text-xs font-bold text-white mb-1">
                        {bufferAfter.level}/{bufferAfter.capacity}
                      </div>
                      <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 ${
                            bufferAfter.fill_percent >= 75
                              ? "bg-red-500"
                              : bufferAfter.fill_percent >= 50
                              ? "bg-amber-400"
                              : "bg-sky-400"
                          }`}
                          style={{ width: `${bufferAfter.fill_percent}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-slate-400 mt-1">
                        {bufferAfter.fill_percent}% full
                      </span>
                    </div>

                    {/* Connecting Flow Arrow */}
                    <div className="my-2 flex items-center justify-center">
                      <ArrowRight
                        className={`w-6 h-6 ${
                          bufferAfter.fill_percent >= 75
                            ? "text-red-500 animate-bounce"
                            : "text-sky-400"
                        }`}
                      />
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Clickable Machine Detail Drawer / Panel */}
      {selectedMachine && (
        <div className="mt-4 bg-slate-900 border border-sky-500/50 rounded-xl p-4 animate-fadeIn">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
            <div>
              <span className="text-xs uppercase tracking-wider text-sky-400 font-bold">
                Machine Inspector • {selectedMachine.stage}
              </span>
              <h3 className="text-base font-bold text-white">
                {selectedMachine.id} — {selectedMachine.name}
              </h3>
            </div>
            <button
              onClick={() => setSelectedMachine(null)}
              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white cursor-pointer"
              aria-label="Close machine details"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-400 flex items-center gap-1 mb-1">
                <Clock className="w-3.5 h-3.5 text-sky-400" /> Last Car Cycle Time
              </div>
              <div className="text-lg font-bold text-white">
                {selectedMachine.cycle_time}s{" "}
                <span className="text-xs font-normal text-slate-500">
                  (Target {selectedMachine.target_cycle}s)
                </span>
              </div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-400 flex items-center gap-1 mb-1">
                <Thermometer className="w-3.5 h-3.5 text-rose-400" /> Core Temperature
              </div>
              <div className="text-lg font-bold text-white">{selectedMachine.temp}°C</div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-400 flex items-center gap-1 mb-1">
                <Activity className="w-3.5 h-3.5 text-amber-400" /> Vibration & Sensor
              </div>
              <div className="text-lg font-bold text-white">
                {selectedMachine.vibration} mm/s{" "}
                <span
                  className={`text-xs px-1.5 py-0.5 rounded ml-1 ${
                    selectedMachine.sensor_health === "OK"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "bg-amber-500/20 text-amber-300"
                  }`}
                >
                  {selectedMachine.sensor_health}
                </span>
              </div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-400 mb-1">Last Car Quality Output</div>
              <div
                className={`text-lg font-bold ${
                  selectedMachine.pass_fail === "PASS" ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {selectedMachine.pass_fail === "PASS" ? "GOOD (PASS)" : "BROKEN (FAIL)"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}