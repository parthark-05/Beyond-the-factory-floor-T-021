
"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  Factory,
  Lightbulb,
  ShieldAlert,
  TrendingDown,
  Wrench,
  XCircle,
} from "lucide-react";

export interface FactoryState {
  oee: number;
  total_cars_built: number;
  pass_rate: number;
  fail_rate: number;
  active_bottleneck: string;
  next_predicted_impact: number;

  alerts: {
    id: string;
    message: string;
    severity: "WARNING" | "CRITICAL";
    machine?: string;
    type?: string;
  }[];

  quality: {
    passed: number;
    failed: number;
    defects: {
      machine: string;
      defect: string;
      count: number;
    }[];
  };

  root_causes: {
    cause: string;
    confidence: string;
    affected_department: string;
    impact_time: string;
    advice: string;
  }[];
}

interface Props {
  data: FactoryState;
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
      <div className="flex justify-between items-center">
        <p className="text-sm text-slate-400">{title}</p>
        <Icon className={color} size={20} />
      </div>

      <h2 className="text-2xl font-bold mt-3">{value}</h2>
    </div>
  );
}

export default function TelemetryPanels({ data }: Props) {
  const passRate = Number(data.pass_rate) || 0;
  const failRate = Number(data.fail_rate) || 0;

  return (
    <div className="space-y-8">

      {/* Summary Dashboard */}
      <section>
        <h2 className="text-xl font-semibold mb-4">
          Factory Performance Summary
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">

          <StatCard
            title="Line OEE"
            value={`${data.oee ?? 0}%`}
            icon={Activity}
            color="text-green-400"
          />

          <StatCard
            title="Total Cars Built"
            value={String(data.total_cars_built ?? 0)}
            icon={Factory}
            color="text-blue-400"
          />

          <StatCard
            title="Pass Rate"
            value={`${passRate}%`}
            icon={CheckCircle}
            color="text-green-400"
          />

          <StatCard
            title="Active Bottleneck"
            value={data.active_bottleneck || "None"}
            icon={TrendingDown}
            color="text-yellow-400"
          />

          <StatCard
            title="Predicted Impact"
            value={`${data.next_predicted_impact ?? 0} min`}
            icon={Clock}
            color="text-orange-400"
          />

        </div>
      </section>

      {/* Three Monitoring Panels */}
      <section>
        <h2 className="text-xl font-semibold mb-4">
          Factory Intelligence Panels
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

          {/* Alerts Panel */}
          <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
            <div className="flex items-center gap-2 mb-5">
              <AlertTriangle className="text-yellow-400" />
              <h3 className="font-semibold text-lg">Machine Alerts</h3>
            </div>

            <div className="space-y-3">
              {data.alerts?.length ? (
                data.alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="border border-slate-700 rounded-lg p-3"
                  >
                    <div className="flex justify-between gap-2 mb-2">
                      <span className="text-xs text-slate-400">
                        {alert.machine || "Factory System"}
                      </span>

                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          alert.severity === "CRITICAL"
                            ? "bg-red-500/20 text-red-400"
                            : "bg-yellow-500/20 text-yellow-400"
                        }`}
                      >
                        {alert.severity}
                      </span>
                    </div>

                    <p className="text-sm">{alert.message}</p>

                    {alert.type && (
                      <p className="text-xs text-slate-500 mt-2">
                        Type: {alert.type}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  No active machine alerts.
                </p>
              )}
            </div>
          </div>

          {/* Product Quality Panel */}
          <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
            <div className="flex items-center gap-2 mb-5">
              <ShieldAlert className="text-blue-400" />
              <h3 className="font-semibold text-lg">
                Product Quality
              </h3>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-green-500/10 rounded-lg p-3">
                <CheckCircle className="text-green-400 mb-2" />
                <p className="text-2xl font-bold">
                  {data.quality?.passed ?? 0}
                </p>
                <p className="text-xs text-slate-400">Cars Passed</p>
              </div>

              <div className="bg-red-500/10 rounded-lg p-3">
                <XCircle className="text-red-400 mb-2" />
                <p className="text-2xl font-bold">
                  {data.quality?.failed ?? 0}
                </p>
                <p className="text-xs text-slate-400">Cars Failed</p>
              </div>
            </div>

            <p className="text-sm text-slate-400 mb-3">
              Defect-to-machine trace
            </p>

            <div className="space-y-3">
              {data.quality?.defects?.length ? (
                data.quality.defects.map((item, index) => (
                  <div
                    key={`${item.machine}-${index}`}
                    className="border-b border-slate-800 pb-2"
                  >
                    <p className="text-sm font-medium">
                      {item.machine}
                    </p>
                    <p className="text-xs text-slate-400">
                      {item.defect} · {item.count} defects
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  No defect records available.
                </p>
              )}
            </div>

            <div className="mt-4 text-xs text-slate-400">
              Pass rate: {passRate}% | Fail rate: {failRate}%
            </div>
          </div>

          {/* Root Cause Panel */}
          <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
            <div className="flex items-center gap-2 mb-5">
              <Lightbulb className="text-purple-400" />
              <h3 className="font-semibold text-lg">
                Root Cause Analysis
              </h3>
            </div>

            <div className="space-y-4">
              {data.root_causes?.length ? (
                data.root_causes.map((cause, index) => (
                  <div
                    key={`${cause.cause}-${index}`}
                    className="border-b border-slate-800 pb-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium">
                        {index + 1}. {cause.cause}
                      </p>

                      <span
                        className={`text-[10px] px-2 py-1 rounded whitespace-nowrap ${
                          cause.confidence === "CONFIRMED"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-purple-500/20 text-purple-400"
                        }`}
                      >
                        {cause.confidence}
                      </span>
                    </div>

                    <p className="text-xs text-slate-400 mt-2">
                      Affected: {cause.affected_department}
                    </p>

                    <p className="text-xs text-yellow-400 mt-1">
                      Impact: {cause.impact_time}
                    </p>

                    <div className="flex gap-2 mt-2">
                      <Wrench
                        size={14}
                        className="text-blue-400 shrink-0"
                      />
                      <p className="text-xs text-slate-300">
                        {cause.advice}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  No root causes identified.
                </p>
              )}
            </div>
          </div>

        </div>
      </section>
    </div>
  );
}
