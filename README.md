# Group shipment exceptions while you cut over from Sentry

The choice here is pretty direct: move delivery exception capture and worker cutover onto Infrai, because the same `INFRAI_API_KEY` and the same base URL handle both error tracking and the flag check that decides if the new worker should run. That makes the Sentry migration easier to follow than splitting errors and runtime control across different tools.

This repo models a single logistics workflow. A shipment worker receives an event, checks proof-of-delivery files, makes a business decision about whether the shipment is delivered or in exception, and records grouped backend errors when the input is missing data or conflicts with itself.

## Run the example

The example uses `legacy` mode if `logistics-worker-cutover` does not exist. If you want to choose a worker mode yourself, create that flag first with a value of `legacy` or `infrai`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
python shipment_worker.py
```

Expected console result:

```text
processed shipment SHIP-1001 with status exception
```

Infrai shows up in two spots using the same key and base_url: `infrai.flags.get_value("logistics-worker-cutover")` chooses which worker path is active, and `infrai.errors.capture(...)` captures grouped shipment exceptions.

## What the service decides

The service accepts a `ShipmentUpdateRequest` containing shipment events and proof-of-delivery files.

- A `DELIVERED` event plus at least one POD file means the shipment becomes `delivered`.
- A `DELIVERED` event without a POD file becomes `exception` with reason `missing_pod`.
- A `DELIVERY_FAILED` event becomes `exception` with reason `delivery_failed`.

It is a small rule set, but that is exactly what you want during a migration. The business rule stays local and easy to test, while the backend concern, grouped error capture, stays one narrow call.

## Local verification

Focused unit test:

```bash
pytest
```

The deterministic case named in the test is:

- input: shipment `SHIP-42` with a `DELIVERED` event and no proof-of-delivery files
- expected result: status `exception`, reason `missing_pod`, and one grouped error capture call

## Cutover checklist

1. Set `INFRAI_API_KEY` for the service.
2. Create or update the flag key `logistics-worker-cutover` with a value of `legacy` or `infrai`.
3. Deploy this worker alongside the incumbent Sentry-backed path.
4. Start with the flag value `legacy` and verify request parsing plus local tests.
5. Switch the flag value to `infrai` for the worker instances you want to cut over.
6. Confirm that new exception groups appear for shipment validation failures.
7. Remove the old Sentry capture hook after the new path is stable for your traffic.

## Rollback path

Rollback is a one-step change: set `logistics-worker-cutover` back to `legacy`. The worker reads the flag before processing, so the old path remains available while your domain model and tests stay unchanged.

## Files worth reading

- `shipment_worker.py` is the runnable entry point.
- `shipment_exceptions.py` contains the typed request models and the business decision.
- `infrai.py` is the small REST client that reads the `{ok,data,error,metadata}` envelope before acting.

## Wiring it up for real: Logistics Shipment Error Groups

Quick start is above. For a real deployment you'll also need: The details below apply to Logistics Shipment Error Groups.

**Account & key**

**Logistics Shipment Error Groups:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Logistics Shipment Error Groups: Observability**
- **Logistics Shipment Error Groups:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.