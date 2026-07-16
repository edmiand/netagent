# Subscriber Profile Fields

Sources:
- https://open5gs.org/open5gs/docs/tutorial/01-your-first-lte/ (provisioning fields)
- https://open5gs.org/open5gs/docs/tutorial/07-infoAPI-UE-gNB-session-data/ (fields exposed at runtime)

## Provisioning fields (per the "Your First LTE" tutorial)

Open5GS's tutorial demonstrates two provisioning methods — programming a
physical USIM via PySIM, or adding a subscriber through the Open5GS Web
UI (default `localhost:9999`). Both require the same core fields:

- **IMSI** — the subscriber's unique identifier (example from the
  tutorial: `310789012345301`).
- **K (subscriber key)** — referred to in the tutorial as "Ki," the
  authentication key shared between the USIM and the network.
- **OPc (operator cipher key)** — operator-specific key material combined
  with K during authentication. The tutorial's Web UI method groups K,
  OPc, and AMF (the 3GPP "Authentication Management Field," not the AMF
  network function — an unrelated same-named field) together under
  "security context."
- **APN/DNN** — the data network the subscriber is provisioned to reach.
  On the 5G SA side this is the DNN (Data Network Name); the LTE tutorial
  uses the older APN terminology for the same concept.

A missing or mismatched K/OPc is what produces the `Authentication
failure(MAC failure)` documented in Open5GS's troubleshooting guide (see
attach-failure-modes.md); a missing IMSI record produces `Cannot find
IMSI in DB`.

## Runtime fields (per the infoAPI tutorial)

Open5GS exposes a lightweight HTTP infoAPI (default port 9090) for
inspecting live subscriber/session state. The AMF's `/ue-info` endpoint
and SMF's `/pdu-info` endpoint expose, per the tutorial's documented
field list:

- Security credentials and encryption/integrity algorithm state
- **S-NSSAI** (network slice assignment)
- **AMBR** (Aggregate Maximum Bit Rate) limits
- **DNN** and assigned IP address
- QoS flow identifiers and PDU/session state
- Location info, GUTI/TMSI identifiers

This means the same fields that matter for provisioning (DNN, slice,
AMBR, security credentials) are also directly queryable at runtime via
the infoAPI — useful for confirming what a subscriber actually has in
effect versus what was intended, without needing direct MongoDB access.

## Status field

Open5GS's own tutorial/troubleshooting docs (as fetched) do not
separately document a numeric `status` field's allowed/barred semantics
in detail — this project's convention (status 0 = allowed, 1 = barred,
per this app's system prompt) should be treated as this deployment's
documented behavior rather than something independently verified against
Open5GS's public docs.
