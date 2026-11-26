# CERBERUS-X Demo Dataset (v1.0)

A lightweight, multi-format synthetic dataset designed to test cross-modal conflict detection and causal timeline verification in **CERBERUS-X**.

## Included Files
| File | Format | Purpose |
| :--- | :--- | :--- |
| `shipment_manifest.csv` | CSV | Baseline dispatch record for shipment `SHP-9042` (42.5 kg, ₹50L cardiac stents). |
| `telemetry_gps_log.json` | JSON | IoT sensor & GPS trail showing weight drop to 18.0 kg and seal tamper in Pune on Nov 19. |
| `checkpoint_weighbridge_slip.png` | PNG | Visual highway weighbridge ticket corroborating the 18.0 kg weight and broken seal in Pune. |
| `delivery_receipt_signed.pdf` | PDF | Falsified Proof of Delivery claiming 42.5 kg intact delivery in Mumbai on Nov 20 signed by `EMP-407`. |
| `gate_security_log.txt` | TXT | Biometric & RFID access logs for Bengaluru Hub showing `EMP-407` on-site Nov 18–20. |
| `expense_claims.xlsx` | XLSX | Travel reimbursement claims placing `EMP-407` in New Delhi on Nov 19–20. |
| `expected.json` | JSON | Ground-truth contradictions (`CON-001` to `CON-003`) for automated evaluation. |

## Expected Contradictions Summary
1. **CON-001 (`SHP-9042`)**: Cargo weight/seal mismatch between Pune checkpoint telemetry/image (18.0 kg, broken seal) and Mumbai signed POD PDF (42.5 kg, intact seal).
2. **CON-002 (`EMP-407`)**: Physical presence conflict on **2026-11-19** between Bengaluru biometric logs and New Delhi flight/hotel expense claims.
3. **CON-003 (`EMP-407`)**: Tri-city impossibility on **2026-11-20** across Bengaluru (08:30 gate entry), Mumbai (14:20 POD signature), and New Delhi (dinner expense).
