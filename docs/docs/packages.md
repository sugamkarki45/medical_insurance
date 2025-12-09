

**Endpoint:** `GET /packages`

### Response Example

```json
[
  "count": 65,
  "packages": [
    {
      "code": "IPDB1",
      "name": "Nebulization per episode",
      "type": "bed_charges",
      "package_group": "Day Care",
      "rate_npr": 120,
      "includes": [
        "bed_charge",
        "consultation",
        "investigations",
        "medications"
      ],
      "icu_included": false,
      "ccu_included": false,
      "claim_mode": "bundled_per_admission",
      "claimable": true,
      "capping": {
        "max_days": null,
        "max_per_visit": 99999
      }
    },
    {
      "code": "MM1",
      "name": "Speech Therapy per session",
      "type": "medical_management",
      "package_group": "Day Care",
      "rate_npr": 180,
      "includes": [
        "bed_charge",
        "consultation",
        "investigations",
        "medications"
      ],
      "icu_included": false,
      "ccu_included": false,
      "claim_mode": "bundled_per_admission",
      "claimable": true,
      "capping": {
        "max_days": null,
        "max_per_visit": 99999
      }
    }]
]
```
