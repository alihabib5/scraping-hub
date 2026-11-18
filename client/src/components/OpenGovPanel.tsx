"use client";

import { useState } from "react";

import OpenGovResults from "@/components/OpenGovResults";
import RunStatusPanel from "@/components/RunStatus";
import { Card, DateField, ErrorBanner, LaunchBar, StartButton } from "@/components/ui";
import LiveMonitor from "@/components/LiveMonitor";
import StopButton from "@/components/StopButton";
import RefreshButton from "@/components/RefreshButton";
import ScraperControls from "@/components/ScraperControls";
import SessionActivity from "@/components/SessionActivity";
import { usePortalSession } from "@/lib/usePortalSession";
import { isRunActive, startOpenGovScrape } from "@/lib/api";

/** OpenGov Procurement: every Current Opportunity on the vendor Network. */
export default function OpenGovPanel() {
  // Release Date range, ISO (yyyy-mm-dd) from the native pickers. From alone
  // means "through today" (the server fills that in); both blank means all.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const { run, error, starting, setError, launch, applyStatus, hasSession, reset } =
    usePortalSession("opengov");

  const handleStart = (livePreview = false) =>
    launch(() => startOpenGovScrape({ dateFrom, dateTo, livePreview }));
  const isRunning = isRunActive(run);

  // ISO dates compare correctly as strings. The pickers' min/max already stop
  // this, but a typed-in date can still get past them.
  const rangeInverted = dateFrom !== "" && dateTo !== "" && dateTo < dateFrom;
  const rangeText =
    dateFrom && dateTo
      ? `released ${dateFrom} to ${dateTo}`
      : dateFrom
        ? `released ${dateFrom} through today`
        : dateTo
          ? `released on or before ${dateTo}`
          : "";

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <Card
        title="Release Date Range"
        description="Optional. Only opportunities released inside the range are exported; the rest are skipped. Leave both blank to capture every current opportunity."
      >
        <div className="flex flex-wrap items-end gap-4">
          <DateField
            label="From"
            value={dateFrom}
            max={dateTo}
            disabled={isRunning}
            onChange={setDateFrom}
          />
          <DateField
            label="To"
            value={dateTo}
            min={dateFrom}
            disabled={isRunning}
            onChange={setDateTo}
          />
        </div>
        {rangeInverted ? (
          <p className="mt-2 text-xs text-rose-600">
            The To date is before the From date — no bid can be released in that range.
          </p>
        ) : (
          <p className="mt-2 text-xs text-ink-500">
            Both days are included. With only a From date, the range runs through today.
          </p>
        )}
      </Card>

      <LaunchBar
        summary={
          rangeInverted
            ? "Fix the date range before starting."
            : rangeText
              ? `Current opportunities ${rangeText}: title, organization, state, status, dates — one spreadsheet.`
              : "Every current opportunity: title, organization, state, status, release and due dates — one spreadsheet."
        }
      >
        <div className="flex items-center gap-2">
          <StopButton run={run} onError={setError} />
          <LiveMonitor run={run} portal="opengov" />
          <ScraperControls run={run} onError={setError} onStatusChange={applyStatus} />
          <RefreshButton run={run} hasSession={hasSession} onReset={reset} />
          <StartButton
            onClick={() => handleStart()}
            disabled={starting || isRunning || rangeInverted}
            running={isRunning}
            starting={starting}
          >
            Start scrape
          </StartButton>
        </div>
      </LaunchBar>

      {run && <RunStatusPanel run={run} />}
      <SessionActivity portal="opengov" />
      {run && <OpenGovResults bids={run.bids} />}
    </div>
  );
}
