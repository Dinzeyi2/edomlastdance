// Server functions that call the Railway RoofAI backend. Field names and
// shapes match backend/app/schemas/analyze.py exactly -- see
// backend/README.md's "API reference" section for the full contract.
//
// Copy this into your Lovable project's src/lib/. Adjust the auth
// middleware import to match your actual setup (this assumes the same
// `requireSupabaseAuth` middleware you sketched).

import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "./auth"; // adjust to your actual path

const RAILWAY_API_URL = process.env["RAILWAY_API_URL"]!; // e.g. https://roofai-web.up.railway.app
const RAILWAY_API_KEY = process.env["RAILWAY_API_KEY"]!; // same secret set on both Railway services

function railwayHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${RAILWAY_API_KEY}`,
  };
}

const analyzeInputSchema = z.object({
  lat: z.number(),
  lng: z.number(),
  address: z.string().optional(),
  compareYear: z.number().optional(),
  resolutionCm: z.number().optional(),
  includeRawTiles: z.boolean().optional(),
});

export type AnalyzeInput = z.infer<typeof analyzeInputSchema>;

// Kicks off an analysis job. Returns immediately with a job_id -- the
// pipeline runs on Railway's worker, not on this request. Pair with
// useRoofAnalysis (src/hooks/useRoofAnalysis.ts) to poll it from the UI.
export const analyzeRoofWithRailway = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input: unknown) => analyzeInputSchema.parse(input))
  .handler(async ({ data, context }) => {
    const res = await fetch(`${RAILWAY_API_URL}/api/v1/analyze/async`, {
      method: "POST",
      headers: railwayHeaders(),
      body: JSON.stringify({
        lat: data.lat,
        lng: data.lng,
        address: data.address,
        user_id: context.userId,
        compare_year: data.compareYear,
        resolution_cm: data.resolutionCm ?? 10,
        include_raw_tiles: data.includeRawTiles ?? true,
      }),
    });

    if (!res.ok) {
      throw new Error(`Railway analyze/async failed: ${res.status} ${await res.text()}`);
    }

    // { job_id, status, estimated_seconds }
    return (await res.json()) as {
      job_id: string;
      status: string;
      estimated_seconds: number;
    };
  });

const jobStatusInputSchema = z.object({ jobId: z.string() });

// One poll of GET /jobs/{id}. The hook in useRoofAnalysis.ts calls this on
// an interval until status is "completed" or "failed".
export const getRoofAnalysisJob = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input: unknown) => jobStatusInputSchema.parse(input))
  .handler(async ({ data }) => {
    const res = await fetch(`${RAILWAY_API_URL}/api/v1/jobs/${data.jobId}`, {
      headers: railwayHeaders(),
    });

    if (res.status === 404) {
      throw new Error(`Unknown job: ${data.jobId}`);
    }
    if (!res.ok) {
      throw new Error(`Railway jobs poll failed: ${res.status} ${await res.text()}`);
    }

    // { job_id, status, progress, stage, result, error }
    // `result`, when present, matches AnalysisResult exactly -- see
    // backend/app/schemas/analyze.py.
    return (await res.json()) as {
      job_id: string;
      status: "queued" | "processing" | "completed" | "failed";
      progress: number;
      stage: string | null;
      result: Record<string, unknown> | null;
      error: string | null;
    };
  });

const feedbackInputSchema = z.object({
  jobId: z.string(),
  correctedScore: z.number().optional(),
  notes: z.string().optional(),
});

// Roofer corrections, saved on Railway as future training data -- see
// backend README's roadmap note on training a real defect model.
export const submitRoofFeedback = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input: unknown) => feedbackInputSchema.parse(input))
  .handler(async ({ data, context }) => {
    const res = await fetch(`${RAILWAY_API_URL}/api/v1/feedback`, {
      method: "POST",
      headers: railwayHeaders(),
      body: JSON.stringify({
        job_id: data.jobId,
        user_id: context.userId,
        corrected_score: data.correctedScore,
        notes: data.notes,
      }),
    });

    if (!res.ok) {
      throw new Error(`Railway feedback failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as { id: string; status: string };
  });
