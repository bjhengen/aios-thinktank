# AI World 2026 — Booth Robot Equipment Proposal

> **Status (2026-11-08): not approved, kept for reference.** Nothing was ordered,
> and the work moved to the robotcar chassis rebuild
> (see `docs/2026-11-08-parts-catalog.md`).

**Prepared:** August 2026
**Event:** Oracle AI World, 25–28 October 2026, Venetian Expo, Las Vegas
**Total requested:** **$10,888**

---

## What we're proposing

A conversational assistant robot for the Oracle booth. Attendees ask it questions
about the conference, Oracle Database and OCI; it retrieves answers from an
Oracle Database using AI Vector Search and speaks them back, while a screen
beside it shows the query and matching rows landing live.

The robot drives itself within a defined area around the booth. All inference
runs locally on an NVIDIA DGX — nothing goes to the cloud.

We are proposing to buy a **commercial robot platform (temi V3)** and put our
own AI software on it, rather than building a robot from scratch. With eleven
weeks to the show, that is the only approach that leaves time to test properly.

---

## Why this platform

- **It does the hard parts already** — self-driving navigation with LiDAR,
  obstacle avoidance, automatic recharging, and an 8-hour battery that covers a
  full show day.
- **It's open enough to run our software.** We verified against the published
  developer documentation that our existing control code can drive the robot,
  use its camera, and replace its built-in voice assistant with ours. Roughly
  85% of our existing software carries over unchanged.
- **Track record at events**, including use as a guide robot at World Expo.

---

## Equipment and costs

### Robot and licensing

| Item | Qty | Unit | Total |
|---|---:|---:|---:|
| temi V3 robot (Wi-Fi) — includes docking station | 1 | $4,399 | $4,399 |
| temi Pro licence, 3 years (required for developer access) | 1 | $2,499 | $2,499 |
| | | | **$6,898** |

### Audio

Trade show floors run 85–100 dB. The robot's built-in microphones and speakers
are designed for offices, so we add directional audio to make conversation work.

| Item | Qty | Unit | Total |
|---|---:|---:|---:|
| Directional USB microphone | 1 | $250 | $250 |
| Spare microphone | 1 | $250 | $250 |
| Powered speaker *(only if needed after testing)* | 1 | $250 | $250 |
| | | | **$750** |

### Booth network

Show floor Wi-Fi will be saturated. We bring our own isolated network.

| Item | Qty | Unit | Total |
|---|---:|---:|---:|
| Wi-Fi 6E access point | 1 | $290 | $290 |
| Spare access point | 1 | $290 | $290 |
| PoE injectors | 2 | $30 | $60 |
| Managed switch | 1 | $150 | $150 |
| Cabling and power distribution | 1 | $80 | $80 |
| | | | **$870** |

### Display

| Item | Qty | Unit | Total |
|---|---:|---:|---:|
| 55" commercial display — live database view | 1 | $800 | $800 |
| Floor stand | 1 | $200 | $200 |
| | | | **$1,000** |

*May already be covered by the booth package — worth checking with the events
team before we buy.*

### Transport and spares

| Item | Qty | Unit | Total |
|---|---:|---:|---:|
| Road case, robot | 1 | $500 | $500 |
| Road case, compute and network | 1 | $300 | $300 |
| Spare charging dock | 1 | $300 | $300 |
| Cables, adapters, power strips, tape | 1 | $200 | $200 |
| Floor marking tape | 1 | $70 | $70 |
| | | | **$1,370** |

### Total

| Section | Amount |
|---|---:|
| Robot and licensing | $6,898 |
| Audio | $750 |
| Booth network | $870 |
| Display | $1,000 |
| Transport and spares | $1,370 |
| **Total** | **$10,888** |

**This is a hardware-only request.** The AI software — vision, navigation
control, mapping, safety limits and the Oracle Database retrieval layer — has
been in development and testing on a working robot for the past year, and the
document-retrieval component is already running against a 25,000-chunk Oracle
documentation corpus. We are adapting proven software to a better robot, not
starting from scratch. That prior work is what makes an eleven-week timeline
realistic.

---

## Not included

- **Compute.** Inference runs on a loaner NVIDIA DGX. If that falls through, a
  replacement workstation is $6,650–7,500 at current market prices, which would
  put the project over budget. Worth confirming the loan terms early.
- **Venue costs** — power drops, hardline internet, freight, and insurance are
  assumed to sit with the booth budget.
- **Labour** — in-house, and reduced by the existing software base described
  above. The work is integration and hardening, not new development.

---

## Timeline

| When | What |
|---|---|
| **By 21 August** | Purchase approved and order placed |
| Late August | Hardware arrives, initial setup |
| September | Voice and database integration |
| Late Sept – early Oct | Full rehearsal on trade show carpet |
| Mid October | Ship with booth freight |
| 25–28 October | Show |

**Ordering is the critical path.** Every week of delay comes out of the
rehearsal window, which is the part that shouldn't be compressed.

---

## Known risks

1. **Audio in a loud hall.** The main technical risk. Mitigated with a
   directional microphone, close-range "tap to ask" interaction, and showing
   answers on screen as well as speaking them — so the demo still works if the
   audio doesn't.
2. **No spare robot.** A single unit means a hardware failure takes the demo
   down. Mitigated by including spares of the components most likely to fail
   (dock, microphone, access point), and by building a fallback where the booth
   screen runs the same question-and-answer experience as a touchscreen kiosk.
   Worth asking the supplier about a standby loaner unit.
3. **One open question with the manufacturer.** We have asked temi's developer
   support to confirm the robot accepts an external microphone. If not, we
   attach a small dedicated computer instead — a change of about $400, not a
   change of plan.

---

## What we're asking for

Approval to spend **$10,888** on the equipment above, with an order placed by
**21 August** to protect the rehearsal window.
