

**Endpoint:** `POST /submit_claim`

### Request Body

```json
{
  "claim_id":"claim id",
  "username":"username",
  "password":"password"
}
{
  "patient_id": "740500036",
  "visit_date": "2025-12-09",
  "service_type": "OPD",
  "service_code": "OPD1",
  "doctor_nmc": "121",
  "diagnosis": {
    "provisional": "malaria",
    "differential": "fever",
    "final": "malaria",
    "is_chronic": false
  },
  "icd_codes": [
    "1F42"
  ],
  "claimable_items": [
    {
      "type": "LAB",
      "item_code": "LAB140",
      "quantity": 1,
      "cost": 70,
      "name": "ammonia",
      "category": "service"
    }
  ],
  "hospital_type": "phc",
  "enterer_reference": "7aa79c53-057e-4e77-8576-dfcfb03584a8",
  "facility_reference": "1ac457d3-efd3-4a67-89b3-bf8cbe18045d",
  "claim_time": "2025-12-09",
  "claim_code": "CLM11",
  "department": "ENT"
}
```

### Response Example

```json
{
  "message": "Claim successfully submitted to IMIS",
  "claim_code": "CLM11",
  "status": "checked",
  "submitted_at": "2025-12-09T06:57:26.777470",
  "created_at": "2025-12-09T00:00:00",
  "items": [
    {
      "sequence_id": 1,
      "item_code": "LAB130",
      "status": "passed"
    }
  ],
  "IMIS_response": {
    "resourceType": "ClaimResponse",
    "addItem": [
      {
        "sequenceLinkId": [
          1
        ],
        "service": {
          "coding": [
            {
              "code": "LAB130"
            }
          ]
        }
      }
    ],
    "created": "2025-12-09",
    "extension": [
      {
        "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment+Claim+Total",
        "valueDecimal": 0.1,
        "valueMoney": 7,
        "valueString": "NormalHibScheme "
      }
    ],
    "id": "79DCDCEA-628A-4E27-8ADB-6561F700E274",
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
        "value": "79DCDCEA-628A-4E27-8ADB-6561F700E274"
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
        "value": "CLM11"
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
                "valueMoney": 7,
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
      "reference": "Claim/79DCDCEA-628A-4E27-8ADB-6561F700E274"
    }
  },
  "payload": {
    "resourceType": "Claim",
    "billablePeriod": {
      "start": "2025-12-09",
      "end": "2025-12-09"
    },
    "created": "2025-12-09T06:57:22.911370",
    "patient": {
      "reference": "Patient/C335B6A2-738C-4373-AFF4-DAD1B8B09645"
    },
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
        "value": "498160191ec7414390b52a0360082cff"
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
        "value": "CLM11"
      }
    ],
    "item": [
      {
        "sequence": 1,
        "category": {
          "text": "service"
        },
        "quantity": {
          "value": 1
        },
        "service": {
          "text": "LAB130"
        },
        "unitPrice": {
          "value": 70
        }
      }
    ],
    "total": {
      "value": 70
    },
    "careType": "O",
    "enterer": {
      "reference": "Practitioner/7aa79c53-057e-4e77-8576-dfcfb03584a8"
    },
    "facility": {
      "reference": "Location/1ac457d3-efd3-4a67-89b3-bf8cbe18045d"
    },
    "diagnosis": [
      {
        "sequence": 1,
        "type": [
          {
            "coding": [
              {
                "code": "icd_0"
              }
            ],
            "text": "icd_0"
          }
        ],
        "diagnosisCodeableConcept": {
          "coding": [
            {
              "code": "1F42"
            }
          ]
        }
      }
    ],
    "nmc": "121",
    "type": {
      "text": "O"
    }
  },
  "system_info": {
    "source": "Unknown",
    "ip": "127.0.0.1",
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "timestamp": "2025-12-09T06:57:26.777451"
  },
  "prevalidation_summary": {
    "is_locally_valid": false,
    "warnings": [
      "Inter-department OPD visit within ticket validity requires referral documentation."
    ],
    "items": [
      {
        "item_code": "LAB130",
        "item_name": "AMMONIA",
        "quantity": 1,
        "claimable": true,
        "approved_amount": 180,
        "copay_amount": 18,
        "warnings": [],
        "type": "lab"
      }
    ],
    "total_approved_local": 180,
    "total_copay": 18,
    "net_claimable": 162,
    "applied_rules_version": "1.0",
    "allowed_money": 25520,
    "used_money": 0,
    "available_money": 25520
  },
  "warnings": [
    "Inter-department OPD visit within ticket validity requires referral documentation."
  ]
}
```

---
