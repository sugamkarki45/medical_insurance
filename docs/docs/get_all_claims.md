

**Endpoint:** `GET /claims/all`

### Response Example

```json
[
  {
  "count": 4,
  "results": [
    {
      "status": "checked",
      "id": 3,
      "items": [
        {
          "sequence_id": 1,
          "item_code": "LAB140",
          "status": "passed"
        }
      ],
      "fetched_at": "2025-12-07T09:04:25.006121",
      "service_code": "OPD1",
      "department": "string",
      "patient_id": "740500036",
      "claim_code": "cl2",
      "created_at": "2025-12-07T00:00:00",
      "raw_response": {
        "resourceType": "ClaimResponse",
        "addItem": [
          {
            "sequenceLinkId": [
              1
            ],
            "service": {
              "coding": [
                {
                  "code": "LAB140"
                }
              ]
            }
          }
        ],
        "created": "2025-12-07",
        "extension": [
          {
            "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment+Claim+Total",
            "valueDecimal": 0.1,
            "valueMoney": 50,
            "valueString": "NormalHibScheme "
          }
        ],
        "id": "B53003DB-DD77-40CD-86C9-973CA2715D6D",
        "identifier": [
          {
            "type": {
              "coding": [
                {
                  "code": "ACSN",
                  "system": "https://hl7.org/fhir/valueset-identifier-type.html"
                }
              ]
            },
            "use": "usual",
            "value": "B53003DB-DD77-40CD-86C9-973CA2715D6D"
          },
          {
            "type": {
              "coding": [
                {
                  "code": "MR",
                  "system": "https://hl7.org/fhir/valueset-identifier-type.html"
                }
              ]
            },
            "use": "usual",
            "value": "cl2"
          }
        ],
        "item": [
          {
            "adjudication": [
              {
                "amount": {
                  "value": 90
                },
                "category": {
                  "text": "general"
                },
                "extension": [
                  {
                    "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment+Item+Value",
                    "valueDecimal": 0.1,
                    "valueMoney": 50,
                    "valueString": "NormalHibScheme "
                  }
                ],
                "reason": {
                  "coding": [
                    {
                      "code": "1"
                    }
                  ],
                  "text": "passed"
                }
              }
            ],
            "sequenceLinkId": 1
          }
        ],
        "outcome": {
          "coding": [
            {
              "code": "4"
            }
          ],
          "text": "checked"
        },
        "request": {
          "reference": "Claim/B53003DB-DD77-40CD-86C9-973CA2715D6D"
        }
      },
      "service_type": "OPD",
      "item_code": [
        {
          "item_code": "LAB140",
          "name": "STRING",
          "qty": 1,
          "cost": 0,
          "category": "service",
          "type": "medicine"
        }
      ]
    }
]}]
```

---
