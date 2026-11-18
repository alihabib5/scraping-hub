"use client";

import { useEffect, useState } from "react";

import CommbuysResults from "@/components/CommbuysResults";
import LiveMonitor from "@/components/LiveMonitor";
import RefreshButton from "@/components/RefreshButton";
import RunStatusPanel from "@/components/RunStatus";
import ScraperControls from "@/components/ScraperControls";
import SessionActivity from "@/components/SessionActivity";
import StopButton from "@/components/StopButton";
import { Button, Card, DateField, ErrorBanner, LaunchBar, StartButton } from "@/components/ui";
import { getCommbuysFilters, isRunActive, startCommbuysScrape, type CommbuysCriteria } from "@/lib/api";
import { usePortalSession } from "@/lib/usePortalSession";

const EMPTY: CommbuysCriteria = { available_from: "", available_to: "" };

/**
 * COMMBUYS open bids. The run signs in, reads every open bid, keeps the ones
 * whose Available Date is in this range, and sorts them into Pass and Reject.
 */
export default function CommbuysPanel() {
  const [criteria, setCriteria] = useState<CommbuysCriteria>(EMPTY);
  const [credentialsSet, setCredentialsSet] = useState(true);
  const { run, error, starting, setError, launch, applyStatus, hasSession, reset } = usePortalSession("commbuys");

  useEffect(() => {
    getCommbuysFilters()
      .then((f) => setCredentialsSet(f.credentials_set))
      .catch((e: Error) => setError(e.message));
  }, [setError]);

  const set = (key: keyof CommbuysCriteria) => (value: string) => setCriteria((c) => ({ ...c, [key]: value }));
  const isRunning = isRunActive(run);
  const datesBackwards = !!(criteria.available_from && criteria.available_to && criteria.available_from > criteria.available_to);
  const hasCriteria = !!(criteria.available_from || criteria.available_to);
  const handleStart = (livePreview = false) => launch(() => startCommbuysScrape(criteria, livePreview));

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}
      {!credentialsSet && (
        <ErrorBanner message="COMMBUYS_USERNAME / COMMBUYS_PASSWORD are not set in server/.env, so a run cannot sign in." />
      )}

      <Card
        title="Available Date"
        description="Keep the open bids COMMBUYS made available between these dates (both included). Leave both blank to take every open bid."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <DateField label="From" value={criteria.available_from} onChange={set("available_from")} disabled={isRunning} max={criteria.available_to || undefined} />
          <DateField label="To" value={criteria.available_to} onChange={set("available_to")} disabled={isRunning} min={criteria.available_from || undefined} />
        </div>
        {datesBackwards && <p className="mt-3 text-sm text-rose-600">The From date is after the To date.</p>}
      </Card>

      <LaunchBar
        summary={
          hasCriteria
            ? "Reading every open bid, keeping those available in your range, then sorting them into Pass and Reject."
            : "No dates set — every open bid will be read and sorted into Pass and Reject."
        }
      >
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setCriteria(EMPTY)} disabled={isRunning || !hasCriteria}>
            Clear Dates
          </Button>
          <StopButton run={run} onError={setError} />
          <LiveMonitor run={run} portal="commbuys" />
          <ScraperControls run={run} onError={setError} onStatusChange={applyStatus} />
          <RefreshButton run={run} hasSession={hasSession} onReset={reset} />
          <StartButton onClick={() => handleStart()} disabled={starting || isRunning || datesBackwards || !credentialsSet} running={isRunning} starting={starting}>
            Scrape open bids
          </StartButton>
        </div>
      </LaunchBar>

      {run && <RunStatusPanel run={run} />}
      <SessionActivity portal="commbuys" />
      {run && <CommbuysResults bids={run.bids} />}
    </div>
  );
}
