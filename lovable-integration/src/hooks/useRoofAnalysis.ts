// React hook: kicks off an analysis via analyzeRoofWithRailway, then polls
// getRoofAnalysisJob on an interval until the job completes or fails.
// TeslaMap.tsx would call `runAnalysis({ lat, lng, ... })` from a map click
// handler instead of the local analyzeRoofImpl.
//
// Copy into your Lovable project's src/hooks/.

import { useCallback, useEffect, useRef, useState } from "react";
import { analyzeRoofWithRailway, getRoofAnalysisJob, type AnalyzeInput } from "../lib/railway.functions";

const POLL_INTERVAL_MS = 2500;
const MAX_POLL_MS = 3 * 60 * 1000; // give up after 3 minutes -- something's wrong past that

export type RoofAnalysisState = {
  status: "idle" | "queued" | "processing" | "completed" | "failed";
  progress: number;
  stage: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  jobId: string | null;
};

const initialState: RoofAnalysisState = {
  status: "idle",
  progress: 0,
  stage: null,
  result: null,
  error: null,
  jobId: null,
};

export function useRoofAnalysis() {
  const [state, setState] = useState<RoofAnalysisState>(initialState);
  const pollHandle = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartedAt = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (pollHandle.current !== null) {
      clearInterval(pollHandle.current);
      pollHandle.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]); // cleanup on unmount

  const runAnalysis = useCallback(
    async (input: AnalyzeInput) => {
      stopPolling();
      setState({ ...initialState, status: "queued" });

      let jobId: string;
      try {
        const started = await analyzeRoofWithRailway({ data: input });
        jobId = started.job_id;
        setState((s) => ({ ...s, jobId, status: "queued" }));
      } catch (err) {
        setState((s) => ({ ...s, status: "failed", error: (err as Error).message }));
        return;
      }

      pollStartedAt.current = Date.now();
      pollHandle.current = setInterval(async () => {
        if (Date.now() - pollStartedAt.current > MAX_POLL_MS) {
          stopPolling();
          setState((s) => ({ ...s, status: "failed", error: "Timed out waiting for analysis." }));
          return;
        }

        try {
          const job = await getRoofAnalysisJob({ data: { jobId } });
          setState((s) => ({
            ...s,
            status: job.status,
            progress: job.progress,
            stage: job.stage,
            result: job.result,
            error: job.error,
          }));

          if (job.status === "completed" || job.status === "failed") {
            stopPolling();
          }
        } catch (err) {
          stopPolling();
          setState((s) => ({ ...s, status: "failed", error: (err as Error).message }));
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    setState(initialState);
  }, [stopPolling]);

  return { ...state, runAnalysis, reset };
}
