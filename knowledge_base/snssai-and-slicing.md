# S-NSSAI and Network Slicing

Sources:
- https://open5gs.org/open5gs/docs/guide/01-quickstart/ (NSSF's role)
- https://open5gs.org/open5gs/docs/tutorial/07-infoAPI-UE-gNB-session-data/ (S-NSSAI as a runtime field)
- General 3GPP terminology (SST/SD numeric meaning) — NOT documented in
  Open5GS's own docs as fetched; included here as widely-used standard
  background, flagged separately from the Open5GS-specific material above.

## What Open5GS's own docs say

Per Open5GS's quickstart guide, the **NSSF (Network Slice Selection
Function)** "provides a way to select the network slice" — it is the NF
responsible for slice selection, but the quickstart guide does not
elaborate on S-NSSAI's internal SST/SD structure.

Per the infoAPI tutorial, **S-NSSAI** is one of the fields exposed for a
connected UE via the AMF's `/ue-info` endpoint and for its PDU sessions
via the SMF's `/pdu-info` endpoint — i.e., the subscriber's active slice
assignment can be inspected directly at runtime through this API, which
is a useful diagnostic tool independent of reading MongoDB or config
files directly.

## Supplementary 3GPP background (not Open5GS-doc-sourced)

S-NSSAI has two parts:
- **SST (Slice/Service Type)** — standardized numeric categories exist
  (1 = eMBB, 2 = URLLC, 3 = MIoT), with operator-defined values also
  possible in non-standardized ranges.
- **SD (Slice Differentiator)** — an optional operator-assigned value
  distinguishing multiple slices sharing the same SST.

## Practical diagnostic implication

Because S-NSSAI is directly queryable via the infoAPI at runtime, a slice
mismatch between what a subscriber is assigned and what the gNB/AMF
actually serves can be confirmed by comparing the infoAPI's reported
S-NSSAI for that UE against the AMF/gNB's configured/advertised slice
list, rather than only inferring it from failure symptoms.
