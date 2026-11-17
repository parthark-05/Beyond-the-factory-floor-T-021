"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import TelemetryPanels, {
  FactoryState,
} from "@/components/TelemetryPanels";
import FactoryFlow from "@/components/FactoryFlow";

const API_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function DashboardPage() {
  const [factory, setFactory] = useState<FactoryState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [injecting, setInjecting] = useState(false);
  const [message, setMessage] = useState("");

  // Get the latest factory information
  const fetchFactoryState = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/factory-state`,
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status}`);
      }

      const data: FactoryState = await response.json();

      setFactory(data);
      setError("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to backend"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll backend every 2 seconds
  useEffect(() => {
    fetchFactoryState();

    const interval = setInterval(() => {
      fetchFactoryState();
    }, 2000);

    return () => clearInterval(interval);
  }, [fetchFactoryState]);

  // Inject a simulated fault
  async function injectFault(fault: string) {
    setInjecting(true);
    setMessage("");

    try {
      const response = await fetch(
        `${API_URL}/api/inject-fault`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ fault }),
        }
      );

      if (!response.ok) {
        throw new Error(`Fault injection failed: ${response.status}`);
      }

      const result = await response.json();

      setMessage(result.message || "Fault injected successfully");

      // Immediately refresh the dashboard
      await fetchFactoryState();
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Request failed"
      );
    } finally {
      setInjecting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#080d18] text-white p-4 md:p-8">

      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            SmartFactory AI
          </h1>
          <p className="text-slate-400 mt-1">
            Car Manufacturing Intelligence Dashboard
          </p>
        </div>

        <div className="flex items-center gap-2 text-sm text-green-400">
          <Activity size={18} />
          Digital Twin Monitoring
        </div>
      </header>

      {/* Simulated Data Banner */}
      <section className="border border-blue-500/30 bg-blue-500/10 rounded-xl p-4 mb-6">
        <div className="flex flex-col lg:flex-row justify-between gap-4">
          <div>
            <h2 className="font-semibold text-blue-300">
              SIMULATED DATA — DIGITAL TWIN MODE
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Inject simulated faults to test factory responses.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => injectFault("normal")}
              disabled={injecting}
              className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 disabled:opacity-50 text-sm font-medium"
            >
              Normal
            </button>

            <button
              onClick={() => injectFault("welding")}
              disabled={injecting}
              className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-sm font-medium"
            >
              Inject Welding Fault
            </button>

            <button
              onClick={() => injectFault("bad_sensor")}
              disabled={injecting}
              className="px-4 py-2 rounded-lg bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-sm font-medium"
            >
              Inject Bad Sensor
            </button>
          </div>
        </div>

        {message && (
          <p className="text-sm text-blue-200 mt-3">{message}</p>
        )}
      </section>

      {/* Backend Connection Status */}
      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-red-300">
          <AlertTriangle size={20} />
          <div>
            <p className="font-semibold">Backend connection problem</p>
            <p className="text-sm">{error}</p>
          </div>
          <button
            onClick={fetchFactoryState}
            className="ml-auto"
            aria-label="Retry connection"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      )}

      {loading && !factory ? (
        <div className="text-center py-20 text-slate-400">
          Connecting to factory backend...
        </div>
      ) : factory ? (
        <>
          {/* Main Dashboard Panels */}
          <TelemetryPanels data={factory} />

          {/* Factory Flow */}
          <section className="mt-8">
            <h2 className="text-xl font-semibold mb-4">
              Factory Production Flow
            </h2>

            <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
              <FactoryFlow />
            </div>
          </section>
        </>
      ) : (
        <div className="text-center py-20 text-slate-400">
          No factory data available. Check that your backend is running.
        </div>
      )}

      <footer className="text-center text-xs text-slate-500 mt-10">
        SmartFactory AI | Digital Twin Monitoring System
      </footer>
    </main>
  );
}
