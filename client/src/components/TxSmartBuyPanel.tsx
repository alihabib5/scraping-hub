"use client";

import { useEffect, useState } from "react";

import LiveMonitor from "@/components/LiveMonitor";
import RefreshButton from "@/components/RefreshButton";
import RunStatusPanel from "@/components/RunStatus";
import ScraperControls from "@/components/ScraperControls";
import SessionActivity from "@/components/SessionActivity";
import StopButton from "@/components/StopButton";
import TxSmartBuyResults from "@/components/TxSmartBuyResults";
import { Button, Card, DateField, ErrorBanner, Field, LaunchBar, SelectField, StartButton } from "@/components/ui";
import { getTxSmartBuyFilters, isRunActive, startTxSmartBuyScrape, type TxSmartBuyCriteria, type TxSmartBuyFilters } from "@/lib/api";
import { usePortalSession } from "@/lib/usePortalSession";

const EMPTY: TxSmartBuyCriteria = {
  agency: "",
  agency_number: "",
  status: "",
  class_item_codes: "",
  keyword: "",
  solicitation_id: "",
  date_range: "custom",
  start_date: "",
  end_date: "",
};

/**
 * ESBD's Solicitations filters, laid out the way the portal lays them out. The
 * run applies them on ESBD, clicks Search, then Export to CSV.
 */
export default function TxSmartBuyPanel() {
  const [criteria, setCriteria] = useState<TxSmartBuyCriteria>(EMPTY);
  const [options, setOptions] = useState<TxSmartBuyFilters | null>(null);
  const { run, error, starting, setError, launch, applyStatus, hasSession, reset } = usePortalSession("txsmartbuy");

  useEffect(() => {
    getTxSmartBuyFilters()
      .then(setOptions)
      .catch((e: Error) => setError(e.message));
  }, [setError]);

  const set = (key: keyof TxSmartBuyCriteria) => (value: string) => setCriteria((c) => ({ ...c, [key]: value }));
  const isRunning = isRunActive(run);
  const custom = criteria.date_range === "custom";
  const datesBackwards = custom && criteria.start_date && criteria.end_date && criteria.start_date > criteria.end_date;
  const hasCriteria = Object.entries(criteria).some(([k, v]) => v !== EMPTY[k as keyof TxSmartBuyCriteria]);
  // A preset range fills its own dates on ESBD, so custom dates are sent only with Custom.
  const handleStart = (livePreview = false) =>
    launch(() => startTxSmartBuyScrape(custom ? criteria : { ...criteria, start_date: "", end_date: "" }, livePreview));

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <Card
        title="Search filters"
        description="The same filters as ESBD's Solicitations search. All optional — leave them blank to export every solicitation (ESBD caps an export at 20,000)."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <SelectField
            label="Agency/Texas SmartBuy Member Name"
            value={criteria.agency}
            onChange={set("agency")}
            disabled={isRunning || !options}
            placeholder={options ? "Any agency" : "Loading agencies…"}
            options={(options?.agencies ?? []).map((a) => ({ value: a, label: a }))}
          />
          <Field label="Agency/Texas SmartBuy Member Number" value={criteria.agency_number} onChange={set("agency_number")} disabled={isRunning} placeholder="e.g. 601" />
          <SelectField
            label="Status"
            value={criteria.status}
            onChange={set("status")}
            disabled={isRunning || !options}
            options={options?.statuses ?? [{ value: "", label: "Select All" }]}
          />
          <Field label="Class/Item Codes" value={criteria.class_item_codes} onChange={set("class_item_codes")} disabled={isRunning} placeholder="e.g. 91371" />
          <Field label="Keyword Search" value={criteria.keyword} onChange={set("keyword")} disabled={isRunning} placeholder="e.g. trailer" />
          <Field label="Solicitation ID" value={criteria.solicitation_id} onChange={set("solicitation_id")} disabled={isRunning} placeholder="e.g. 6100019963" />
          <SelectField
            label="Date Range"
            value={criteria.date_range}
            onChange={set("date_range")}
            disabled={isRunning || !options}
            options={options?.date_ranges ?? [{ value: "custom", label: "Custom" }]}
          />
          <DateField label="Start Date" value={criteria.start_date} onChange={set("start_date")} disabled={isRunning || !custom} max={criteria.end_date || undefined} />
          <DateField label="End Date" value={criteria.end_date} onChange={set("end_date")} disabled={isRunning || !custom} min={criteria.start_date || undefined} />
        </div>
        {datesBackwards && <p className="mt-3 text-sm text-rose-600">The start date is after the end date.</p>}
      </Card>

      <LaunchBar summary={hasCriteria ? "Searching ESBD with your filters, then exporting the results." : "No filters set — every ESBD solicitation will be exported."}>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setCriteria(EMPTY)} disabled={isRunning || !hasCriteria}>
            Clear Filters
          </Button>
          <StopButton run={run} onError={setError} />
          <LiveMonitor run={run} portal="txsmartbuy" />
          <ScraperControls run={run} onError={setError} onStatusChange={applyStatus} />
          <RefreshButton run={run} hasSession={hasSession} onReset={reset} />
          <StartButton onClick={() => handleStart()} disabled={starting || isRunning || !!datesBackwards} running={isRunning} starting={starting}>
            Search &amp; export
          </StartButton>
        </div>
      </LaunchBar>

      {run && <RunStatusPanel run={run} />}
      <SessionActivity portal="txsmartbuy" />
      {run && <TxSmartBuyResults bids={run.bids} />}
    </div>
  );
}
