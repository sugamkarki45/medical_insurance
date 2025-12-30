

**Endpoint:** `POST /prevalidation`

### Header
```json
{
  "X-API-Key":"API key" 
}

```
### Request Body
```json
identifier:
{
  "patient_identifier": "string",
  "username": "string",
  "password": "string"
},
Input data:
{
  "patient_id": "740500036",  // patient inusrance number
  "visit_date": "2025-12-09",
  "service_type": "OPD",      // service taken by the patient OPD, IPD, ER
  "service_code": "OPD1",     // code of the service taken
  "doctor_nmc": "121", // doctor's NMC number. This can be multiple and can be sent as a list
  "diagnosis": {      // Provisional, Differential, final diagnosis with ICD code is required
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
      "category": "service"  // Service or Item( according to HIB catalogue)
    }
  ],
  "hospital_type": "phc",   // Types of hospital: PHC, Government, Private
  "enterer_reference": "7aa79c53-057e-4e77-8576-dfcfb03584a8", // UUID provided of the enterer
  "facility_reference": "1ac457d3-efd3-4a67-89b3-bf8cbe18045d", // Facility UUID
  "claim_time": "2025-12-09",
  "claim_code": "CLM11",  // Claim code: shall be upto 8 in length only
  "department": "ENT"     // Department the patient took service from
}
```

### Response Example

```json
{
  "local_validation": {
    "is_locally_valid": false,
    "warnings": [
      "Inter-department OPD visit within ticket validity requires referral documentation."
    ],
    "items": [
      {
        "item_code": "LAB145",
        "item_name": "AMMONIA",
        "quantity": 1,
        "claimable": true,
        "approved_amount": 960,
        "copay_amount": 96,
        "warnings": [],
        "type": "lab"
      }
    ],
    "total_approved_local": 960,
    "total_copay": 96,
    "net_claimable": 864,
    "applied_rules_version": "1.0",
    "allowed_money": 25520,
    "used_money": 0,
    "available_money": 25520
  },
  "imis_patient": {
    "resourceType": "Bundle",
    "entry": [
      {
        "fullUrl": "http://localhost/api/api_fhir/Patient/C335B6A2-738C-4373-AFF4-DAD1B8B09645",
        "resource": {
          "resourceType": "Patient",
          "address": [
            {
              "text": "0.0 0.0",
              "type": "both",
              "use": "home"
            }
          ],
          "birthDate": "2016-04-07",
          "extension": [
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960069653/FHIR+extension+isHead",
              "valueBoolean": true
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960331779/FHIR+extension+registrationDate",
              "valueString": "2024-07-31 15:52:57.760000"
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960495619/FHIR+extension+Location",
              "valueString": ""
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960331788/FHIR+extension+Education",
              "valueString": ""
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960135203/FHIE+extension+Profession",
              "valueString": ""
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,
              "valueString": "NormalHibScheme "
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+Photo+Url",
              "valueString": ""
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+FSP",
              "valueString": ""
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+District",
              "valueString": ""
            }
          ],
          "gender": "Male",
          "id": "C335B6A2-738C-4373-AFF4-DAD1B8B09645",
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
              "value": "C335B6A2-738C-4373-AFF4-DAD1B8B09645"
            },
            {
              "type": {
                "coding": [
                  {
                    "code": "SB",
                    "system": "https://hl7.org/fhir/valueset-identifier-type.html"
                  }
                ]
              },
              "use": "usual",
              "value": "740500036"
            },
            {
              "type": {
                "coding": [
                  {
                    "code": "PPN",
                    "system": "https://hl7.org/fhir/valueset-identifier-type.html"
                  }
                ]
              },
              "use": "usual",
              "value": ""
            }
          ],
          "name": [
            {
              "family": "Number",
              "given": [
                "Test Bima "
              ],
              "use": "usual"
            }
          ],
          "telecom": [
            {
              "system": "phone",
              "use": "home",
              "value": "9871717177"
            },
            {
              "system": "email",
              "use": "home",
              "value": ""
            }
          ]
        }
      }
    ],
    "link": [
      {
        "relation": "self",
        "url": "http://localhost/api/api_fhir/Patient/?identifier=740500036"
      }
    ],
    "total": 1,
    "type": "searchset"
  },
  "eligibility": {
    "success": true,
    "data": {
      "resourceType": "EligibilityResponse",
      "extension": [
        {
          "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+Photo+Url",
          "valueString": "https://imis.hib.gov.np/Images\\Updated\\/740500036_kat1_20240421_0.0_0.0.jpg"
        },
        {
          "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+FSP",
          "valueString": "TESTHF1 TEST API HOSPITAL"
        },
        {
          "url": "https://hib.gov.np/fhir/FHIE+extension+Profile+District",
          "valueString": ""
        }
      ],
      "insurance": [
        {
          "benefitBalance": [
            {
              "category": {
                "text": "medical"
              },
              "financial": [
                {
                  "allowedMoney": {
                    "value": 25520
                  },
                  "usedMoney": {
                    "value": 0
                  }
                }
              ]
            }
          ],
          "contract": {
            "reference": "Contract/HIB-3500/2026-11-16 00:00:00"
          },
          "extension": [
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,
              "valueString": "NormalHibScheme "
            }
          ]
        },
        {
          "benefitBalance": [
            {
              "category": {
                "text": "medical"
              },
              "financial": [
                {
                  "allowedMoney": {
                    "value": 99950
                  },
                  "usedMoney": {
                    "value": 0
                  }
                }
              ]
            }
          ],
          "contract": {
            "reference": "Contract/HIB-8D/2026-11-16 00:00:00"
          },
          "extension": [
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,
              "valueString": "NormalHibScheme "
            }
          ]
        }
      ]
    }
  }
}
```

---
