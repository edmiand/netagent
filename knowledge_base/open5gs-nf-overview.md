# Open5GS Network Function Overview

Source: https://open5gs.org/open5gs/docs/guide/01-quickstart/
(supplemented with https://open5gs.org/open5gs/docs/tutorial/01-your-first-lte
for LTE-side terminology mapping)

Open5GS implements a Service Based Architecture (SBA) for the 5G
Standalone (SA) core — a set of independent network functions (NFs) that
register with and discover each other dynamically, rather than being
wired together with static point-to-point connections the way 4G EPC
components (MME/SGW/PGW) traditionally are.

## Core NFs and their roles (per Open5GS's own quickstart guide)

- **AMF (Access and Mobility Management Function)** — handles connection
  and mobility management. Serves as the entry point where gNBs (5G base
  stations) connect. Open5GS describes it as covering "a subset of what
  the 4G MME is tasked with."
- **SMF (Session Management Function)** — manages all session-related
  operations. Open5GS notes this consolidates responsibilities that were
  previously split across 4G's MME, SGW-C, and PGW-C into one component.
- **UPF (User Plane Function)** — the sole user-plane element. It carries
  user data packets between the gNB and the external WAN, and connects
  back to the SMF for control (PFCP).
- **AUSF, UDM, and UDR** — described by Open5GS as together carrying out
  what the 4G HSS did: generating SIM authentication vectors (AUSF) and
  holding/mediating the subscriber profile (UDM/UDR).
- **NRF (NF Repository Function)** — control-plane functions register
  with the NRF, which then helps them discover each other. This
  registration-based discovery model is what replaces 4G's static,
  point-to-point NF connectivity.
- **PCF (Policy Control Function)** — handles charging and enforcing
  subscriber policies.
- **NSSF (Network Slice Selection Function)** — provides the mechanism
  for selecting a network slice.
- **BSF and SEPP** — BSF provides binding support (tracking which PCF
  instance is bound to a given session); SEPP provides roaming security
  capabilities (relevant to inter-operator roaming scenarios, not covered
  in Open5GS's core quickstart tutorial).

## LTE-side terminology mapping (for reference)

Open5GS also supports 4G/LTE deployments, where the equivalent roles are
split differently: MME (mobility + auth), HSS/UDR (subscriber storage),
and SGW/PGW (user-plane routing, now unified into UPF on the 5G SA side).
Subscriber provisioning in the LTE tutorial uses the same underlying
credential fields (IMSI, K, OPc) that carry over to 5G SA subscriber
profiles.

## Typical attach call flow (Open5GS SBA)

1. UE → AMF: registration request (via gNB).
2. AMF → AUSF: authentication using subscriber's K/OPc (retrieved via
   UDM/UDR).
3. AMF → UDM: retrieve subscription data.
4. AMF → SMF: PDU session establishment request.
5. SMF → UPF: session rules over PFCP (N4); UPF becomes active on the
   user-plane path.

A break at any step surfaces differently — authentication failures never
get past step 2, session failures happen after registration but before
step 5, and connectivity issues can occur even after step 5 completes
successfully (UPF up but misrouting traffic).
