
**Endpoint:** `POST /Eligibility_check`

### Request Body

```json
{
  "patient_identifier": "string",
  "username": "Username",
  "password":"User password"
}
```

### Response Example

```json
{
  "patient_code": "740500036",       // Internal identifier of the patient in IMIS
  "uuid": "C335B6A2-738C-4373-AFF4-DAD1B8B09645",  // FHIR-compliant UUID
  "name": "Test Bima ",              // Patient full name
  "birthDate": "2016-04-07",         // Date of birth (YYYY-MM-DD)
  "gender": "Male",                   // Patient gender
  "copayment": "0.10",                // Copayment fraction (0.10 = 10%)
  "allowed_money": "25520.00",        // Total coverage allowed
  "used_money": "0.00",               // Already used amount
  "category": "medical",              // Type of benefit
  "policy_id": "HIB-3500",            // Policy number
  "policy_expiry": "2026-11-16",      // Policy expiration date
  "imis": {
    "resourceType": "Bundle",         // FHIR resource type
    "entry": [
      {
        "fullUrl": "http://localhost/api/api_fhir/Patient/C335B6A2-738C-4373-AFF4-DAD1B8B09645", // URL of patient resource
        "resource": {
          "resourceType": "Patient",   // Resource type
          "address": [
            {
              "text": "0.0 0.0",       // Address text
              "type": "both",         // Type of address
              "use": "home"           // Address use
            }
          ],
          "birthDate": "2016-04-07",   // Birth date
          "extension": [
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960069653/FHIR+extension+isHead",
              "valueBoolean": true    // Indicates if patient is head of household
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960331779/FHIR+extension+registrationDate",
              "valueString": "2024-07-31 15:52:57.760000" // Registration date
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,    // Copayment fraction
              "valueString": "NormalHibScheme " // Scheme name
            }
          ],
          "gender": "Male",             // Gender
          "id": "C335B6A2-738C-4373-AFF4-DAD1B8B09645", // UUID
          "identifier": [
            {
              "type": { "coding": [{"code": "ACSN"}]},
              "use": "usual",
              "value": "C335B6A2-738C-4373-AFF4-DAD1B8B09645" // FHIR UUID identifier
            },
            {
              "type": { "coding": [{"code": "SB"}]},
              "use": "usual",
              "value": "740500036"     // Secondary ID / Patient code
            }
          ],
          "name": [
            {
              "family": "Number",       // Last name
              "given": ["Test Bima "],  // First name(s)
              "use": "usual"
            }
          ],
          "telecom": [
            {
              "system": "phone",        // Contact type
              "use": "home",
              "value": "9871717177"    // Phone number
            }
          ]
        }
      }
    ],
    "total": 1                        // Number of entries
  },
  "eligibility": {
    "success": true,                  // Eligibility check success
    "data": {
      "resourceType": "EligibilityResponse",  // FHIR resource type
      "insurance": [
        {
          "benefitBalance": [
            {
              "category": { "text": "medical" }, // Benefit type
              "financial": [
                {
                  "allowedMoney": {"value": 25520}, // Allowed coverage
                  "usedMoney": {"value": 0}        // Already used
                }
              ]
            }
          ],
          "contract": {"reference": "Contract/HIB-3500/2026-11-16 00:00:00"}, // Policy reference
          "extension": [
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,
              "valueString": "NormalHibScheme "  // Copayment for this policy
            }
          ]
        }
      ]
    }
  }
}

```

---

