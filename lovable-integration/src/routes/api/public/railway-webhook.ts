// Receives the signed push notification Railway sends when a job finishes
// (backend/app/services/webhook.py's notify_lovable) -- matches the URL in
// your original spec: POST /api/public/railway-webhook.
//
// IMPORTANT: I don't have access to your actual Lovable/TanStack Start
// codebase, so I can't confirm which exact route API your project's
// TanStack Start version uses (`createServerFileRoute`, `createAPIFileRoute`,
// or something else -- this has changed across TanStack Start versions).
// The `verifyAndParseWebhook` function below is the part that matters and is
// framework-independent; wire it into whatever your project's actual
// file-route convention is. The `Route` export below is one plausible
// shape -- treat it as a sketch to adapt, not copy-paste-verified code, the
// way the rest of this integration folder is.

import crypto from "node:crypto";

const WEBHOOK_SECRET = process.env["WEBHOOK_SECRET"]!; // must match Railway's WEBHOOK_SECRET exactly

export type RailwayWebhookPayload = {
  job_id: string;
  user_id: string | null;
  status: "completed" | "failed";
  result: Record<string, unknown> | null;
};

export class InvalidWebhookSignatureError extends Error {}

// Framework-independent: verify the HMAC-SHA256 signature (constant-time
// compare, since this is exactly the kind of check that must not leak
// timing info) and parse the body. Call this from whatever your actual
// route handler looks like.
export function verifyAndParseWebhook(rawBody: string, signatureHeader: string | null): RailwayWebhookPayload {
  if (!signatureHeader) {
    throw new InvalidWebhookSignatureError("Missing X-Webhook-Signature header");
  }

  const expected = crypto.createHmac("sha256", WEBHOOK_SECRET).update(rawBody).digest("hex");
  const expectedBuf = Buffer.from(expected, "hex");
  const gotBuf = Buffer.from(signatureHeader, "hex");

  if (expectedBuf.length !== gotBuf.length || !crypto.timingSafeEqual(expectedBuf, gotBuf)) {
    throw new InvalidWebhookSignatureError("Signature mismatch");
  }

  return JSON.parse(rawBody) as RailwayWebhookPayload;
}

// --- one plausible TanStack Start wiring; verify against your actual version ---
//
// import { createServerFileRoute } from "@tanstack/react-start/server";
// import { db } from "~/lib/db"; // adjust to your actual DB client
//
// export const Route = createServerFileRoute().methods({
//   POST: async ({ request }) => {
//     const rawBody = await request.text();
//     let payload: RailwayWebhookPayload;
//     try {
//       payload = verifyAndParseWebhook(rawBody, request.headers.get("x-webhook-signature"));
//     } catch (err) {
//       if (err instanceof InvalidWebhookSignatureError) {
//         return new Response("invalid signature", { status: 401 });
//       }
//       return new Response("bad payload", { status: 400 });
//     }
//
//     // Upsert into your roof_reports table -- adjust to your actual schema/ORM.
//     await db.roof_reports.upsert({
//       where: { job_id: payload.job_id },
//       create: {
//         job_id: payload.job_id,
//         user_id: payload.user_id,
//         status: payload.status,
//         result: payload.result,
//       },
//       update: {
//         status: payload.status,
//         result: payload.result,
//       },
//     });
//
//     return new Response("ok", { status: 200 });
//   },
// });
