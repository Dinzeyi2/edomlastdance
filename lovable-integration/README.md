# Lovable-side Railway integration

Copy these files into your Lovable project. They're written against your
sketched TanStack Start + Supabase-auth pattern, and against the Railway
backend's real API contract (`backend/app/schemas/analyze.py`) -- not
guessed field names.

## Confidence level, file by file

- **`src/lib/railway.functions.ts`** -- high confidence. Uses the exact
  `createServerFn` pattern you sketched; the only things to verify are the
  `requireSupabaseAuth` import path and that `context.userId` is really
  where your auth middleware puts the user id.
- **`src/hooks/useRoofAnalysis.ts`** -- high confidence. Plain React, no
  framework-specific assumptions.
- **`src/routes/api/public/railway-webhook.ts`** -- **lower confidence on
  the route wiring specifically.** I don't have your actual codebase, so I
  can't confirm which TanStack Start route API your project's version uses
  (`createServerFileRoute` vs `createAPIFileRoute` vs something else -- this
  has changed across versions). The signature-verification logic
  (`verifyAndParseWebhook`) is framework-independent and should be correct
  as-is; the commented-out `Route` export at the bottom is a sketch to adapt
  to your actual routing convention and `roof_reports` schema, not
  copy-paste-verified code.

## Required env vars (Lovable side)

```
RAILWAY_API_URL=https://<your-web-service>.up.railway.app
RAILWAY_API_KEY=<same value as RAILWAY_API_KEY on both Railway services>
WEBHOOK_SECRET=<same value as WEBHOOK_SECRET on Railway, only if you wire up the webhook receiver>
```

## Usage in TeslaMap.tsx

```tsx
import { useRoofAnalysis } from "~/hooks/useRoofAnalysis";

function TeslaMap() {
  const { status, progress, stage, result, error, runAnalysis } = useRoofAnalysis();

  const handleMapClick = (lat: number, lng: number) => {
    runAnalysis({ lat, lng, compareYear: 2023 });
  };

  // status: "idle" | "queued" | "processing" | "completed" | "failed"
  // result, once completed, matches AnalysisResult exactly:
  //   score, condition, confidence, findings[], temporal, image_urls, ...
}
```

## What I have not done

Written the actual `db.roof_reports` write (I don't know your schema/ORM),
and not touched your real Lovable codebase at all -- these are standalone
files for you to copy in and adapt, not a verified patch against your
project.
